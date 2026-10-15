"""Chat memory for the channels: the last few turns from SQLite."""

from __future__ import annotations

import sqlite3

from friday import db

MEMORY_TURNS = 6  # one turn = the user's message + Friday's reply


def load_history(conn: sqlite3.Connection, turns: int = MEMORY_TURNS) -> list[dict]:
    """Last N turns, starting on a user message (same rule as the voice loop)."""
    history = db.recent_messages(conn, turns * 2)
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history