import av
import numpy as np
import pytest

from friday.voice.decode import SAMPLE_RATE, decode_audio_file

OPUS_RATE = 48000  # Opus works at 48 kHz internally, like Telegram voice notes


def make_opus(path, seconds=1.0, hz=440):
    """Write a short OGG/Opus tone, the same container and codec Telegram uses."""
    if "libopus" not in av.codecs_available:
        pytest.skip("this PyAV build has no Opus encoder")
    t = np.arange(int(OPUS_RATE * seconds)) / OPUS_RATE
    samples = (0.3 * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    out = av.open(str(path), "w", format="ogg")
    stream = out.add_stream("libopus", rate=OPUS_RATE)
    stream.layout = "mono"
    for i in range(0, len(samples) - 960, 960):
        chunk = samples[i : i + 960].reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(chunk, format="flt", layout="mono")
        frame.sample_rate = OPUS_RATE
        frame.pts = i
        for packet in stream.encode(frame):
            out.mux(packet)
    for packet in stream.encode(None):
        out.mux(packet)
    out.close()


def test_opus_voice_note_decodes_to_16khz_mono_float32(tmp_path):
    path = tmp_path / "note.oga"
    make_opus(path, seconds=1.0)
    audio = decode_audio_file(path)
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert abs(len(audio) / SAMPLE_RATE - 1.0) < 0.1
    assert 0.2 < float(np.abs(audio).max()) < 0.4  # the tone was written at 0.3


def test_decoded_audio_keeps_the_pitch(tmp_path):
    path = tmp_path / "note.oga"
    make_opus(path, seconds=1.0, hz=440)
    audio = decode_audio_file(path)
    spectrum = np.abs(np.fft.rfft(audio))
    pitch = np.fft.rfftfreq(len(audio), 1 / SAMPLE_RATE)[spectrum.argmax()]
    assert abs(pitch - 440) < 10


def test_a_file_that_is_not_audio_raises_value_error(tmp_path):
    path = tmp_path / "bad.oga"
    path.write_bytes(b"this is not audio")
    with pytest.raises(ValueError):
        decode_audio_file(path)