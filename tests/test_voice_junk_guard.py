"""Junk-turn guard in process_capture: little speech or a Whisper phantom is dropped unsaved."""

import numpy as np
import pytest

from friday import db
from friday.voice import loop
from friday.voice.stt import STTResult

SR = 16000


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SR * seconds), dtype=np.float32)


def speech(seconds: float, level: float = 0.2) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return (level * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class FakeSTT:
    def __init__(self, text: str) -> None:
        self.text, self.calls, self.vads = text, 0, []

    def transcribe(self, audio, vad=False):
        self.calls += 1
        self.vads.append(vad)
        return STTResult(text=self.text, model="fake", ms=1)


class FakeTTS:
    def __init__(self) -> None:
        self.said = []

    def speak(self, text):
        self.said.append(text)
        return type("S", (), {"sentences": 1, "first_audio_ms": 1})()


class FakeApp:
    def __init__(self) -> None:
        self.texts = []

    def invoke(self, state):
        self.texts.append(state["text"])
        return {"reply": "ok", "via": "llm", "skill_name": "", "provider": "fake"}


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "t.db")


def run(conn, audio, text, source="key"):
    stt, tts, app = FakeSTT(text), FakeTTS(), FakeApp()
    seconds = len(audio) / SR
    peak = float(np.abs(audio).max()) if len(audio) else 0.0
    handled = loop.process_capture(conn, app, stt, tts, audio, seconds, peak, source=source)
    return handled, stt, tts, app


def saved(conn):
    return conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]


def test_loud_chunks_counts_80ms_pieces():
    assert loop.loud_chunks(silence(1.0)) == 0
    assert loop.loud_chunks(speech(0.4)) == 5  # 0.4 s = 5 chunks of 80 ms
    both = np.concatenate([silence(0.4), speech(0.4)])
    assert loop.loud_chunks(both) == 5


def test_a_clip_with_no_speech_never_reaches_stt_llm_memory_or_tts(conn):
    handled, stt, tts, app = run(conn, silence(0.6), "You")
    assert not handled and stt.calls == 0 and not app.texts and not tts.said
    assert saved(conn) == 0


def test_quiet_noise_below_the_speech_level_is_not_speech(conn):
    handled, stt, _, _ = run(conn, speech(0.6, level=0.005), "You")
    assert not handled and stt.calls == 0 and saved(conn) == 0


@pytest.mark.parametrize("text", ["You", "Thank you.", "... ... ...", "Thank you. Thank you. Thank you.",
                                  "Bye. Bye. Bye. Bye.", "Thanks for watching!"])
def test_known_phantom_with_little_speech_is_dropped_and_not_saved(conn, text):
    audio = np.concatenate([silence(0.5), speech(0.16)])  # 2 loud chunks: past the first gate
    handled, stt, tts, app = run(conn, audio, text)
    assert stt.calls == 1 and not handled
    assert not app.texts and not tts.said and saved(conn) == 0


def test_a_real_short_thank_you_still_works(conn):
    handled, _, tts, app = run(conn, speech(0.8), "Thank you.")  # 10 loud chunks
    assert handled and app.texts == ["Thank you."] and tts.said == ["ok"]
    assert saved(conn) == 2  # the user message and the reply


def test_a_phantom_phrase_is_not_dropped_for_other_text_with_little_speech(conn):
    handled, _, _, app = run(conn, speech(0.3), "what time is it")
    assert handled and app.texts == ["what time is it"]


def test_stt_is_always_called_with_vad_on_including_the_key_path(conn):
    for source in ("key", "wake", "follow_up"):
        _, stt, _, _ = run(conn, speech(0.8), "what time is it", source)
        assert stt.vads == [True]


def test_short_taps_are_still_too_short(conn):
    handled, stt, _, _ = run(conn, speech(0.2), "hello")
    assert not handled and stt.calls == 0


@pytest.mark.parametrize("text,expected", [
    ("You", True), ("you.", True), ("Thank you.", True), ("...", True), ("", True),
    ("Thank you. Thank you.", True), ("Bye bye", True), ("Bye. Bye. Bye.", True),
    ("Thank you for the reminder", False), ("What time is it?", False),
    ("You are Friday", False), ("I'm David. Thank you. Thank you.", False),
])
def test_is_known_hallucination(text, expected):
    assert loop.is_known_hallucination(text) is expected


def test_dropped_turns_are_traced_with_the_reason(conn):
    run(conn, silence(0.6), "You")
    rows = conn.execute("SELECT step, output FROM traces ORDER BY id").fetchall()
    assert [r["step"] for r in rows] == ["record", "dropped"]
    assert "loud 0" in rows[0]["output"] and "not enough speech" in rows[1]["output"]
