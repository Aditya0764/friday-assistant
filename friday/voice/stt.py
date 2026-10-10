"""Speech to text with faster-whisper.

The model loads once (in SpeechToText.__init__); transcribe() is then fast.
Run `python -m friday.voice.stt` to record 5 s from the mic and test it.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000  # Whisper expects 16 kHz mono
DEFAULT_MODEL = "base.en"  # tiny.en is the faster fallback


@dataclass(frozen=True)
class STTResult:
    text: str
    model: str
    ms: int


class SpeechToText:
    """Holds one loaded Whisper model. Create it once at startup."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        from faster_whisper import WhisperModel

        start = time.perf_counter()
        self.model_name = model_name
        self._model = WhisperModel(model_name, device="cpu", compute_type="int8")
        self.load_ms = int((time.perf_counter() - start) * 1000)

    def transcribe(self, audio: str | Path | np.ndarray) -> STTResult:
        """audio: a wav file path, or a mono float32 array at 16 kHz."""
        if isinstance(audio, np.ndarray):
            audio = np.ascontiguousarray(audio, dtype=np.float32)
        else:
            audio = str(audio)

        start = time.perf_counter()
        segments, _info = self._model.transcribe(audio, language="en")
        text = " ".join(seg.text.strip() for seg in segments).strip()
        ms = int((time.perf_counter() - start) * 1000)
        return STTResult(text=text, model=self.model_name, ms=ms)


_stt: SpeechToText | None = None


def get_stt(model_name: str = DEFAULT_MODEL) -> SpeechToText:
    """Return the shared instance, loading the model only on the first call."""
    global _stt
    if _stt is None or _stt.model_name != model_name:
        _stt = SpeechToText(model_name)
    return _stt


def _record(seconds: int = 5) -> np.ndarray:
    import sounddevice as sd

    print(f"Recording {seconds} s... speak now.")
    rec = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return rec[:, 0]


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    stt = get_stt(model)
    print(f"Model {stt.model_name} loaded in {stt.load_ms} ms")

    clip = _record(5)
    first = stt.transcribe(clip)
    print(f"Run 1: {first.ms} ms -> {first.text!r}")

    # Same clip again, same loaded model: proves the load happens only once.
    second = get_stt(model).transcribe(clip)
    print(f"Run 2: {second.ms} ms -> {second.text!r}")