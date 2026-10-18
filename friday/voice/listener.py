"""Always-on listening (P6-04): wake word and push-to-talk from one shared mic stream.

Idle: every chunk goes to the wake-word detector. When it fires, the command is recorded until
the speaker goes quiet (endpoint.py). The last PREROLL_CHUNKS of audio before the wake are kept
and put in front of the command, so the first word is not cut off. They are NOT used to decide
when the command ends. After Friday answers, a FOLLOW_UP_SECONDS window lets you speak again
without the wake word. Holding the push-to-talk key records while it is held.
Friday's own voice is never listened to: chunks are skipped while she speaks, plus a short tail.

All the timing numbers here are starting guesses, not measured.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from datetime import datetime

import numpy as np

from friday.voice.endpoint import CHUNK_SECONDS, Endpointer, NoiseFloor, rms, speech_threshold

FOLLOW_UP_SECONDS = 6.0
FOLLOW_UP_CHUNKS = round(FOLLOW_UP_SECONDS / CHUNK_SECONDS)  # 75
PREROLL_CHUNKS = round(1.5 / CHUNK_SECONDS)  # 19: about 1.5 s kept from before the wake fires
TAIL_CHUNKS = 6  # about 0.5 s ignored after Friday stops speaking
MAX_PTT_CHUNKS = 750  # a held key never records more than 60 s
LOG_MIN_SCORE = 0.2  # scores below this are not logged (the heartbeat still counts them)
BEAT_SECONDS = 60.0


class Listener:
    def __init__(
        self,
        mic,
        detector,
        on_audio: Callable[[np.ndarray, str, float | None], bool],
        is_speaking: Callable[[], bool],
        key_down: Callable[[], bool],
        wake_log: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.mic = mic
        self.detector = detector
        self.on_audio = on_audio  # (int16 audio, source, preroll_s) -> True if a reply was spoken
        self.is_speaking = is_speaking
        self.key_down = key_down
        self.wake_log = wake_log
        self.clock = clock
        self.floor = NoiseFloor()
        self.wake_events = 0
        self._preroll: deque[np.ndarray] = deque(maxlen=PREROLL_CHUNKS)
        self._beat_at = clock()
        self._beat_chunks = 0
        self._beat_max = 0.0

    # ---- logging -------------------------------------------------------------------------

    def _write(self, kind: str, score: float, chunks: int) -> None:
        if self.wake_log is None:
            return
        stamp = datetime.now().isoformat(timespec="seconds")
        self.wake_log(f"{stamp},{kind},{score:.2f},{chunks}")

    def _log_score(self, score: float, fired: bool) -> None:
        self._beat_chunks += 1
        self._beat_max = max(self._beat_max, score)
        if fired:
            self._write("wake", score, 1)
        elif score >= LOG_MIN_SCORE:
            self._write("score", score, 1)
        now = self.clock()
        if now - self._beat_at >= BEAT_SECONDS:
            self._write("beat", self._beat_max, self._beat_chunks)
            self._beat_at, self._beat_chunks, self._beat_max = now, 0, 0.0

    # ---- helpers -------------------------------------------------------------------------

    def _discard(self, count: int) -> None:
        for _ in range(count):
            self.mic.read(timeout=0.5)

    def _after_reply(self) -> None:
        """Forget anything heard while Friday was busy or speaking."""
        self.detector.reset()
        self.mic.flush()
        self._preroll.clear()
        self._discard(TAIL_CHUNKS)

    def _handle(self, audio: np.ndarray, source: str, preroll_s: float | None = None) -> bool:
        try:
            return bool(self.on_audio(audio, source, preroll_s))
        except Exception as exc:  # noqa: BLE001 - one bad turn must not stop the listener
            print(f"Turn failed: {exc}")
            return False

    def _record_command(
        self, first: list[np.ndarray], lead: list[np.ndarray] | None = None
    ) -> np.ndarray | None:
        """Collect audio until the speaker goes quiet. None means nothing usable was said.
        `lead` (the pre-roll) goes in front of the audio but is not shown to the endpointer."""
        threshold = speech_threshold(self.floor.level)
        endpoint = Endpointer(threshold)
        pending = list(first)
        chunks: list[np.ndarray] = list(lead or [])
        loud = 0
        loudest = 0.0
        reason = None
        while reason is None:
            chunk = pending.pop(0) if pending else self.mic.read(timeout=1.0)
            if chunk is None:
                reason = "mic_stalled"
                break
            chunks.append(chunk)
            level = rms(chunk)
            loudest = max(loudest, level)
            if level >= threshold:
                loud += 1
            reason = endpoint.update(chunk)
        print(
            f"    command window ended: {reason} after {endpoint.chunks * CHUNK_SECONDS:.1f} s"
            f" | loud chunks {loud}, loudest {loudest:.3f}, speech threshold {threshold:.4f},"
            f" noise floor {self.floor.level:.4f}"
        )
        if reason in ("no_speech", "mic_stalled"):
            return None
        return np.concatenate(chunks)

    def _wait_for_speech(self) -> list[np.ndarray] | None:
        """The follow-up window: the first loud chunk, or None if nothing is said in time."""
        threshold = speech_threshold(self.floor.level)
        for _ in range(FOLLOW_UP_CHUNKS):
            chunk = self.mic.read(timeout=1.0)
            if chunk is None or self.is_speaking():
                return None
            if rms(chunk) >= threshold:
                return [chunk]
        return None

    def _conversation(self, audio: np.ndarray | None, preroll_s: float | None = None) -> None:
        if audio is None:
            # Nobody spoke after the wake. Start fresh, so a "hey friday" said right now is not
            # blocked by the cooldown of the wake that just ended.
            self.detector.reset()
            self._preroll.clear()
            return
        source = "wake"
        while audio is not None:
            handled = self._handle(audio, source, preroll_s if source == "wake" else None)
            self._after_reply()
            if not handled:
                return
            first = self._wait_for_speech()
            if first is None:
                print("Follow-up window closed.")
                return
            audio, source = self._record_command(first), "follow_up"

    def _push_to_talk(self, first: np.ndarray) -> None:
        chunks = [first]
        while self.key_down() and len(chunks) < MAX_PTT_CHUNKS:
            chunk = self.mic.read(timeout=0.5)
            if chunk is None:
                break
            chunks.append(chunk)
        self._handle(np.concatenate(chunks), "key")
        self._after_reply()

    # ---- main loop -----------------------------------------------------------------------

    def run(self, should_stop: Callable[[], bool] = lambda: False) -> None:
        tail = 0
        while not should_stop():
            chunk = self.mic.read(timeout=0.5)
            if chunk is None:
                continue
            if self.is_speaking():
                tail = TAIL_CHUNKS
                self.detector.reset()
                self._preroll.clear()
                continue
            if tail > 0:
                tail -= 1
                continue
            if self.key_down():
                self._push_to_talk(chunk)
                continue
            self.floor.add(rms(chunk))
            self._preroll.append(chunk)
            score, fired = self.detector.feed(chunk)
            self._log_score(score, fired)
            if fired:
                self.wake_events += 1
                print(f">>> WAKE (score {score:.2f}). Listening...")
                lead = list(self._preroll)  # the pre-roll as it is at the moment the wake fires
                self._conversation(self._record_command([], lead), len(lead) * CHUNK_SECONDS)