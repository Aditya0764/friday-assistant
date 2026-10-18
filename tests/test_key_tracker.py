"""Push-to-talk follows the key by NAME: left ctrl never starts a recording, right ctrl does."""

import sys
import threading
import time
import types

import numpy as np
import pytest

from friday.voice import audio
from friday.voice.audio import KeyTracker


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class FakeKeyboard:
    """Stands in for the `keyboard` library: a hook, and an is_pressed that (like the real one)
    is True for BOTH ctrl keys because they share scan code 29."""

    def __init__(self, hook_fails: bool = False) -> None:
        self.callbacks, self.down, self.hook_fails = [], set(), hook_fails

    def hook(self, callback):
        if self.hook_fails:
            raise OSError("no permission")
        self.callbacks.append(callback)
        return callback

    def unhook(self, callback) -> None:
        self.callbacks.remove(callback)

    def is_pressed(self, key: str) -> bool:
        if key == "right ctrl":
            return bool(self.down & {"ctrl", "right ctrl"})
        return key in self.down

    def send(self, event_type: str, name: str, scan: int = 29) -> None:
        (self.down.add if event_type == "down" else self.down.discard)(name)
        event = types.SimpleNamespace(event_type=event_type, name=name, scan_code=scan)
        for callback in list(self.callbacks):
            callback(event)


def tracker(kb, clock=None):
    t = KeyTracker("right ctrl", clock=clock or Clock())
    assert t.install(kb)
    return t


def test_left_ctrl_never_counts_even_though_the_library_says_pressed():
    kb = FakeKeyboard()
    t = tracker(kb)
    kb.send("down", "ctrl")
    assert kb.is_pressed("right ctrl") is True  # the library bug this fixes
    assert t.is_down() is False
    kb.send("up", "ctrl")
    for name in ("left alt", "right alt", "shift", "a"):
        kb.send("down", name, 30)
        assert t.is_down() is False


def test_right_ctrl_down_and_up():
    kb = FakeKeyboard()
    t = tracker(kb)
    kb.send("down", "right ctrl")
    assert t.is_down() is True
    kb.send("up", "right ctrl")
    assert t.is_down() is False


def test_right_ctrl_held_while_left_ctrl_is_tapped_keeps_going():
    kb = FakeKeyboard()
    t = tracker(kb)
    kb.send("down", "right ctrl")
    kb.send("down", "ctrl")
    kb.send("up", "ctrl")
    assert t.is_down() is True
    kb.send("up", "right ctrl")
    assert t.is_down() is False


def test_auto_repeat_downs_do_not_restart_the_hold_timer():
    kb, clock = FakeKeyboard(), Clock()
    t = tracker(kb, clock)
    kb.send("down", "right ctrl")
    clock.now += audio.MAX_HOLD_SECONDS - 1
    kb.send("down", "right ctrl")  # auto-repeat
    clock.now += 2
    assert t.is_down() is False  # still measured from the first down


def test_lost_key_up_is_released_when_the_library_says_no_ctrl_is_held():
    kb, clock = FakeKeyboard(), Clock()
    t = tracker(kb, clock)
    kb.send("down", "right ctrl")
    kb.down.clear()  # the key-up was lost; the library table also lost the key
    assert t.is_down() is True  # inside the grace period the lag is allowed
    clock.now += audio.GRACE_SECONDS + 0.01
    assert t.is_down() is False
    assert t.is_down() is False  # and it stays released


def test_lost_key_up_with_a_stale_library_table_ends_after_the_max_hold():
    kb, clock = FakeKeyboard(), Clock()
    t = tracker(kb, clock)
    kb.send("down", "right ctrl")  # the library table keeps saying "pressed" (stale)
    clock.now += audio.MAX_HOLD_SECONDS - 1
    assert t.is_down() is True
    clock.now += 2
    assert t.is_down() is False
    kb.send("down", "right ctrl")  # a new real press works again
    assert t.is_down() is True


def test_hook_failure_warns_once_and_says_the_fallback(capsys, monkeypatch):
    monkeypatch.setattr(audio, "_warned_no_hook", False)
    kb = FakeKeyboard(hook_fails=True)
    t = KeyTracker("right ctrl")
    assert t.install(kb) is False
    out = capsys.readouterr().out
    assert "WARNING" in out and "LEFT ctrl" in out and "is_pressed" in out
    kb.down.add("ctrl")
    assert t.is_down() is True  # the announced fallback: old behaviour
    KeyTracker("right ctrl").install(kb)
    assert capsys.readouterr().out == ""  # only one warning per run


def test_the_modifier_log_still_sees_events_but_not_other_keys():
    seen = []
    t = KeyTracker("right ctrl", on_event=lambda *e: seen.append(e))
    t.handle("down", "ctrl", 29)
    t.handle("down", "a", 30)
    assert seen == [("down", "ctrl", 29), ("down", "a", 30)]  # filtering is note_key's job


# ---- record_while_held with the fake keyboard -----------------------------------------------


@pytest.fixture
def rig(monkeypatch, tmp_path):
    kb = FakeKeyboard()

    class FakeStream:
        def __init__(self, callback, **_):
            self.callback = callback

        def __enter__(self):
            self.stop = threading.Event()
            threading.Thread(target=self._feed, daemon=True).start()
            return self

        def __exit__(self, *_):
            self.stop.set()

        def _feed(self):
            while not self.stop.is_set():
                self.callback(np.full((160, 1), 0.1, dtype=np.float32), 160, None, None)
                time.sleep(0.005)

    monkeypatch.setitem(sys.modules, "keyboard", kb)
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(InputStream=FakeStream))
    monkeypatch.setattr(audio, "KEY_LOG", tmp_path / "key_events.log")
    result = {}
    thread = threading.Thread(target=lambda: result.update(cap=audio.record_while_held()))
    thread.start()
    time.sleep(0.1)  # let it install the hook and start waiting
    yield kb, thread, result
    kb.down.clear()
    for name in list(kb.down) + ["right ctrl"]:
        kb.send("up", name)
    thread.join(timeout=3)


def test_record_while_held_ignores_left_ctrl_and_follows_right_ctrl(rig):
    kb, thread, result = rig
    kb.send("down", "ctrl")  # Ctrl+C: must not start anything
    time.sleep(0.2)
    kb.send("up", "ctrl")
    assert thread.is_alive() and "cap" not in result
    kb.send("down", "right ctrl")
    time.sleep(0.2)
    kb.send("down", "ctrl")  # left ctrl tapped while right ctrl is held
    kb.send("up", "ctrl")
    time.sleep(0.1)
    assert thread.is_alive()  # still recording
    kb.send("up", "right ctrl")
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert 0.2 < result["cap"].seconds and result["cap"].peak == pytest.approx(0.1)
    assert kb.callbacks == []  # the hook was removed
