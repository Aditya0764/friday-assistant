"""Add a document to Friday from the command line.

Run: python -m friday.rag.ingest path\\to\\file.pdf   (also .txt and .md)
Text PDFs only: scanned PDFs have no text layer and would need OCR, which is out of scope.
The first run loads the embedding model, so it takes a little while.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np

from friday import db
from friday.rag import store
from friday.rag.embedder import embed

TEXT_SUFFIXES = {".txt", ".md"}


def load_text(path: Path) -> str:
    """Read the text of a .pdf, .txt or .md file. Raises ValueError with a clear message."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"File not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(path)
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # pypdf raises many different errors
            raise ValueError(f"Couldn't read the PDF: {exc}") from exc
        if not text.strip():
            raise ValueError(
                "No text found in this PDF. Scanned PDFs need OCR, which Friday doesn't do."
            )
        return text
    if suffix in TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            raise ValueError("The file is empty.")
        return text
    raise ValueError("Only .pdf, .txt and .md files are supported.")


def ingest_file(
    conn: sqlite3.Connection,
    path: Path,
    embed_fn: Callable[[list[str]], np.ndarray] = embed,
) -> int:
    """Load, chunk, embed and save a file. Returns the document id."""
    path = Path(path)
    store.ensure_tables(conn)
    if any(doc["name"] == path.name for doc in store.list_documents(conn)):
        raise ValueError(f"{path.name} is already added.")
    text = load_text(path)
    return store.add_document(conn, path.name, text, embed_fn=embed_fn)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python -m friday.rag.ingest path\\to\\file.pdf")
        return 1
    conn = db.connect()
    try:
        doc_id = ingest_file(conn, Path(argv[1]))
        doc = next(d for d in store.list_documents(conn) if d["id"] == doc_id)
    except ValueError as exc:
        print(exc)
        return 1
    finally:
        conn.close()
    print(f"Added {doc['name']} as document {doc['id']} ({doc['chunk_count']} chunks).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))