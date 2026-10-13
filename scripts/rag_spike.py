"""P4-07 check: ingest a pasted text with the REAL model and search it.

Uses a throwaway database in the temp folder, so your real friday.db is untouched.
Run: python scripts\\rag_spike.py
"""

import tempfile
import time
from pathlib import Path

from friday import db
from friday.rag import store

TEXT = (
    "Friday is a voice-first personal assistant built by Aditya in Bengaluru. "
    "It listens through a push-to-talk key, transcribes speech with faster-whisper, "
    "and speaks replies with Piper. "
    "Reminders are stored in SQLite and scheduled with APScheduler, so they survive a restart. "
    "Music is played through the Spotify Web API on a single named device. "
    "The chat skill keeps the last six turns of conversation as memory. "
    "Math is handled by a safe parser that never uses eval."
)

QUESTIONS = [
    "What speaks the replies?",
    "How do reminders survive a restart?",
    "Which API plays the music?",
]

with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "spike.db")

    t0 = time.perf_counter()
    store.add_document(conn, "friday-notes", TEXT, size=30, overlap=5)
    print(f"Ingest (includes first model load): {time.perf_counter() - t0:.1f} s")

    for q in QUESTIONS:
        t0 = time.perf_counter()
        hits = store.search(conn, q, k=2)
        ms = (time.perf_counter() - t0) * 1000
        print(f"\nQ: {q}  ({ms:.0f} ms)")
        for h in hits:
            print(f"  [{h['score']:.2f}] chunk {h['idx']}: {h['text'][:90]}...")
    conn.close()