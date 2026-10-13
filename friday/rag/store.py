"""Store document chunks and their vectors in SQLite, search them with FAISS.

The `documents` table (from db.py) holds the full text. This module adds a `chunks`
table with one row per chunk and its vector as a BLOB. The FAISS index is built in
memory from that table at search time, so there is no separate index file to get out
of sync with SQLite. With a few documents this is instant.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

import faiss
import numpy as np

from friday.rag.chunking import CHUNK_WORDS, OVERLAP_WORDS, chunk_text
from friday.rag.embedder import embed

EmbedFn = Callable[[list[str]], np.ndarray]

CHUNKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL
);
"""


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(CHUNKS_SCHEMA)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def add_document(
    conn: sqlite3.Connection,
    name: str,
    text: str,
    embed_fn: EmbedFn = embed,
    size: int = CHUNK_WORDS,
    overlap: int = OVERLAP_WORDS,
) -> int:
    """Chunk, embed and save a document. Returns the document id."""
    ensure_tables(conn)
    chunks = chunk_text(text, size, overlap)
    if not chunks:
        raise ValueError("The document has no text.")
    vectors = np.asarray(embed_fn(chunks), dtype="float32")  # embed first: a failure saves nothing
    cur = conn.execute(
        "INSERT INTO documents (name, text, created_at) VALUES (?, ?, ?)",
        (name, text, _now()),
    )
    doc_id = int(cur.lastrowid)
    conn.executemany(
        "INSERT INTO chunks (doc_id, idx, text, embedding) VALUES (?, ?, ?, ?)",
        [(doc_id, i, chunks[i], vectors[i].tobytes()) for i in range(len(chunks))],
    )
    conn.commit()
    return doc_id


def list_documents(conn: sqlite3.Connection) -> list[dict]:
    ensure_tables(conn)
    rows = conn.execute(
        "SELECT d.id, d.name, d.created_at, COUNT(c.id) AS chunk_count "
        "FROM documents d LEFT JOIN chunks c ON c.doc_id = d.id "
        "GROUP BY d.id ORDER BY d.id"
    ).fetchall()
    return [dict(r) for r in rows]


def search(
    conn: sqlite3.Connection,
    query: str,
    k: int = 4,
    embed_fn: EmbedFn = embed,
) -> list[dict]:
    """Return the top-k chunks for the query, best first.

    Each result: doc_id, doc_name, idx, text, score (cosine similarity, higher = closer).
    """
    ensure_tables(conn)
    rows = conn.execute(
        "SELECT c.doc_id, d.name AS doc_name, c.idx, c.text, c.embedding "
        "FROM chunks c JOIN documents d ON d.id = c.doc_id ORDER BY c.id"
    ).fetchall()
    if not rows or not query.strip():
        return []
    matrix = np.vstack([np.frombuffer(r["embedding"], dtype="float32") for r in rows])
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    q = np.asarray(embed_fn([query]), dtype="float32")
    scores, ids = index.search(q, min(k, len(rows)))
    results = []
    for score, i in zip(scores[0], ids[0], strict=True):
        if i < 0:
            continue
        r = rows[int(i)]
        results.append(
            {
                "doc_id": r["doc_id"],
                "doc_name": r["doc_name"],
                "idx": r["idx"],
                "text": r["text"],
                "score": float(score),
            }
        )
    return results