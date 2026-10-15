"""Tests for the document list, paste, sources in /chat and shared skills.
Fake embedder and fake LLM: no models, no network."""

from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from friday.api.app import create_app
from friday.skills.base import SkillRegistry
from friday.skills.docs import DocsSkill
from friday.skills.echo import EchoSkill
from friday.skills.lists import ListsSkill

ANSWER = "The speaker is a JBL."
LONG_TEXT = " ".join(f"Sentence number {n} ends here." for n in range(80)).encode()


def fake_embed(texts):
    return np.ones((len(texts), 4), dtype=np.float32)


def fake_ask(messages):
    return SimpleNamespace(text=ANSWER, provider="fake", model="fake", ms=0)


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "t.db"
    registry = SkillRegistry()
    registry.register(EchoSkill())
    registry.register(ListsSkill(db_path))
    registry.register(DocsSkill(db_path, embed_fn=fake_embed, ask_fn=fake_ask))
    api = create_app(db_path=db_path, embed_fn=fake_embed, registry=registry)
    return TestClient(api)


def upload(client, name, data=b"The speaker is a JBL and sits on the table."):
    return client.post("/documents", files={"file": (name, data, "text/plain")})


def chat(client, text):
    r = client.post("/chat", json={"text": text})
    assert r.status_code == 200
    return r.json()


def test_list_is_empty_at_first(client):
    r = client.get("/documents")
    assert r.status_code == 200
    assert r.json() == []


def test_list_shows_newest_first(client):
    upload(client, "a.txt")
    upload(client, "b.txt")
    names = [d["name"] for d in client.get("/documents").json()]
    assert names == ["b.txt", "a.txt"]


def test_paste_document(client):
    r = client.post("/documents/text", json={"name": "my note", "text": "hello world, this is a note"})
    assert r.status_code == 200
    assert r.json()["name"] == "my note"
    assert r.json()["chunks"] >= 1
    assert [d["name"] for d in client.get("/documents").json()] == ["my note"]


def test_paste_without_name_gets_a_name(client):
    r = client.post("/documents/text", json={"text": "some pasted words"})
    assert r.status_code == 200
    assert r.json()["name"].startswith("pasted-")


def test_paste_same_name_twice_is_rejected(client):
    body = {"name": "note", "text": "some pasted words"}
    assert client.post("/documents/text", json=body).status_code == 200
    assert client.post("/documents/text", json=body).status_code == 400


def test_paste_blank_text_is_rejected(client):
    r = client.post("/documents/text", json={"name": "x", "text": "    "})
    assert r.status_code == 400


def test_document_answer_comes_with_sources(client):
    upload(client, "notes.txt")
    body = chat(client, "what does the document say about the speaker")
    assert body["skill"] == "docs"
    assert body["reply"] == ANSWER
    assert body["grounded"] is True
    assert body["sources"]
    assert body["sources"][0]["doc_name"] == "notes.txt"
    assert "JBL" in body["sources"][0]["text"]


def test_document_question_with_no_document(client):
    body = chat(client, "what does the document say about the speaker")
    assert body["skill"] == "docs"
    assert body["grounded"] is False
    assert body["sources"] == []


def test_normal_chat_has_no_sources(client):
    body = chat(client, "echo hello friday")
    assert body["sources"] == []
    assert body["grounded"] is None


def test_reading_place_is_kept_between_requests(client):
    upload(client, "long.txt", LONG_TEXT)
    first = chat(client, "read it to me")["reply"]
    second = chat(client, "keep reading")["reply"]
    assert "Say keep reading for more." in first
    assert not second.startswith("Say read it to me first")
    assert second != first


def test_reading_turn_has_no_stale_sources(client):
    upload(client, "notes.txt")
    chat(client, "what does the document say about the speaker")
    body = chat(client, "read it to me")
    assert body["sources"] == []
    assert body["grounded"] is None


def test_lists_work_across_requests(client):
    chat(client, "add milk to my shopping list")
    body = chat(client, "what's on my shopping list")
    assert "milk" in body["reply"].lower()