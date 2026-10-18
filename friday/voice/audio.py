"""Mic capture with a hold-to-talk key.

record_while_held() waits for the key, records while it is held, and returns
mono float32 audio at 16 kHz (what STT expects).
Run `python -m friday.voice.audio` to test: hold the key, speak, release.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
DEFAULT_KEY = "right ctrl"  # change this if you prefer another key, e.g. "f9"
POLL_SECONDS = 0.01
KEY_LOG = Path("data") / "key_events.log"  # one line per recording: what started it


@dataclass(frozen=True)
class Capture:
    audio: np.ndarray  # mono float32, 16 kHz
    seconds: float
    peak: float  # loudest sample, 0.0 to 1.0 (near 1.0 = clipping, near 0 = silent)


MODIFIER_KEYS = frozenset(
    {
        "ctrl", "left ctrl", "right ctrl",
        "alt", "left alt", "right alt", "alt gr",
        "shift", "left shift", "right shift",
        "windows", "left windows", "right windows",
    }
)  # the only keys the hook ever records; every other key is dropped on sight
KEY_LOG_LINES = 500  # data/key_events.log keeps only this many of the newest lines


def is_modifier(name: str | None) -> bool:
    return (name or "").lower() in MODIFIER_KEYS


def note_key(events: deque, event_type: str, name: str | None, scan_code: int) -> None:
    """Remember a key event, but only for modifier keys. Any other key is ignored entirely."""
    if is_modifier(name):
        events.append((event_type, name, scan_code, time.monotonic()))


def describe_key_start(key: str, events: list[tuple], now: float) -> str:
    """The detailed key-start line (file only): what the hook last saw before recording.

    events: (event_type, name, scan_code, time) for MODIFIER keys only, oldest first.
    `is_pressed` reads the library's own key table, so a recording with no recent "down"
    event for the key means that table said "held" without a real key-down."""
    if not events:
        return f"key-start: key={key!r} is_pressed=True, hook saw no modifier events yet"
    kind, name, scan, at = events[-1]
    recent = ", ".join(f"{t} {n}/{c} {now - w:.2f}s ago" for t, n, c, w in events[-3:])
    return (
        f"key-start: key={key!r} is_pressed=True, last modifier event: {kind} {name!r} "
        f"scan {scan} {now - at:.2f}s ago | recent: {recent}"
    )


def _write_key_log(short: str, detail: str | None = None) -> None:
    """Print the short line; append the detailed one to data/key_events.log (newest
    KEY_LOG_LINES kept). A debug aid: never raises."""
    print(f"    ({short})")
    try:
        KEY_LOG.parent.mkdir(exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        lines = []
        if KEY_LOG.exists():
            lines = KEY_LOG.read_text(encoding="utf-8").splitlines()
        lines.append(f"{stamp} {detail or short}")
        KEY_LOG.write_text("\n".join(lines[-KEY_LOG_LINES:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def record_while_held(key: str = DEFAULT_KEY, device: int | str | None = None) -> Capture:
    """Block until `key` is pressed, record until it is released, return the audio."""
    import keyboard
    import sounddevice as sd

    blocks: list[np.ndarray] = []
    recording = threading.Event()
    events: deque[tuple] = deque(maxlen=6)  # the last MODIFIER key events the hook saw

    def on_key(event) -> None:
        note_key(events, event.event_type, event.name, event.scan_code)

    def on_audio(indata, _frame_count, _time_info, _status) -> None:
        if recording.is_set():
            blocks.append(indata[:, 0].copy())

    hook = keyboard.hook(on_key)
    try:
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
            started = time.monotonic()
            _write_key_log(
                f"key-start ({key})", describe_key_start(key, list(events), started)
            )
            while keyboard.is_pressed(key):
                time.sleep(POLL_SECONDS)
            recording.clear()
            _write_key_log(f"key-end held {time.monotonic() - started:.2f}s")
    finally:
        keyboard.unhook(hook)

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