import zlib

import numpy as np
import pytest
from pypdf import PdfWriter

from friday import db
from friday.rag import store
from friday.rag.ingest import ingest_file, load_text

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


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def test_text_file_is_ingested(conn, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Friday uses Piper for speech. Reminders use APScheduler.", encoding="utf-8")
    doc_id = ingest_file(conn, path, embed_fn=fake_embed)
    docs = store.list_documents(conn)
    assert docs[0]["id"] == doc_id
    assert docs[0]["name"] == "notes.txt"
    assert docs[0]["chunk_count"] == 1


def test_missing_file_is_rejected(conn, tmp_path):
    with pytest.raises(ValueError, match="not found"):
        ingest_file(conn, tmp_path / "nope.txt", embed_fn=fake_embed)


def test_unsupported_type_is_rejected(tmp_path):
    path = tmp_path / "pic.png"
    path.write_bytes(b"not really a picture")
    with pytest.raises(ValueError, match="Only"):
        load_text(path)


def test_empty_text_file_is_rejected(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("  \n ", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_text(path)


def test_pdf_without_text_is_rejected_like_a_scan(tmp_path):
    path = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with open(path, "wb") as handle:
        writer.write(handle)
    with pytest.raises(ValueError, match="No text found"):
        load_text(path)


def test_same_file_twice_is_rejected(conn, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Some words here.", encoding="utf-8")
    ingest_file(conn, path, embed_fn=fake_embed)
    with pytest.raises(ValueError, match="already added"):
        ingest_file(conn, path, embed_fn=fake_embed)
    assert len(store.list_documents(conn)) == 1