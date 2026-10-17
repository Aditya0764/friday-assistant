r"""Cut short review clips around false-accept moments so you can listen by ear.

Run from the repo root:  python training\cut_events.py
Output: data_wake\review\  (git-ignored with the rest of data_wake)
Each clip = 4.0 s before the flagged time + 1.5 s after (the model fires right
after the phrase ends, so the sound it reacted to is just before the time).
"""
import os
import wave

# (folder, file, seconds, score) - from the eval printouts
EVENTS = [
    ("away2", "part_075.wav", 204.0, 0.94),
    ("away2", "part_065.wav", 3.6, 0.91),
    ("away2", "part_054.wav", 275.8, 0.90),
    ("away2", "part_058.wav", 57.7, 0.89),
    ("away2", "part_076.wav", 75.8, 0.88),
    ("away2", "part_052.wav", 181.7, 0.87),
    ("away2", "part_078.wav", 27.6, 0.85),
    ("away2", "part_057.wav", 23.7, 0.85),
    ("away2", "part_052.wav", 204.3, 0.83),
    ("away2", "part_077.wav", 297.1, 0.81),
    ("away", "part_041.wav", 61.9, 0.92),
]
BEFORE = 4.0
AFTER = 1.5
SRC = os.path.join("data_wake", "neg")
OUT = os.path.join("data_wake", "review")
HARD = os.path.join("data_wake", "neg", "hard")


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(HARD, exist_ok=True)
    joined = []
    fmt = None
    for i, (folder, name, sec, score) in enumerate(EVENTS, 1):
        path = os.path.join(SRC, folder, name)
        if not os.path.exists(path):
            print("missing:", path)
            continue
        with wave.open(path, "rb") as w:
            rate, width, ch = w.getframerate(), w.getsampwidth(), w.getnchannels()
            start = max(0, int((sec - BEFORE) * rate))
            end = min(w.getnframes(), int((sec + AFTER) * rate))
            w.setpos(start)
            frames = w.readframes(end - start)
            fmt = (ch, width, rate)
        out = os.path.join(OUT, "ev%02d_%s_%s_%ss_score%.2f.wav" % (
            i, folder, name[:-4], ("%.1f" % sec), score))
        joined.append(frames)
        with wave.open(out, "wb") as o:
            o.setnchannels(ch)
            o.setsampwidth(width)
            o.setframerate(rate)
            o.writeframes(frames)
        print("wrote", out)
    if joined:
        # one file = the trainer takes a fixed number of random windows per file,
        # so all the hard moments together count as one negative recording
        hard = os.path.join(HARD, "part_001.wav")
        with wave.open(hard, "wb") as o:
            o.setnchannels(fmt[0])
            o.setsampwidth(fmt[1])
            o.setframerate(fmt[2])
            o.writeframes(b"".join(joined))
        print("wrote", hard, "(%d clips joined)" % len(joined))
    print("done - clips for listening are in", OUT)


if __name__ == "__main__":
    main()
