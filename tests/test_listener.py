import numpy as np

from friday.voice.listener import FOLLOW_UP_CHUNKS, PREROLL_CHUNKS, TAIL_CHUNKS, Listener

CHUNK = 1280
WAKE, LOUD, QUIET, SCORED = 777, 6000, 0, 555


def _c(value, n=1):
    return [np.full(CHUNK, value, dtype=np.int16) for _ in range(n)]


class FakeMic:
    """Plays a fixed list of chunks, then returns None. flush() does nothing here."""

    def __init__(self, chunks):
        self.chunks = list(chunks)

    def read(self, timeout=1.0):
        return self.chunks.pop(0) if self.chunks else None

    def flush(self):
        return 0

    @property
    def empty(self):
        return not self.chunks


class FakeDetector:
    def __init__(self):
        self.fed = 0

    def feed(self, chunk):
        self.fed += 1
        value = int(chunk[0])
        return (0.5 if value == SCORED else 0.0), value == WAKE

    def reset(self):
        pass


class CooldownDetector:
    """Like the real one: a wake inside the cooldown (counted in FED chunks) is ignored."""

    def __init__(self):
        self.reset()

    def feed(self, chunk):
        self._n += 1
        crossed = int(chunk[0]) == WAKE
        fired = crossed and (self._n - self._last) > 25
        if crossed:
            self._last = self._n
        return 0.0, fired

    def reset(self):
        self._n = 0
        self._last = -10_000


class Clock:
    def __init__(self):
        self.t = -20.0

    def __call__(self):
        self.t += 20.0
        return self.t


def _run(chunks, speaking=(), keys=(), fail_first=False, rows=None, clock=None, detector=None):
    mic, calls, prerolls = FakeMic(chunks), [], []
    detector = detector or FakeDetector()
    speaking, keys = list(speaking), list(keys)

    def on_audio(audio, source, preroll_s):
        calls.append((source, len(audio) // CHUNK))
        prerolls.append(preroll_s)
        if fail_first and len(calls) == 1:
            raise RuntimeError("boom")
        return True

    extra = {"clock": clock} if clock else {}
    listener = Listener(
        mic,
        detector,
        on_audio,
        is_speaking=lambda: speaking.pop(0) if speaking else False,
        key_down=lambda: keys.pop(0) if keys else False,
        wake_log=rows.append if rows is not None else None,
        **extra,
    )
    listener.prerolls = prerolls  # what each on_audio call was told about the pre-roll
    listener.run(should_stop=lambda: mic.empty)
    return listener, calls, detector


def test_wake_then_command_then_quiet_runs_one_turn():
    chunks = _c(QUIET, 3) + _c(WAKE) + _c(LOUD, 5) + _c(QUIET, 12)
    listener, calls, _ = _run(chunks)
    assert calls == [("wake", 4 + 17)]  # 4 pre-roll chunks + the command
    assert listener.wake_events == 1


def test_the_real_preroll_length_goes_to_the_wake_turn_and_none_to_the_follow_up():
    chunks = (
        _c(QUIET, 3) + _c(WAKE) + _c(LOUD, 3) + _c(QUIET, 12)  # 3 quiet + the firing chunk = 4
        + _c(QUIET, TAIL_CHUNKS)
        + _c(LOUD, 3) + _c(QUIET, 12)
    )
    listener, calls, _ = _run(chunks)
    assert [c[0] for c in calls] == ["wake", "follow_up"]
    assert listener.prerolls == [4 * 0.08, None]  # shorter than full: the real length, not 1.52


def test_follow_up_without_the_wake_word():
    chunks = (
        _c(WAKE) + _c(LOUD, 3) + _c(QUIET, 12)
        + _c(QUIET, TAIL_CHUNKS)
        + _c(LOUD, 3) + _c(QUIET, 12)
    )
    _, calls, _ = _run(chunks)
    assert calls == [("wake", 1 + 15), ("follow_up", 15)]


def test_follow_up_window_closes_after_six_seconds():
    chunks = _c(WAKE) + _c(LOUD, 3) + _c(QUIET, 12) + _c(QUIET, TAIL_CHUNKS + FOLLOW_UP_CHUNKS)
    _, calls, _ = _run(chunks)
    assert calls == [("wake", 1 + 15)]


def test_wake_word_but_nobody_speaks_runs_no_turn():
    _, calls, _ = _run(_c(WAKE) + _c(QUIET, 50))
    assert calls == []


def test_a_wake_right_after_a_silent_wake_is_not_blocked_by_the_cooldown():
    chunks = _c(WAKE) + _c(QUIET, 50) + _c(WAKE) + _c(LOUD, 3) + _c(QUIET, 12)
    _, calls, _ = _run(chunks, detector=CooldownDetector())
    assert calls == [("wake", 1 + 15)]


def test_push_to_talk_records_while_the_key_is_down():
    listener, calls, _ = _run(_c(LOUD, 3), keys=[True, True, True, False])
    assert calls == [("key", 3)]
    assert listener.wake_events == 0


def test_nothing_is_heard_while_friday_speaks():
    _, calls, detector = _run(_c(WAKE) + _c(LOUD), speaking=[True, True])
    assert calls == [] and detector.fed == 0


def test_a_short_tail_after_speech_is_also_ignored():
    chunks = _c(QUIET) + _c(WAKE, TAIL_CHUNKS) + _c(QUIET, 2)
    _, calls, detector = _run(chunks, speaking=[True])
    assert calls == [] and detector.fed == 2


def test_a_failing_turn_does_not_stop_the_listener():
    one = _c(WAKE) + _c(LOUD, 3) + _c(QUIET, 12)
    _, calls, _ = _run(one + _c(QUIET, TAIL_CHUNKS) + one, fail_first=True)
    assert [c[0] for c in calls] == ["wake", "wake"]


def test_scores_and_wakes_are_logged():
    rows = []
    chunks = _c(QUIET) + _c(SCORED) + _c(WAKE) + _c(LOUD, 3) + _c(QUIET, 12)
    _run(chunks, rows=rows)
    assert [r.split(",")[1] for r in rows] == ["score", "wake"]
    assert rows[0].split(",")[2] == "0.50"


def test_heartbeat_rows_count_listened_chunks():
    rows = []
    _run(_c(QUIET, 7), rows=rows, clock=Clock())
    beats = [r.split(",") for r in rows if ",beat," in r]
    assert len(beats) == 2 and beats[0][3] == "3"


def test_preroll_is_capped():
    chunks = _c(QUIET, 30) + _c(WAKE) + _c(LOUD, 3) + _c(QUIET, 12)
    _, calls, _ = _run(chunks)
    assert calls == [("wake", PREROLL_CHUNKS + 15)]


def test_a_pause_after_the_wake_phrase_does_not_end_the_command():
    # "hey friday" (loud, in the pre-roll), a 14-chunk pause, then the command.
    chunks = _c(QUIET, 10) + _c(LOUD, 5) + _c(WAKE) + _c(QUIET, 14) + _c(LOUD, 3) + _c(QUIET, 12)
    _, calls, _ = _run(chunks)
    assert calls == [("wake", 16 + 29)]