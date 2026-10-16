"""Deciding when a spoken command is over, from how loud each 80 ms chunk is (P6-04).

The speech threshold is relative to the room's noise floor, measured while Friday is just
listening. SPEECH_OVER_FLOOR, MIN_SPEECH_RMS and the window lengths are STARTING GUESSES, not
tuned: wake_test.py prints the numbers so they can be set from your own room and mic.
"""

from __future__ import annotations

from collections import deque

import numpy as np

CHUNK_SECONDS = 0.08
MIN_SPEECH_RMS = 0.01
SPEECH_OVER_FLOOR = 3.0
SILENCE_CHUNKS = 12  # about 1 s of quiet after speech ends the command
NO_SPEECH_CHUNKS = 50  # about 4 s without any speech: give up
MAX_CHUNKS = 100  # about 8 s: a command never runs longer than this


def rms(chunk: np.ndarray) -> float:
    """Loudness of an int16 chunk, 0.0 (silent) to 1.0 (full scale)."""
    samples = chunk.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(samples * samples)))


class NoiseFloor:
    """The quiet level of the room: a low percentile of the recent chunk loudness."""

    def __init__(self, window: int = 60) -> None:
        self._values: deque[float] = deque(maxlen=window)

    def add(self, level: float) -> None:
        self._values.append(level)

    @property
    def level(self) -> float:
        return float(np.percentile(list(self._values), 20)) if self._values else 0.0


def speech_threshold(floor: float) -> float:
    return max(MIN_SPEECH_RMS, floor * SPEECH_OVER_FLOOR)


class Endpointer:
    """Feed it chunks after the wake word. update() returns None while the command goes on,
    then one of: "done" (speech, then quiet), "no_speech" (nothing said) or "max" (too long)."""

    def __init__(
        self,
        speech_rms: float,
        silence_chunks: int = SILENCE_CHUNKS,
        no_speech_chunks: int = NO_SPEECH_CHUNKS,
        max_chunks: int = MAX_CHUNKS,
    ) -> None:
        self.speech_rms = speech_rms
        self._silence = silence_chunks
        self._no_speech = no_speech_chunks
        self._max = max_chunks
        self.chunks = 0
        self._heard = False
        self._quiet = 0

    def update(self, chunk: np.ndarray) -> str | None:
        self.chunks += 1
        if rms(chunk) >= self.speech_rms:
            self._heard = True
            self._quiet = 0
        else:
            self._quiet += 1
        if self._heard and self._quiet >= self._silence:
            return "done"
        if not self._heard and self.chunks >= self._no_speech:
            return "no_speech"
        if self.chunks >= self._max:
            return "max"
        return None