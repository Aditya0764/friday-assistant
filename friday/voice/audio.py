"""Mic capture with a hold-to-talk key.

record_while_held() waits for the key, records while it is held, and returns
mono float32 audio at 16 kHz (what STT expects).
Run `python -m friday.voice.audio` to test: hold the key, speak, release.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000
DEFAULT_KEY = "right ctrl"  # change this if you prefer another key, e.g. "f9"
POLL_SECONDS = 0.01


@dataclass(frozen=True)
class Capture:
    audio: np.ndarray  # mono float32, 16 kHz
    seconds: float
    peak: float  # loudest sample, 0.0 to 1.0 (near 1.0 = clipping, near 0 = silent)


def record_while_held(key: str = DEFAULT_KEY, device: int | str | None = None) -> Capture:
    """Block until `key` is pressed, record until it is released, return the audio."""
    import keyboard
    import sounddevice as sd

    blocks: list[np.ndarray] = []
    recording = threading.Event()

    def on_audio(indata, _frame_count, _time_info, _status) -> None:
        if recording.is_set():
            blocks.append(indata[:, 0].copy())

    # The stream is already running while we wait, so the first syllable is not clipped.
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=device,
        callback=on_audio,
    ):
        while not keyboard.is_pressed(key):
            time.sleep(POLL_SECONDS)
        recording.set()
        while keyboard.is_pressed(key):
            time.sleep(POLL_SECONDS)
        recording.clear()

    if not blocks:
        return Capture(audio=np.zeros(0, dtype=np.float32), seconds=0.0, peak=0.0)

    audio = np.concatenate(blocks)
    return Capture(
        audio=audio,
        seconds=len(audio) / SAMPLE_RATE,
        peak=float(np.abs(audio).max()),
    )


if __name__ == "__main__":
    from friday.voice.stt import get_stt

    stt = get_stt()
    print(f"STT ready. Hold [{DEFAULT_KEY}], speak, release. Ctrl+C to quit.")
    for round_no in range(1, 4):
        print(f"\nRound {round_no}: waiting for key...")
        cap = record_while_held()
        print(f"Captured {cap.seconds:.1f} s, peak level {cap.peak:.2f}")
        if cap.seconds < 0.3:
            print("Too short, ignored.")
            continue
        result = stt.transcribe(cap.audio)
        print(f"STT {result.ms} ms -> {result.text!r}")