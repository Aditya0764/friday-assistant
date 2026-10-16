"""One always-open microphone stream (P6-04, option A): the wake word and push-to-talk share it.

The stream delivers 16 kHz mono int16 audio in chunks of exactly CHUNK (1280) samples, the size
the wake-word model expects. One reader at a time takes chunks with read(). A reader that stops
reading just falls behind: when more than MAX_QUEUED_CHUNKS are waiting, the oldest chunk is
dropped and counted in `dropped`. The microphone stays open (the Windows mic indicator stays on)
as long as the hub is started.
"""

from __future__ import annotations

import queue
from collections.abc import Callable
from typing import Self

import numpy as np

SAMPLE_RATE = 16000
CHUNK = 1280  # 80 ms
MAX_QUEUED_CHUNKS = 250  # 20 s


class MicHub:
    def __init__(
        self, device: int | str | None = None, stream_factory: Callable | None = None
    ) -> None:
        self._device = device
        self._factory = stream_factory or self._sounddevice_stream
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=MAX_QUEUED_CHUNKS)
        self._pending = np.zeros(0, dtype=np.int16)
        self._stream = None
        self.dropped = 0  # chunks thrown away because nobody was reading
        self.overflows = 0  # times the sound card reported lost or late audio

    def _sounddevice_stream(self, callback):
        import sounddevice as sd

        return sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK,
            device=self._device,
            callback=callback,
        )

    def start(self) -> None:
        if self._stream is None:
            self._stream = self._factory(self._on_audio)
            self._stream.start()

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()

    def _on_audio(self, indata, _frames, _time_info, status) -> None:
        if status:
            self.overflows += 1
        data = np.concatenate([self._pending, indata[:, 0].astype(np.int16, copy=False)])
        whole = len(data) // CHUNK
        for i in range(whole):
            self._put(data[i * CHUNK : (i + 1) * CHUNK].copy())
        self._pending = data[whole * CHUNK :].copy()

    def _put(self, chunk: np.ndarray) -> None:
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self.dropped += 1
            try:
                self._queue.put_nowait(chunk)
            except queue.Full:
                self.dropped += 1

    def read(self, timeout: float = 1.0) -> np.ndarray | None:
        """The next CHUNK of audio, or None if none arrived within `timeout` seconds."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush(self) -> int:
        """Throw away everything waiting. Returns how many chunks were dropped."""
        count = 0
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return count
            count += 1