"""Text to speech with Piper (en_US-amy-medium).

The voice loads once (in TextToSpeech.__init__). speak() synthesizes in a
background thread and plays each sentence as soon as it is ready, so audio
starts after the first sentence instead of after the whole text.
synthesize_wav() returns the same speech as WAV bytes and plays nothing (used by the web API).
Run `python -m friday.voice.tts` to test it.
"""

from __future__ import annotations

import io
import queue
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "en_US-amy-medium.onnx"


@dataclass(frozen=True)
class TTSResult:
    sentences: int
    first_audio_ms: int  # start of speak() until the first sentence is ready to play
    total_ms: int  # start of speak() until the last sample has played


class TextToSpeech:
    """Holds one loaded Piper voice. Create it once at startup."""

    def __init__(self, model_path: str | Path = MODEL_PATH) -> None:
        from piper import PiperVoice

        start = time.perf_counter()
        self._voice = PiperVoice.load(str(model_path))
        self.load_ms = int((time.perf_counter() - start) * 1000)

        # Warm-up: the first synthesize() call is slow, so pay that cost now.
        start = time.perf_counter()
        for _ in self._voice.synthesize("Ready."):
            pass
        self.warmup_ms = int((time.perf_counter() - start) * 1000)

    def synthesize_wav(self, text: str) -> bytes:
        """Return the spoken text as a WAV file (bytes). Plays nothing, so it is safe for the web."""
        pieces: list[np.ndarray] = []
        rate = 0
        for chunk in self._voice.synthesize(text):
            rate = chunk.sample_rate
            pieces.append(np.ascontiguousarray(chunk.audio_int16_array, dtype=np.int16).reshape(-1))
        if not pieces:
            raise ValueError("Nothing to say.")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(np.concatenate(pieces).tobytes())
        return buffer.getvalue()

    def speak(self, text: str) -> TTSResult:
        """Speak text through the default output, sentence by sentence."""
        import sounddevice as sd

        start = time.perf_counter()
        chunks: queue.Queue[tuple[int, np.ndarray] | None] = queue.Queue(maxsize=4)
        errors: list[Exception] = []

        def produce() -> None:
            try:
                for chunk in self._voice.synthesize(text):
                    chunks.put((chunk.sample_rate, chunk.audio_int16_array))
            except Exception as exc:  # noqa: BLE001 - re-raised in the main thread below
                errors.append(exc)
            finally:
                chunks.put(None)

        worker = threading.Thread(target=produce, daemon=True)
        worker.start()

        stream = None
        first_ms = 0
        count = 0
        try:
            while True:
                item = chunks.get()
                if item is None:
                    break
                rate, audio = item
                if stream is None:
                    first_ms = int((time.perf_counter() - start) * 1000)
                    # latency="high" = bigger device buffer, to test against Bluetooth crackle
                    stream = sd.OutputStream(
                        samplerate=rate, channels=1, dtype="int16", latency="high"
                    )
                    stream.start()
                data = np.ascontiguousarray(audio, dtype=np.int16).reshape(-1, 1)
                stream.write(data)
                count += 1
        finally:
            if stream is not None:
                stream.stop()  # waits for queued audio to finish playing
                stream.close()
        worker.join()

        if errors:
            raise errors[0]
        total_ms = int((time.perf_counter() - start) * 1000)
        return TTSResult(sentences=count, first_audio_ms=first_ms, total_ms=total_ms)


_tts: TextToSpeech | None = None


def get_tts() -> TextToSpeech:
    """Return the shared instance, loading the voice only on the first call."""
    global _tts
    if _tts is None:
        _tts = TextToSpeech()
    return _tts


if __name__ == "__main__":
    tts = get_tts()
    print(f"Voice loaded in {tts.load_ms} ms, warm-up {tts.warmup_ms} ms")

    long_text = (
        "Hello Aditya. You have two urgent emails. "
        "One reminder is due at four o'clock. "
        "The weather looks fine, so a walk later could be a good idea. "
        "That is all for now."
    )
    for run in (1, 2):
        result = get_tts().speak(long_text)
        print(
            f"Run {run}: {result.sentences} sentences, "
            f"first audio {result.first_audio_ms} ms, total {result.total_ms} ms"
        )