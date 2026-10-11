import time
from datetime import datetime, timedelta

import pytest

from friday import db
from friday.scheduler import ReminderScheduler


def _soon(seconds=0.5):
    return datetime.now().astimezone() + timedelta(seconds=seconds)


def _wait_until(check, timeout=6.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.05)
    return False


def _pending(path):
    conn = db.connect(path)
    try:
        return db.pending_reminders(conn)
    finally:
        conn.close()


def test_db_rejects_naive_datetimes(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    with pytest.raises(ValueError, match="timezone-aware"):
        db.add_reminder(conn, "x", datetime(2026, 10, 11, 18, 0))
    conn.close()


def test_db_pending_order_and_done(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    later = db.add_reminder(conn, "later", _soon(60))
    sooner = db.add_reminder(conn, "sooner", _soon(30))
    assert [r["text"] for r in db.pending_reminders(conn)] == ["sooner", "later"]
    assert db.pending_reminders(conn)[0]["due_at"].tzinfo is not None
    db.mark_reminder_done(conn, sooner)
    assert [r["id"] for r in db.pending_reminders(conn)] == [later]
    conn.close()


def test_reminder_fires_once_and_is_marked_done(tmp_path):
    path = tmp_path / "t.db"
    spoken = []
    scheduler = ReminderScheduler(spoken.append, db_path=path)
    scheduler.start()
    try:
        scheduler.add("Reminder: test.", _soon())
        assert _wait_until(lambda: spoken)
        assert _wait_until(lambda: not _pending(path))
    finally:
        scheduler.shutdown()
    assert spoken == ["Reminder: test."]
    conn = db.connect(path)
    steps = [row["step"] for row in conn.execute("SELECT step FROM traces")]
    conn.close()
    assert steps == ["reminder"]


def test_reminder_survives_a_restart(tmp_path):
    path = tmp_path / "t.db"
    first_spoken = []
    first = ReminderScheduler(first_spoken.append, db_path=path)
    first.start()
    first.add("Reminder: after restart.", _soon(1.0))
    first.shutdown()  # "Friday quits" before the reminder is due
    assert first_spoken == []

    second_spoken = []
    second = ReminderScheduler(second_spoken.append, db_path=path)
    try:
        assert second.start() == 1
        assert _wait_until(lambda: second_spoken)
    finally:
        second.shutdown()
    assert second_spoken == ["Reminder: after restart."]


def test_reminder_that_came_due_while_off_fires_on_start(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    db.add_reminder(conn, "Reminder: missed one.", datetime.now().astimezone() - timedelta(hours=1))
    conn.close()

    spoken = []
    scheduler = ReminderScheduler(spoken.append, db_path=path)
    try:
        scheduler.start()
        assert _wait_until(lambda: spoken)
    finally:
        scheduler.shutdown()
    assert spoken == ["Reminder: missed one."]


def test_failed_speech_keeps_the_reminder_pending(tmp_path):
    path = tmp_path / "t.db"

    def broken_say(text):
        raise RuntimeError("speaker unplugged")

    scheduler = ReminderScheduler(broken_say, db_path=path)
    scheduler.start()
    try:
        scheduler.add("Reminder: important.", _soon())
        time.sleep(1.5)
    finally:
        scheduler.shutdown()
    assert [r["text"] for r in _pending(path)] == ["Reminder: important."]