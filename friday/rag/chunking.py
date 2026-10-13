"""Split a document into overlapping word chunks for RAG."""

from __future__ import annotations

CHUNK_WORDS = 500
OVERLAP_WORDS = 50


def chunk_text(text: str, size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    """Split text into chunks of about `size` words, each sharing `overlap` words with the last.

    Whitespace (including newlines) is collapsed to single spaces. An empty text gives [].
    """
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Need size > 0 and 0 <= overlap < size.")
    words = text.split()
    if not words:
        return []
    step = size - overlap
    chunks: list[str] = []
    start = 0
    while True:
        end = start + size
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start += step
    return chunks