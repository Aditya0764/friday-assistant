import zlib

import numpy as np
import pytest

from friday import db
from friday.rag import store

DIM = 64


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


DOC = (
    "apples oranges bananas fruit juice "
    "python code tests ruff pytest "
    "rain cloud storm weather wind"
)


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def test_add_document_saves_text_and_chunks(conn):
    doc_id = store.add_document(conn, "demo", DOC, embed_fn=fake_embed, size=5, overlap=0)
    docs = store.list_documents(conn)
    assert docs[0]["id"] == doc_id
    assert docs[0]["name"] == "demo"
    assert docs[0]["chunk_count"] == 3


def test_search_finds_the_right_chunk(conn):
    store.add_document(conn, "demo", DOC, embed_fn=fake_embed, size=5, overlap=0)
    results = store.search(conn, "storm and wind weather", k=2, embed_fn=fake_embed)
    assert len(results) == 2
    assert results[0]["idx"] == 2
    assert results[0]["doc_name"] == "demo"
    assert results[0]["score"] >= results[1]["score"]


def test_search_limits_to_k(conn):
    store.add_document(conn, "demo", DOC, embed_fn=fake_embed, size=5, overlap=0)
    assert len(store.search(conn, "python", k=1, embed_fn=fake_embed)) == 1


def test_search_with_no_documents_is_empty(conn):
    assert store.search(conn, "anything", embed_fn=fake_embed) == []


def test_empty_document_is_rejected_and_saves_nothing(conn):
    with pytest.raises(ValueError):
        store.add_document(conn, "empty", "   ", embed_fn=fake_embed)
    assert store.list_documents(conn) == []