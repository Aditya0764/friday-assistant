"""T-08: sanity-check recorded clips. Rough heuristics, not a verdict.

  python training/check_clips.py data_wake/pos/normal data_wake/pos/far

Per clip: peak level, when the peak happens, how long it is "active" (louder than
the room noise), when activity starts and ends, share of clipped samples, and how
much of the first 0.4 s is a pure 1 kHz tone (the recorder's beep). Flags:
NO SPEECH?, CUT START?, CUT END?, CLIPPED, BEEP?
"""

import sys
import wave
from pathlib import Path

import numpy as np

RATE = 16000
FRAME = 320  # 20 ms


def load(path):
    with wave.open(str(path), "rb") as f:
        data = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
    return data.astype(np.float32)


def beep_ratio(x):
    head = x[: int(0.4 * RATE)]
    if len(head) < 1024 or not head.any():
        return 0.0
    spec = np.abs(np.fft.rfft(head * np.hanning(len(head)))) ** 2
    freqs = np.fft.rfftfreq(len(head), 1 / RATE)
    total = spec[freqs > 100].sum()
    band = spec[(freqs > 900) & (freqs < 1100)].sum()
    return float(band / total) if total else 0.0


def analyse(path):
    x = load(path)
    n = len(x) // FRAME
    rms = np.sqrt((x[: n * FRAME].reshape(n, FRAME) ** 2).mean(axis=1))
    floor = float(np.percentile(rms, 10))
    active = np.flatnonzero(rms > max(floor * 4, 300))
    seconds = len(x) / RATE
    first = active[0] * FRAME / RATE if len(active) else 0.0
    last = (active[-1] + 1) * FRAME / RATE if len(active) else 0.0
    row = {
        "name": path.name,
        "peak": float(np.abs(x).max()) / 32768.0,
        "peak_t": int(np.abs(x).argmax()) / RATE,
        "active": len(active) * FRAME / RATE,
        "first": first,
        "last": last,
        "clipped": float((np.abs(x) >= 32000).mean()),
        "beep": beep_ratio(x),
    }
    flags = []
    if row["active"] < 0.3:
        flags.append("NO SPEECH?")
    if len(active) and first < 0.05:
        flags.append("CUT START?")
    if len(active) and last > seconds - 0.05:
        flags.append("CUT END?")
    if row["clipped"] > 0.005:
        flags.append("CLIPPED")
    if row["beep"] > 0.5:
        flags.append("BEEP?")
    row["flags"] = " ".join(flags)
    return row


def main():
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: python training/check_clips.py <folder> [<folder> ...]"
        )
    flagged = total = 0
    for folder in sys.argv[1:]:
        print(f"\n{folder}")
        print(
            f"{'clip':<14}{'peak':>5}{'at s':>6}{'active':>7}{'from':>6}{'to':>6}"
            f"{'clip%':>6}{'beep':>6}  flags"
        )
        for path in sorted(Path(folder).glob("*.wav")):
            r = analyse(path)
            total += 1
            flagged += bool(r["flags"])
            print(
                f"{r['name']:<14}{r['peak']:>5.2f}{r['peak_t']:>6.2f}{r['active']:>7.2f}"
                f"{r['first']:>6.2f}{r['last']:>6.2f}{r['clipped'] * 100:>6.1f}"
                f"{r['beep']:>6.2f}  {r['flags']}"
            )
    print(f"\n{flagged} of {total} clips flagged")


if __name__ == "__main__":
    main()