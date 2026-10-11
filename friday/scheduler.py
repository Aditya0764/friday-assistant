"""Reminder scheduler: APScheduler wakes up on time, SQLite is the source of truth.

Every reminder is saved in the `reminders` table first. On start(), every reminder
that is not done yet is scheduled again, so reminders survive a restart. A reminder
that came due while Friday was off fires as soon as Friday starts.

`say` is the function that speaks (the voice loop passes one that takes a lock, so a
reminder never talks over a reply). It runs on the scheduler's own thread.
Each thread opens its own SQLite connection.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from friday import db
from friday.trace import Tracer


class ReminderScheduler:
    def __init__(self, say: Callable[[str], object], db_path: Path | None = None) -> None:
        self._say = say
        self._db_path = db_path
        self._scheduler = BackgroundScheduler(timezone=datetime.now().astimezone().tzinfo)

    def start(self) -> int:
        """Start the scheduler and re-schedule saved reminders. Returns how many."""
        self._scheduler.start()
        conn = db.connect(self._db_path)
        try:
            pending = db.pending_reminders(conn)
        finally:
            conn.close()
        for reminder in pending:
            self._schedule(reminder["id"], reminder["due_at"], reminder["text"])
        return len(pending)

    def add(self, text: str, due_at: datetime) -> int:
        """Save a reminder and schedule it. Returns its id."""
        conn = db.connect(self._db_path)
        try:
            reminder_id = db.add_reminder(conn, text, due_at)
        finally:
            conn.close()
        self._schedule(reminder_id, due_at, text)
        return reminder_id

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _schedule(self, reminder_id: int, due_at: datetime, text: str) -> None:
        self._scheduler.add_job(
            self._fire,
            "date",
            run_date=due_at,
            args=[reminder_id, text],
            id=f"reminder-{reminder_id}",
            misfire_grace_time=None,  # never skip: a late reminder still fires
            replace_existing=True,
        )

    def _fire(self, reminder_id: int, text: str) -> None:
        conn = db.connect(self._db_path)
        try:
            with Tracer(conn).step("reminder", text) as out:
                self._say(text)
                out["output"] = "spoken"
            db.mark_reminder_done(conn, reminder_id)
        except Exception as exc:  # noqa: BLE001 - stays pending, fires again at next start
            print(f"Reminder {reminder_id} failed: {exc}")
        finally:
            conn.close()