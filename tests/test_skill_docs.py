import zlib

import numpy as np
import pytest

from friday import db
from friday.llm import LLMReply
from friday.rag import answer, store
from friday.router.router import normalize
from friday.skills.docs import DocsSkill

DIM = 64
SENTENCES = " ".join(f"Sentence {i} is here." for i in range(1, 61))  # 240 words, 4 per sentence


def fake_embed(texts: list[str]) -> np.ndarray:
    """Tiny deterministic stand-in for the real model: hashed bag of words."""
    out = np.zeros((len(texts), DIM), dtype="float32")
    for i, text in enumerate(texts):
        for word in text.lower().split():
            out[i, zlib.crc32(word.encode()) % DIM] += 1.0
        norm = np.linalg.norm(out[i])
        if norm:
            out[i] /= norm
    return out


class FakeAsk:
    def __init__(self, text: str = "Sentence 7 is here.") -> None:
        self.text = text
        self.calls: list[list[dict]] = []

    def __call__(self, messages: list[dict]) -> LLMReply:
        self.calls.append(messages)
        return LLMReply(text=self.text, provider="fake", model="fake", ms=1)


def say(skill: DocsSkill, sentence: str) -> str:
    return skill.run({"text": sentence, "clean": normalize(sentence)})


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "docs.db"
    conn = db.connect(path)
    store.add_document(conn, "demo", SENTENCES, embed_fn=fake_embed)
    conn.close()
    return path


@pytest.fixture
def empty_db_path(tmp_path):
    path = tmp_path / "empty.db"
    db.connect(path).close()
    return path


def test_can_handle_document_phrases():
    skill = DocsSkill()
    for sentence in (
        "what does the document say about reminders",
        "according to the document how do reminders work",
        "in the pdf what is the deadline",
        "read it to me",
        "read the document to me",
        "read me the document",
        "can you read the document to me please",
        "keep reading",
    ):
        assert skill.can_handle(sentence), sentence


def test_can_handle_ignores_other_commands():
    skill = DocsSkill()
    for sentence in (
        "what time is it",
        "what's on my shopping list",
        "read my notes",
        "add milk to my shopping list",
        "tell me a fun fact",
        "read it",
    ):
        assert not skill.can_handle(sentence), sentence


def test_question_returns_the_grounded_answer_and_keeps_sources(db_path):
    fake = FakeAsk("Sentence 7 is here.")
    skill = DocsSkill(db_path, embed_fn=fake_embed, ask_fn=fake)
    reply = say(skill, "What does the document say about sentence 7?")
    assert reply == "Sentence 7 is here."
    assert skill.last_answer.grounded is True
    assert skill.last_answer.sources[0]["doc_name"] == "demo"


def test_question_the_document_does_not_answer_is_refused(db_path):
    skill = DocsSkill(db_path, embed_fn=fake_embed, ask_fn=FakeAsk("That's not in the document."))
    reply = say(skill, "What does the document say about bananas?")
    assert reply == answer.NOT_IN_DOC
    assert skill.last_answer.grounded is False


def test_question_with_no_document_does_not_call_the_llm(empty_db_path):
    fake = FakeAsk()
    skill = DocsSkill(empty_db_path, embed_fn=fake_embed, ask_fn=fake)
    assert say(skill, "What does the document say about anything?") == answer.NO_DOCUMENT
    assert fake.calls == []


def test_reading_goes_in_parts_and_ends_cleanly(db_path):
    skill = DocsSkill(db_path, embed_fn=fake_embed, ask_fn=FakeAsk())
    first = say(skill, "Read it to me.")
    assert first.startswith("Sentence 1 is here.")
    assert "Sentence 26" not in first
    assert first.endswith("Say keep reading for more.")

    second = say(skill, "Keep reading.")
    assert second.startswith("Sentence 26 is here.")
    assert "Sentence 51" not in second

    third = say(skill, "Keep reading.")
    assert "Sentence 60 is here." in third
    assert third.endswith("That's the end of the document.")

    assert say(skill, "Keep reading.") == "Say read it to me first, then I can keep reading."
    assert say(skill, "Read it to me.").startswith("Sentence 1 is here.")


def test_reading_with_no_document(empty_db_path):
    skill = DocsSkill(empty_db_path, embed_fn=fake_embed, ask_fn=FakeAsk())
    assert say(skill, "Read it to me.") == answer.NO_DOCUMENT