"""P4-08 check: real embeddings + real LLM, with questions IN and NOT IN the document.

Uses a throwaway database in the temp folder, so your real friday.db is untouched.
Run: set PYTHONPATH=.  then  python scripts\\rag_answer_spike.py
"""

import tempfile
from pathlib import Path

from friday import db
from friday.rag import answer, store

TEXT = (
    "Friday is a voice-first personal assistant built by Aditya in Bengaluru. "
    "It listens through a push-to-talk key, transcribes speech with faster-whisper, "
    "and speaks replies with Piper. "
    "Reminders are stored in SQLite and scheduled with APScheduler, so they survive a restart. "
    "Music is played through the Spotify Web API on a single named device. "
    "The chat skill keeps the last six turns of conversation as memory. "
    "Math is handled by a safe parser that never uses eval."
)

IN_DOC = [
    "What speaks the replies?",
    "How do reminders survive a restart?",
    "Which API plays the music?",
    "How many turns does the chat skill remember?",
]
NOT_IN_DOC = [
    "What is the capital of France?",
    "Which database does Friday use for the dashboard charts?",
    "What is Aditya's favourite colour?",
    "Does Friday support Telegram voice notes?",
]


def run(conn, label, questions):
    print(f"\n=== {label} ===")
    for q in questions:
        r = answer.answer_question(conn, q)
        top = f"{r.sources[0]['score']:.2f}" if r.sources else "-"
        print(f"\nQ: {q}")
        print(f"A: {r.text}")
        print(f"   grounded={r.grounded}  top score={top}")


with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "spike.db")
    store.add_document(conn, "friday-notes", TEXT, size=30, overlap=5)
    run(conn, "IN the document", IN_DOC)
    run(conn, "NOT in the document", NOT_IN_DOC)
    conn.close()