import zlib

import numpy as np
import pytest

from friday import db
from friday.llm import LLMReply
from friday.rag import answer, store

DIM = 64

DOC = (
    "apples oranges bananas fruit juice "
    "python code tests ruff pytest "
    "rain cloud storm weather wind"
)


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
    """Records the messages it was given and returns a fixed reply."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[list[dict]] = []

    def __call__(self, messages: list[dict]) -> LLMReply:
        self.calls.append(messages)
        return LLMReply(text=self.text, provider="fake", model="fake", ms=1)


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    store.add_document(connection, "demo", DOC, embed_fn=fake_embed, size=5, overlap=0)
    yield connection
    connection.close()


def test_grounded_answer_returns_text_and_sources(conn):
    fake = FakeAsk("A storm brings rain and wind.")
    result = answer.answer_question(conn, "storm wind weather", k=2, embed_fn=fake_embed, ask_fn=fake)
    assert result.grounded is True
    assert result.text == "A storm brings rain and wind."
    assert len(result.sources) == 2
    assert result.sources[0]["doc_name"] == "demo"
    assert len(fake.calls) == 1


def test_prompt_contains_the_excerpt_the_question_and_the_rules(conn):
    fake = FakeAsk("Some answer.")
    answer.answer_question(conn, "storm wind weather", k=1, embed_fn=fake_embed, ask_fn=fake)
    system, user = fake.calls[0]
    assert system["role"] == "system"
    assert answer.NOT_IN_DOC in system["content"]
    assert user["role"] == "user"
    assert "[1] rain cloud storm weather wind" in user["content"]
    assert "Question: storm wind weather" in user["content"]
    assert "apples" not in user["content"]


def test_refusal_from_the_llm_gives_fixed_text_and_no_sources(conn):
    fake = FakeAsk("That's not in the document.")
    result = answer.answer_question(conn, "storm wind weather", embed_fn=fake_embed, ask_fn=fake)
    assert result.grounded is False
    assert result.text == answer.NOT_IN_DOC
    assert result.sources == []


def test_refusal_with_curly_apostrophe_and_extra_words_still_counts(conn):
    fake = FakeAsk("Sorry, that\u2019s not in the document, but the weather is nice.")
    result = answer.answer_question(conn, "storm wind weather", embed_fn=fake_embed, ask_fn=fake)
    assert result.grounded is False
    assert result.text == answer.NOT_IN_DOC
    assert result.sources == []


def test_no_documents_does_not_call_the_llm(tmp_path):
    connection = db.connect(tmp_path / "empty.db")
    fake = FakeAsk("should never be used")
    result = answer.answer_question(connection, "anything", embed_fn=fake_embed, ask_fn=fake)
    assert result.grounded is False
    assert result.text == answer.NO_DOCUMENT
    assert fake.calls == []
    connection.close()


def test_blank_question_does_not_call_the_llm(conn):
    fake = FakeAsk("should never be used")
    result = answer.answer_question(conn, "   ", embed_fn=fake_embed, ask_fn=fake)
    assert result.grounded is False
    assert result.text == answer.NOT_IN_DOC
    assert fake.calls == []