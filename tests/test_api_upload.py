"""Tests for /documents and /voice. Fake embedder and fake Whisper: no models, no network."""

import io
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from friday.api.app import create_app


def fake_embed(texts):
    return np.ones((len(texts), 4), dtype=np.float32)


def make_wav(seconds: float = 1.0) -> bytes:
    rate = 16000
    t = np.arange(int(rate * seconds)) / rate
    samples = (np.sin(2 * np.pi * 440 * t) * 8000).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


@pytest.fixture
def make_client(tmp_path):
    def build(transcribe=None):
        api = create_app(db_path=tmp_path / "t.db", embed_fn=fake_embed, transcribe=transcribe)
        return TestClient(api)

    return build


def upload(client, name, data, kind="text/plain"):
    return client.post("/documents", files={"file": (name, data, kind)})


def test_upload_text_document(make_client):
    client = make_client()
    r = upload(client, "notes.txt", b"Friday is a voice assistant. " * 20)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "notes.txt"
    assert body["chunks"] >= 1


def test_upload_same_name_twice_is_rejected(make_client):
    client = make_client()
    assert upload(client, "a.txt", b"hello there friend").status_code == 200
    assert upload(client, "a.txt", b"hello there friend").status_code == 400


def test_upload_unsupported_type_is_rejected(make_client):
    r = upload(make_client(), "pic.xyz", b"not a document")
    assert r.status_code == 400


def test_upload_empty_file_is_rejected(make_client):
    assert upload(make_client(), "empty.txt", b"").status_code == 400


def test_upload_folder_in_name_is_dropped(make_client):
    r = upload(make_client(), "../../evil.txt", b"some harmless text here")
    assert r.status_code == 200
    assert r.json()["name"] == "evil.txt"


def test_voice_returns_heard_text_and_reply(make_client):
    client = make_client(transcribe=lambda audio: "echo hello friday")
    r = client.post("/voice", files={"file": ("a.wav", make_wav(), "audio/wav")})
    assert r.status_code == 200
    body = r.json()
    assert body["heard"] == "echo hello friday"
    assert body["via"] == "rule"
    assert body["reply"]


def test_voice_gets_decoded_float_audio(make_client):
    seen = {}

    def transcribe(audio):
        seen["dtype"] = audio.dtype
        seen["seconds"] = len(audio) / 16000
        return "echo hi"

    client = make_client(transcribe=transcribe)
    client.post("/voice", files={"file": ("a.wav", make_wav(1.0), "audio/wav")})
    assert seen["dtype"] == np.float32
    assert 0.9 < seen["seconds"] < 1.1


def test_voice_garbage_audio_is_rejected(make_client):
    client = make_client(transcribe=lambda audio: "x")
    r = client.post("/voice", files={"file": ("a.wav", b"this is not audio", "audio/wav")})
    assert r.status_code == 400


def test_voice_silence_is_rejected(make_client):
    client = make_client(transcribe=lambda audio: "   ")
    r = client.post("/voice", files={"file": ("a.wav", make_wav(), "audio/wav")})
    assert r.status_code == 422


def test_voice_transcriber_crash_hides_details(make_client):
    def boom(audio):
        raise RuntimeError("secret internal path C:\\x")

    client = make_client(transcribe=boom)
    r = client.post("/voice", files={"file": ("a.wav", make_wav(), "audio/wav")})
    assert r.status_code == 502
    assert "secret" not in r.text