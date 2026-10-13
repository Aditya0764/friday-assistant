"""Documents by voice: ask questions about the latest document, or have it read aloud.

Understood: "What does the document say about X?", "According to the document, ...",
"In the PDF, ...", "Read it to me", "Read the document to me", "Keep reading".
Questions go through answer_question, so a document that doesn't say it gets
"That's not in the document." and never an invented answer.
Reading: about READ_WORDS words at a time, ending on a sentence. Say "keep reading" for the next part.
It works on the most recent document. The last answer (with its sources) is kept in
`last_answer` for the dashboard to show later.
Not supported yet: choosing a document by name, stopping mid-sentence.
"""

from __future__ import annotations

import re
from pathlib import Path

from friday import db
from friday.llm import ask
from friday.rag import answer
from friday.rag.embedder import embed
from friday.skills.base import Skill

READ_WORDS = 100  # about 40 seconds of speech per part
READ_EXTRA = 60  # may run this many words over to finish a sentence

_DOC = r"(?:the|this|my) (?:document|doc|pdf|paper)"
_OPENING = r"(?:(?:can|could) you |please |hey friday |friday )?"

_ASK = re.compile(
    rf"\b(?:what does {_DOC} (?:say|tell)|according to {_DOC}|(?:in|from|based on) {_DOC})\b"
)
_READ = re.compile(
    rf"{_OPENING}read (?:it to me|{_DOC}(?: to me)?|me {_DOC})(?: out loud| aloud)?(?: please)?"
)
_MORE = re.compile(
    r"(?:please )?(?:keep reading|continue reading|read more|read on|carry on reading)(?: please)?"
)


class DocsSkill(Skill):
    name = "docs"

    def __init__(self, db_path: Path | None = None, embed_fn=embed, ask_fn=ask) -> None:
        self._db_path = db_path
        self._embed_fn = embed_fn
        self._ask_fn = ask_fn
        self._cursor: tuple[int, int] | None = None  # (document id, next word to read)
        self.last_answer: answer.RagAnswer | None = None

    def can_handle(self, text: str) -> bool:
        return bool(_READ.fullmatch(text) or _MORE.fullmatch(text) or _ASK.search(text))

    def run(self, args: dict[str, str]) -> str:
        clean = args.get("clean", "")
        conn = db.connect(self._db_path)
        try:
            if _READ.fullmatch(clean):
                return self._read(conn, restart=True)
            if _MORE.fullmatch(clean):
                return self._read(conn, restart=False)
            return self._ask(conn, args.get("text") or clean)
        finally:
            conn.close()

    def _ask(self, conn, question: str) -> str:
        result = answer.answer_question(
            conn, question, embed_fn=self._embed_fn, ask_fn=self._ask_fn
        )
        self.last_answer = result
        return result.text

    def _read(self, conn, restart: bool) -> str:
        row = conn.execute(
            "SELECT id, text FROM documents ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return answer.NO_DOCUMENT
        words = row["text"].split()
        if restart:
            start = 0
        elif self._cursor and self._cursor[0] == row["id"]:
            start = self._cursor[1]
        else:
            return "Say read it to me first, then I can keep reading."
        if start >= len(words):
            self._cursor = None
            return "That's the end of the document."
        end = min(start + READ_WORDS, len(words))
        limit = min(start + READ_WORDS + READ_EXTRA, len(words))
        while end < limit and not words[end - 1].endswith((".", "!", "?")):
            end += 1
        piece = " ".join(words[start:end])
        if end >= len(words):
            self._cursor = None
            return f"{piece} That's the end of the document."
        self._cursor = (row["id"], end)
        return f"{piece} Say keep reading for more."