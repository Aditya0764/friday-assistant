import wave
from datetime import datetime

import numpy as np

from friday.voice.clips import CLIPS_FLAG, clips_enabled, save_clip

NOW = datetime(2026, 10, 17, 1, 30, 5)


def test_a_saved_clip_reads_back_exactly(tmp_path):
    audio = np.arange(-50, 50, dtype=np.int16)
    path = save_clip(audio, "wake", tmp_path, now=NOW)
    assert path.name == "20261017-013005_wake.wav"
    with wave.open(str(path), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
        data = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    assert np.array_equal(data, audio)


def test_two_clips_in_the_same_second_do_not_overwrite(tmp_path):
    first = save_clip(np.zeros(10, dtype=np.int16), "wake", tmp_path, now=NOW)
    second = save_clip(np.zeros(10, dtype=np.int16), "wake", tmp_path, now=NOW)
    assert first != second and second.name == "20261017-013005_wake_1.wav"


def test_the_switch_is_off_unless_set(monkeypatch):
    monkeypatch.delenv(CLIPS_FLAG, raising=False)
    assert not clips_enabled()
    monkeypatch.setenv(CLIPS_FLAG, "1")
    assert clips_enabled()