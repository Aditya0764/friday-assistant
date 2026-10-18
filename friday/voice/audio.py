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
MAX_HOLD_SECONDS = 60.0  # a key is never "held" longer than this, whatever the hook says
GRACE_SECONDS = 0.25  # right after a key-down, the library's own key table may lag behind


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


class KeyTracker:
    """Is the push-to-talk key held? Tracked from keyboard-hook events BY NAME.

    keyboard.is_pressed("right ctrl") is also True for the LEFT ctrl key (both are scan code 29),
    so Ctrl+C or Ctrl+V used to start a recording. Left ctrl events are named 'ctrl' and right
    ctrl events 'right ctrl': only a down event with exactly this key's name counts.

    A lost key-up (lock screen, UAC, remote desktop...) would leave the key "held" forever, so
    is_down() also lets go when: (1) any later up event for the key arrives; (2) the library's
    own table says no ctrl at all is held (it is a superset of this key, so False means this key
    is surely up), checked after GRACE_SECONDS because the table can lag the event by a moment;
    (3) MAX_HOLD_SECONDS have passed since the key went down."""

    def __init__(self, key=DEFAULT_KEY, lib_pressed=None, clock=time.monotonic, on_event=None):
        self.key = key.lower()
        self._lib_pressed = lib_pressed
        self._clock = clock
        self._on_event = on_event  # (event_type, name, scan_code), sees every event first
        self._lock = threading.Lock()
        self._since: float | None = None  # when the key went down; None = up
        self.hooked = False
        self._hook = None

    def handle(self, event_type: str, name: str | None, scan_code: int = 0) -> None:
        if self._on_event:
            self._on_event(event_type, name, scan_code)
        if (name or "").lower() != self.key:
            return
        with self._lock:
            if event_type == "down":
                if self._since is None:  # key auto-repeat sends more downs: keep the first time
                    self._since = self._clock()
            else:
                self._since = None

    def install(self, keyboard) -> bool:
        """Start listening. If the hook cannot be installed, say so and fall back loudly."""
        self._lib_pressed = keyboard.is_pressed
        try:
            self._hook = keyboard.hook(lambda e: self.handle(e.event_type, e.name, e.scan_code))
            self.hooked = True
        except Exception as exc:  # noqa: BLE001 - any hook failure means the same fallback
            self.hooked = False
            _warn_no_hook(self.key, exc)
        return self.hooked

    def close(self, keyboard) -> None:
        if self._hook is not None:
            keyboard.unhook(self._hook)
            self._hook = None

    def _lib_says_pressed(self) -> bool:
        try:
            return bool(self._lib_pressed(self.key)) if self._lib_pressed else True
        except Exception:  # noqa: BLE001 - a failing check must not hide a real key press
            return True

    def is_down(self) -> bool:
        if not self.hooked:  # fallback: the old behaviour, which also reacts to left ctrl
            return self._lib_says_pressed() if self._lib_pressed else False
        with self._lock:
            since = self._since
            if since is None:
                return False
            age = self._clock() - since
            if age > MAX_HOLD_SECONDS or (age > GRACE_SECONDS and not self._lib_says_pressed()):
                self._since = None  # lost key-up: let go
                return False
            return True


_warned_no_hook = False


def _warn_no_hook(key: str, exc: Exception) -> None:
    global _warned_no_hook
    if _warned_no_hook:
        return
    _warned_no_hook = True
    print(
        f"WARNING: could not install the keyboard hook ({exc}). Falling back to "
        f"keyboard.is_pressed({key!r}), which is ALSO true for the LEFT ctrl key: "
        "Ctrl+C or Ctrl+V can start a recording."
    )


def record_while_held(key: str = DEFAULT_KEY, device: int | str | None = None) -> Capture:
    """Block until `key` is pressed, record until it is released, return the audio."""
    import keyboard
    import sounddevice as sd

    blocks: list[np.ndarray] = []
    recording = threading.Event()
    events: deque[tuple] = deque(maxlen=6)  # the last MODIFIER key events the hook saw

    tracker = KeyTracker(key, on_event=lambda t, n, c: note_key(events, t, n, c))

    def on_audio(indata, _frame_count, _time_info, _status) -> None:
        if recording.is_set():
            blocks.append(indata[:, 0].copy())

    tracker.install(keyboard)
    try:
        # The stream is already running while we wait, so the first syllable is not clipped.
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=device,
            callback=on_audio,
        ):
            while not tracker.is_down():
                time.sleep(POLL_SECONDS)
            recording.set()
            started = time.monotonic()
            _write_key_log(
                f"key-start ({key})", describe_key_start(key, list(events), started)
            )
            while tracker.is_down():
                time.sleep(POLL_SECONDS)
            recording.clear()
            _write_key_log(f"key-end held {time.monotonic() - started:.2f}s")
    finally:
        tracker.close(keyboard)

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