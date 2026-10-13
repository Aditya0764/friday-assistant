"""Answer a question from the stored documents, and refuse when the document doesn't say.

Flow: search the top chunks, give them to the LLM as numbered excerpts with a strict
system prompt, then check the reply in code. If the LLM says the excerpts don't answer
the question, we return the fixed refusal and no sources, so a made-up answer can't
slip through with a source list attached.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

from friday.llm import LLMReply, ask
from friday.rag import store
from friday.rag.embedder import embed

AskFn = Callable[[list[dict]], LLMReply]

NOT_IN_DOC = "That's not in the document."
NO_DOCUMENT = "I don't have a document yet. Paste one in first."

RAG_PROMPT = (
    "You answer questions using ONLY the numbered excerpts you are given. "
    "Your answer is spoken aloud, so use 2 to 3 short sentences of plain text: no markdown, "
    "no lists, no emoji, no line breaks. "
    "Do not use outside knowledge and do not guess. "
    "If the excerpts do not clearly answer the question, reply with exactly: "
    f"{NOT_IN_DOC}"
)


@dataclass(frozen=True)
class RagAnswer:
    text: str
    grounded: bool  # True = answered from the document, False = refused or no document
    sources: list[dict] = field(default_factory=list)  # doc_name, idx, score, text


def _is_refusal(text: str) -> bool:
    cleaned = text.lower().replace("\u2019", "'")
    return "not in the document" in cleaned


def _build_messages(question: str, hits: list[dict]) -> list[dict]:
    excerpts = "\n\n".join(f"[{n}] {hit['text']}" for n, hit in enumerate(hits, start=1))
    user = f"Excerpts:\n{excerpts}\n\nQuestion: {question}"
    return [
        {"role": "system", "content": RAG_PROMPT},
        {"role": "user", "content": user},
    ]


def answer_question(
    conn: sqlite3.Connection,
    question: str,
    k: int = 4,
    embed_fn=embed,
    ask_fn: AskFn = ask,
) -> RagAnswer:
    """Answer from the top-k chunks, or say it's not in the document."""
    if not store.list_documents(conn):
        return RagAnswer(text=NO_DOCUMENT, grounded=False)
    hits = store.search(conn, question, k=k, embed_fn=embed_fn)
    if not hits:
        return RagAnswer(text=NOT_IN_DOC, grounded=False)
    reply = ask_fn(_build_messages(question, hits))
    text = reply.text.strip()
    if not text or _is_refusal(text):
        return RagAnswer(text=NOT_IN_DOC, grounded=False)
    return RagAnswer(text=text, grounded=True, sources=hits)