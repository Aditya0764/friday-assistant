"""Step-by-step trace logger. Every step is saved to SQLite with its time in ms."""

import sqlite3
import time
import uuid
from contextlib import contextmanager

from friday import db


class Tracer:
    """One Tracer = one run (for example, one user command)."""

    def __init__(self, conn: sqlite3.Connection, run_id: str | None = None):
        self.conn = conn
        self.run_id = run_id or uuid.uuid4().hex[:12]

    def log(self, step: str, input_text: str, output_text: str, ms: int) -> None:
        db.add_trace(self.conn, self.run_id, step, str(input_text), str(output_text), ms)

    @contextmanager
    def step(self, name: str, input_text: str = ""):
        """Time a block of code and save it as one trace row.

        Set out["output"] inside the block to record what the step produced.
        """
        start = time.perf_counter()
        out = {"output": ""}
        try:
            yield out
        except Exception as exc:
            out["output"] = f"ERROR: {exc}"
            raise
        finally:
            ms = round((time.perf_counter() - start) * 1000)
            self.log(name, input_text, out["output"], ms)