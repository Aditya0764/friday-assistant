"""Debug aid (P6-04): save the audio of each wake / follow-up / key command as a WAV file.

Off unless the environment variable FRIDAY_SAVE_CLIPS=1. Files go to data\\clips\\ (git-ignored).
The clips contain whatever the mic heard, so delete them when you are done.
"""

from __future__ import annotations

import os
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

CLIPS_FLAG = "FRIDAY_SAVE_CLIPS"
CLIPS_DIR = Path("data") / "clips"
SAMPLE_RATE = 16000


def clips_enabled() -> bool:
    return os.environ.get(CLIPS_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def save_clip(
    audio: np.ndarray,
    source: str,
    folder: Path = CLIPS_DIR,
    now: datetime | None = None,
) -> Path:
    """Write int16 mono 16 kHz audio to folder/YYYYMMDD-HHMMSS_<source>.wav and return the path."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    path = folder / f"{stamp}_{source}.wav"
    count = 1
    while path.exists():  # two clips in the same second
        path = folder / f"{stamp}_{source}_{count}.wav"
        count += 1
    pcm = np.ascontiguousarray(audio, dtype="<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())
    return path