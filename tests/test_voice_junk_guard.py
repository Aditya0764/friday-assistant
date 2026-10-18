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
    def __init__(self, text: str, words=None, ranges=None) -> None:
        self.text, self.calls, self.vads, self.word_flags = text, 0, [], []
        self.words, self.ranges = words, ranges

    def transcribe(self, audio, vad=False, words=False):
        self.calls += 1
        self.vads.append(vad)
        self.word_flags.append(words)
        extra = {}
        if self.ranges:
            extra = {"no_speech_range": self.ranges[0], "avg_logprob_range": self.ranges[1]}
        return STTResult(
            text=self.text, model="fake", ms=1, words=self.words if words else None, **extra
        )


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


def run(conn, audio, text, source="key", preroll_s=None, words=None, ranges=None):
    stt, tts, app = FakeSTT(text, words, ranges), FakeTTS(), FakeApp()
    seconds = len(audio) / SR
    peak = float(np.abs(audio).max()) if len(audio) else 0.0
    handled = loop.process_capture(
        conn, app, stt, tts, audio, seconds, peak, source=source, preroll_s=preroll_s
    )
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


# ---- wake turns: cut by time (preroll_s), regex only as the fallback ----

HEARD = (
    (" Hey", 0.1, 0.4), (" Freddy,", 0.4, 0.9), (" play", 1.05, 1.3), (" Blinding", 1.3, 1.7),
    (" Lights", 1.7, 2.1),
)
HEARD_TEXT = "Hey Freddy, play Blinding Lights"


def test_wake_turn_cuts_words_before_the_wake_point(conn):
    handled, stt, _, app = run(conn, speech(0.8), HEARD_TEXT, "wake", 0.8, HEARD)
    assert handled and app.texts == ["play Blinding Lights"]
    assert stt.word_flags == [True] and stt.vads == [True]


def test_wake_turn_cut_does_not_run_the_regex_on_a_real_leading_friday(conn):
    words = ((" Hey", 0.1, 0.4), (" Friday", 0.4, 0.9), (" Friday", 1.1, 1.5), (" the", 1.5, 1.6),
             (" 13th", 1.6, 2.0), (" is", 2.0, 2.1), (" a", 2.1, 2.2), (" movie", 2.2, 2.6))
    _, _, _, app = run(conn, speech(0.8), "Hey Friday Friday the 13th is a movie", "wake", 0.8, words)
    assert app.texts == ["Friday the 13th is a movie"]


def test_wake_turn_without_word_times_falls_back_to_the_regex(conn):
    _, _, _, app = run(conn, speech(0.8), "Hey Friday, what time is it?", "wake", 0.8, None)
    assert app.texts == ["what time is it?"]


def test_wake_turn_with_an_empty_cut_falls_back_to_the_regex(conn):
    words = ((" Hey", 0.1, 0.4), (" Friday,", 0.4, 0.7), (" stop", 0.7, 0.9))
    _, _, _, app = run(conn, speech(0.8), "Hey Friday, stop", "wake", 0.8, words)
    assert app.texts == ["stop"]  # the cut left nothing (all words end before 1.0 s)


def test_wake_turn_without_preroll_info_uses_the_old_path(conn):
    _, stt, _, app = run(conn, speech(0.8), "Hey Friday, what time is it?", "wake", None, HEARD)
    assert app.texts == ["what time is it?"] and stt.word_flags == [False]


@pytest.mark.parametrize("source", ["key", "follow_up"])
def test_key_and_follow_up_never_ask_for_words_or_use_the_cut(conn, source):
    handled, stt, _, app = run(conn, speech(0.8), "Hey Friday, play Blinding Lights", source,
                               0.8, HEARD)
    expected = "Hey Friday, play Blinding Lights" if source == "key" else "play Blinding Lights"
    assert handled and app.texts == [expected] and stt.word_flags == [False]


def test_stt_confidence_numbers_are_traced_and_never_drop_a_turn(conn):
    handled, _, _, _ = run(conn, speech(0.8), "what time is it", "key",
                           ranges=((0.021, 0.272), (-0.845, -0.3)))
    assert handled
    out = conn.execute("SELECT output FROM traces WHERE step = 'stt'").fetchone()["output"]
    assert out == ("what time is it [no_speech_prob min 0.021 max 0.272,"
                   " avg_logprob min -0.845 max -0.300]")
