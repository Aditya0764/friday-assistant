"""T-08: record own wake-word data. Run from the repo root, venv active.

Saves 16 kHz mono 16-bit WAV files under data_wake/ (git-ignored, never commit).

  python training/record_wakeword.py test
  python training/record_wakeword.py pos --session normal --count 20
  python training/record_wakeword.py pos --session far --count 20 --auto
  python training/record_wakeword.py miss --session s1 --count 20
  python training/record_wakeword.py neg --session talk --minutes 5

pos  = you say the wake phrase once per clip (positives).
miss = you say near-miss phrases (negatives that sound close).
neg  = a long recording of normal sound where the phrase is NOT said.
--auto = no Enter key: a beep cues each clip (good for recording from far away).
"""

import argparse
import sys
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

RATE = 16000
CLIP_SECONDS = 2.5
CHUNK_MINUTES = 5
OUT = Path("data_wake")
PHRASE = "hey friday"
NEAR_MISSES = [
    "friday",
    "it's friday today",
    "happy friday",
    "see you on friday",
    "hey friend",
    "hey freddy",
    "hey frieda",
    "hey fry day",
    "hey fred",
    "friday night",
]


def save_wav(path, audio):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(audio.tobytes())


def record(stream, seconds):
    """Cut a clip out of the always-open mic stream (no device warm-up delay)."""
    waiting = stream.read_available
    if waiting:
        stream.read(waiting)  # drop audio from before the cue
    audio, _ = stream.read(int(seconds * RATE))
    return audio[:, 0].copy()


def peak(audio):
    return float(np.abs(audio.astype(np.float32)).max()) / 32768.0


def level_note(level):
    if level < 0.05:
        return "TOO QUIET, speak up or move closer"
    if level > 0.98:
        return "CLIPPING, move back a bit"
    return "ok"


def next_index(folder, prefix):
    """Highest existing clip number, so new clips never overwrite old ones."""
    if not folder.exists():
        return 0
    numbers = [int(p.stem.rsplit("_", 1)[1]) for p in folder.glob(f"{prefix}_*.wav")]
    return max(numbers, default=0)


def beep():
    try:
        import winsound

        winsound.Beep(1000, 150)
    except ImportError:
        print("\a", end="", flush=True)


def record_clips(stream, folder, prompts, count, auto):
    start = next_index(folder, "clip")
    if auto:
        print("Auto mode: say the phrase right after each beep. Ctrl+C stops.")
    for n in range(count):
        prompt = prompts[n % len(prompts)]
        label = f'[{n + 1}/{count}] say: "{prompt}"'
        if auto:
            print(f"{label} ... get ready")
            time.sleep(1.5)
            beep()
            time.sleep(0.2)
        else:
            input(f"{label} (press Enter, then speak) ... ")
            time.sleep(0.3)
        audio = record(stream, CLIP_SECONDS)
        level = peak(audio)
        save_wav(folder / f"clip_{start + n + 1:03d}.wav", audio)
        print(f"    saved, peak {level:.2f}: {level_note(level)}")


def record_negatives(stream, folder, minutes):
    start = next_index(folder, "part")
    parts = max(1, round(minutes / CHUNK_MINUTES))
    print(f"Recording {parts * CHUNK_MINUTES} minutes in {parts} part(s).")
    print("Do NOT say the wake phrase. Ctrl+C stops (finished parts are kept).")
    for n in range(parts):
        print(f"  part {n + 1}/{parts} recording...")
        audio = record(stream, CHUNK_MINUTES * 60)
        level = peak(audio)
        save_wav(folder / f"part_{start + n + 1:03d}.wav", audio)
        print(f"  saved, peak {level:.2f}: {level_note(level)}")


def mic_test(stream):
    print("Input device:", sd.query_devices(kind="input")["name"])
    print("Say something for 3 seconds...")
    audio = record(stream, 3)
    level = peak(audio)
    print(f"peak {level:.2f}: {level_note(level)}")


def main():
    parser = argparse.ArgumentParser(description="Record wake-word data.")
    parser.add_argument("mode", choices=["test", "pos", "miss", "neg"])
    parser.add_argument("--session", default="s1")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--minutes", type=int, default=5)
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args()
    try:
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16") as stream:
            time.sleep(1.0)  # let the mic start up before the first cue
            if args.mode == "test":
                mic_test(stream)
            elif args.mode == "pos":
                folder = OUT / "pos" / args.session
                record_clips(stream, folder, [PHRASE], args.count, args.auto)
            elif args.mode == "miss":
                folder = OUT / "neg" / f"miss_{args.session}"
                record_clips(stream, folder, NEAR_MISSES, args.count, args.auto)
            else:
                folder = OUT / "neg" / args.session
                record_negatives(stream, folder, args.minutes)
    except KeyboardInterrupt:
        print("\nStopped. Files saved so far are kept.")
        sys.exit(0)


if __name__ == "__main__":
    main()