"""SQLite storage for Friday: messages, reminders, lists, traces, documents."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from friday.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    channel TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS list_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_name TEXT NOT NULL,
    item TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    step TEXT NOT NULL,
    input TEXT,
    output TEXT,
    ms INTEGER
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the database (creating the file and tables if needed)."""
    path = Path(db_path) if db_path else get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def add_message(conn: sqlite3.Connection, role: str, content: str, channel: str = "cli") -> int:
    cur = conn.execute(
        "INSERT INTO messages (ts, channel, role, content) VALUES (?, ?, ?, ?)",
        (_now(), channel, role, content),
    )
    conn.commit()
    return cur.lastrowid


def recent_messages(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """Last `limit` messages, oldest first, in the shape llm.ask() expects."""
    rows = conn.execute(
        "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in reversed(rows)]


def add_trace(
    conn: sqlite3.Connection,
    run_id: str,
    step: str,
    input_text: str,
    output_text: str,
    ms: int,
) -> int:
    cur = conn.execute(
        "INSERT INTO traces (run_id, ts, step, input, output, ms) VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, _now(), step, input_text, output_text, ms),
    )
    conn.commit()
    return cur.lastrowid


def get_traces(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT step, input, output, ms FROM traces WHERE run_id = ? ORDER BY id", (run_id,)
    ).fetchall()
    return [dict(row) for row in rows]