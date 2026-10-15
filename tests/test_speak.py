"""Tests for /speak and TextToSpeech.synthesize_wav. A fake voice stands in for Piper:
no model is loaded and nothing plays."""

import io
import wave
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from friday.api.app import create_app
from friday.voice.tts import TextToSpeech


class FakeTTS(TextToSpeech):
    def __init__(self, voice) -> None:
        self._voice = voice


def fake_voice(*chunk_sizes):
    chunks = [
        SimpleNamespace(sample_rate=22050, audio_int16_array=np.ones(n, dtype=np.int16))
        for n in chunk_sizes
    ]
    return SimpleNamespace(synthesize=lambda text: iter(chunks))


def make_client(tmp_path, speak):
    return TestClient(create_app(db_path=tmp_path / "t.db", speak=speak))


def test_speak_returns_a_wav(tmp_path):
    client = make_client(tmp_path, lambda text: b"RIFFfake")
    r = client.post("/speak", json={"text": "Hello there"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content == b"RIFFfake"


def test_speak_trims_the_text(tmp_path):
    seen = []

    def speak(text):
        seen.append(text)
        return b"x"

    make_client(tmp_path, speak).post("/speak", json={"text": "  hi there  "})
    assert seen == ["hi there"]


def test_speak_blank_text_is_rejected(tmp_path):
    client = make_client(tmp_path, lambda text: b"x")
    assert client.post("/speak", json={"text": "   "}).status_code == 422
    assert client.post("/speak", json={"text": ""}).status_code == 422


def test_speak_too_long_is_rejected(tmp_path):
    client = make_client(tmp_path, lambda text: b"x")
    assert client.post("/speak", json={"text": "a" * 3001}).status_code == 422


def test_speak_nothing_to_say_is_422(tmp_path):
    def speak(text):
        raise ValueError("Nothing to say.")

    r = make_client(tmp_path, speak).post("/speak", json={"text": "..."})
    assert r.status_code == 422


def test_speak_crash_hides_details(tmp_path):
    def speak(text):
        raise RuntimeError("secret model path C:\\x")

    r = make_client(tmp_path, speak).post("/speak", json={"text": "hello"})
    assert r.status_code == 502
    assert "secret" not in r.text


def test_synthesize_wav_joins_the_sentences():
    tts = FakeTTS(fake_voice(100, 50))
    data = tts.synthesize_wav("Hello. Bye.")
    with wave.open(io.BytesIO(data)) as wav:
        assert wav.getframerate() == 22050
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getnframes() == 150


def test_synthesize_wav_with_nothing_raises():
    tts = FakeTTS(fake_voice())
    with pytest.raises(ValueError):
        tts.synthesize_wav("...")