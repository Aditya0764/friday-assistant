"""The key-start log (what started a recording, per the keyboard hook; modifier keys only)."""

import time
from collections import deque

from friday.voice import audio


def test_no_hook_events_is_said_plainly():
    line = audio.describe_key_start("right ctrl", [], 10.0)
    assert "hook saw no modifier events yet" in line and "is_pressed=True" in line


def test_line_names_the_last_event_and_its_age():
    events = [("down", "left alt", 56, 8.0), ("up", "right ctrl", 29, 9.5)]
    line = audio.describe_key_start("right ctrl", events, 10.0)
    assert "up 'right ctrl' scan 29 0.50s ago" in line
    assert "down left alt/56 2.00s ago" in line


def test_only_modifier_keys_are_remembered():
    events: deque = deque(maxlen=6)
    for name, scan in [("a", 30), ("enter", 28), ("space", 57), ("f9", 67), (None, 0)]:
        audio.note_key(events, "down", name, scan)
    assert not events
    for name in ["ctrl", "right ctrl", "alt", "right alt", "alt gr", "shift", "windows",
                 "left windows", "Right Ctrl"]:
        audio.note_key(events, "down", name, 1)
    assert len(events) == 6  # the deque holds the newest 6 of the 9 modifiers


def test_a_non_modifier_key_never_reaches_the_printed_line_or_the_file(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(audio, "KEY_LOG", tmp_path / "key_events.log")
    events: deque = deque(maxlen=6)
    audio.note_key(events, "down", "a", 30)
    audio.note_key(events, "down", "right ctrl", 29)
    audio.note_key(events, "up", "q", 16)
    now = time.monotonic()
    audio._write_key_log("key-start (right ctrl)", audio.describe_key_start("right ctrl", list(events), now))
    audio._write_key_log("key-end held 0.40s")
    shown = capsys.readouterr().out
    logged = (tmp_path / "key_events.log").read_text()
    assert "key-start (right ctrl)" in shown and "key-end held 0.40s" in shown
    assert "scan" not in shown and "is_pressed" not in shown  # detail is file-only
    assert "is_pressed=True" in logged and "right ctrl" in logged
    for text in (shown, logged):
        assert "'a'" not in text and "'q'" not in text and "/30" not in text and "/16" not in text


def test_log_keeps_only_the_newest_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "KEY_LOG", tmp_path / "key_events.log")
    monkeypatch.setattr(audio, "KEY_LOG_LINES", 5)
    for i in range(12):
        audio._write_key_log(f"line {i}")
    lines = (tmp_path / "key_events.log").read_text().splitlines()
    assert len(lines) == 5
    assert lines[0].endswith("line 7") and lines[-1].endswith("line 11")


def test_log_write_failure_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "KEY_LOG", tmp_path)  # a directory: the write fails
    audio._write_key_log("still fine")
