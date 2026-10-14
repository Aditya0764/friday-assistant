"""T-08: record own wake-word data. Run from the repo root, venv active.

Saves 16 kHz mono 16-bit WAV files under data_wake/ (git-ignored, never commit).

  python training/record_wakeword.py test
  python training/record_wakeword.py pos --session normal --count 20
  python training/record_wakeword.py miss --session s1 --count 20
  python training/record_wakeword.py neg --session talk --minutes 5

pos  = you say the wake phrase once per clip (positives).
miss = you say near-miss phrases (negatives that sound close).
neg  = a long recording of normal sound where the phrase is NOT said.
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


def record(seconds):
    audio = sd.rec(int(seconds * RATE), samplerate=RATE, channels=1, dtype="int16")
    sd.wait()
    return audio[:, 0]


def peak(audio):
    return float(np.abs(audio.astype(np.float32)).max()) / 32768.0


def level_note(level):
    if level < 0.05:
        return "TOO QUIET, speak up or move closer"
    if level > 0.98:
        return "CLIPPING, move back a bit"
    return "ok"


def next_index(folder, prefix):
    if not folder.exists():
        return 0
    return len(list(folder.glob(f"{prefix}_*.wav")))


def record_clips(folder, prompts, count):
    start = next_index(folder, "clip")
    for n in range(count):
        prompt = prompts[n % len(prompts)]
        input(f'[{n + 1}/{count}] Press Enter, then say: "{prompt}" ... ')
        time.sleep(0.3)
        audio = record(CLIP_SECONDS)
        level = peak(audio)
        save_wav(folder / f"clip_{start + n + 1:03d}.wav", audio)
        print(f"    saved, peak {level:.2f}: {level_note(level)}")


def record_negatives(folder, minutes):
    start = next_index(folder, "part")
    parts = max(1, round(minutes / CHUNK_MINUTES))
    print(f"Recording {parts * CHUNK_MINUTES} minutes in {parts} part(s).")
    print("Do NOT say the wake phrase. Ctrl+C stops (finished parts are kept).")
    for n in range(parts):
        print(f"  part {n + 1}/{parts} recording...")
        audio = record(CHUNK_MINUTES * 60)
        level = peak(audio)
        save_wav(folder / f"part_{start + n + 1:03d}.wav", audio)
        print(f"  saved, peak {level:.2f}: {level_note(level)}")


def mic_test():
    print("Input device:", sd.query_devices(kind="input")["name"])
    print("Say something for 3 seconds...")
    audio = record(3)
    level = peak(audio)
    print(f"peak {level:.2f}: {level_note(level)}")


def main():
    parser = argparse.ArgumentParser(description="Record wake-word data.")
    parser.add_argument("mode", choices=["test", "pos", "miss", "neg"])
    parser.add_argument("--session", default="s1")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--minutes", type=int, default=5)
    args = parser.parse_args()
    try:
        if args.mode == "test":
            mic_test()
        elif args.mode == "pos":
            record_clips(OUT / "pos" / args.session, [PHRASE], args.count)
        elif args.mode == "miss":
            record_clips(OUT / "neg" / f"miss_{args.session}", NEAR_MISSES, args.count)
        else:
            record_negatives(OUT / "neg" / args.session, args.minutes)
    except KeyboardInterrupt:
        print("\nStopped. Files saved so far are kept.")
        sys.exit(0)


if __name__ == "__main__":
    main()