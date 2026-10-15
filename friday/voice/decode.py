"""Decode an audio file (such as a Telegram OGG/Opus voice note) to 16 kHz mono float32.

faster-whisper can open files itself, but its decoder passes an option that PyAV 19 no
longer accepts (TypeError: open() got an unexpected keyword argument 'metadata_errors').
So we decode here with PyAV and hand Whisper an array, the same way the voice loop does.
"""

from __future__ import annotations

from pathlib import Path

import av
import numpy as np

SAMPLE_RATE = 16000  # Whisper expects 16 kHz mono


def decode_audio_file(path: str | Path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Return the audio as a mono float32 array at `sample_rate`, values in -1..1."""
    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=sample_rate)
    chunks: list[np.ndarray] = []
    with av.open(str(path)) as container:
        if not container.streams.audio:
            raise ValueError("This file has no audio.")
        for frame in container.decode(audio=0):
            chunks.extend(out.to_ndarray().reshape(-1) for out in resampler.resample(frame))
        chunks.extend(out.to_ndarray().reshape(-1) for out in resampler.resample(None))
    if not chunks:
        raise ValueError("No audio could be decoded from this file.")
    return np.concatenate(chunks).astype(np.float32) / 32768.0