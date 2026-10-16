"""Wake word detector: openWakeWord running ww_B ("hey friday").

Settings are exactly the ones the evaluation used, so its numbers apply: raw 16 kHz int16
chunks of 1280 samples (80 ms), no smoothing, NO VAD, threshold 0.9, and a 2 s cooldown
(25 chunks). An event fires when a chunk's score is >= the threshold and the previous chunk
that crossed it was MORE than 25 chunks earlier; every crossing restarts the cooldown, so
continuous noise above the threshold counts as one event.

Status: ww_B at 0.9 is a CANDIDATE (about 0.43 false accepts per hour, 3 events in 7 h, the
threshold chosen after seeing that recording). It is not confirmed.

Needs: pip install openwakeword==0.6.0, plus melspectrogram.onnx and embedding_model.onnx in
openwakeword/resources/models (copied from the ww-eval venv).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "wakeword" / "variants" / "ww_B.onnx"
SAMPLE_RATE = 16000
CHUNK = 1280  # samples per model step (80 ms)
THRESHOLD = 0.9
COOLDOWN_CHUNKS = 25  # 2.0 s


class WakeWordDetector:
    def __init__(
        self,
        model_path: str | Path = MODEL_PATH,
        threshold: float = THRESHOLD,
        cooldown_chunks: int = COOLDOWN_CHUNKS,
        model=None,
    ) -> None:
        if model is None:
            from openwakeword.model import Model

            model = Model(wakeword_models=[str(model_path)], inference_framework="onnx")
        self._model = model
        self.threshold = threshold
        self.cooldown = cooldown_chunks
        self._n = 0
        self._last_cross = -(10**9)

    def reset(self) -> None:
        """Forget audio history and the cooldown (call before a new, unrelated stretch of audio)."""
        self._model.reset()
        self._n = 0
        self._last_cross = -(10**9)

    def feed(self, chunk: np.ndarray) -> tuple[float, bool]:
        """Score one chunk. Returns (score, fired)."""
        if chunk.dtype != np.int16 or chunk.shape != (CHUNK,):
            raise ValueError(f"need {CHUNK} int16 samples, got {chunk.dtype} {chunk.shape}")
        scores = self._model.predict(chunk)
        score = float(max(scores.values())) if scores else 0.0
        self._n += 1
        fired = False
        if score >= self.threshold:
            fired = (self._n - self._last_cross) > self.cooldown
            self._last_cross = self._n
        return score, fired