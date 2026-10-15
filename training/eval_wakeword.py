"""T-10: score a wake-word model on YOUR held-out recordings (run on the laptop).

  python training\\eval_wakeword.py --model models\\wakeword\\hey_friday.onnx ^
      --pos data_wake\\pos\\eval --neg data_wake\\neg\\media data_wake\\neg\\away

Positives (--pos): short clips where the phrase IS said -> recall.
Negatives (--neg): long recordings where it is NOT said -> false accepts per hour.
Scores are cached next to the model, so changing thresholds is instant.
"""

import argparse
import hashlib
import sys
import wave
from pathlib import Path

import numpy as np

CHUNK = 1280  # 80 ms at 16 kHz, what openWakeWord expects
LEAD_SECONDS = 1.0
TRAIL_SECONDS = 1.0  # the model needs audio after the last word to decide


def load_wav(path):
    with wave.open(str(path), "rb") as f:
        if f.getframerate() != 16000 or f.getnchannels() != 1:
            raise SystemExit(f"{path}: need 16 kHz mono")
        return np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)


def chunk_scores(model, audio):
    """Score of every 80 ms chunk, streamed the way the live app will do it."""
    model.reset()
    scores = []
    for i in range(0, len(audio) - CHUNK + 1, CHUNK):
        out = model.predict(audio[i : i + CHUNK])
        scores.append(max(out.values()))
    return np.array(scores, dtype=np.float32)


def cached_scores(model, path, cache, lead=False):
    tag = f"{path.resolve()}:{path.stat().st_size}"
    if lead:
        tag += f":L{LEAD_SECONDS}T{TRAIL_SECONDS}"
    key = hashlib.md5(tag.encode()).hexdigest()
    file = cache / f"{key}.npy"
    if file.exists():
        return np.load(file)
    audio = load_wav(path)
    if lead:
        pad_in = np.zeros(int(LEAD_SECONDS * 16000), np.int16)
        pad_out = np.zeros(int(TRAIL_SECONDS * 16000), np.int16)
        audio = np.concatenate([pad_in, audio, pad_out])
    scores = chunk_scores(model, audio)
    np.save(file, scores)
    return scores


def count_events(scores, threshold, cooldown_chunks):
    """Separate triggers: a score over threshold, then a quiet period."""
    events, last = [], -(10**9)
    for i in np.flatnonzero(scores >= threshold):
        if i - last > cooldown_chunks:
            events.append(int(i))
        last = i
    return events


def wav_files(folders):
    files = []
    for folder in folders:
        files += sorted(Path(folder).rglob("*.wav"))
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True)
    ap.add_argument("--pos", nargs="+", default=[])
    ap.add_argument("--neg", nargs="+", default=[])
    ap.add_argument("--thresholds", nargs="+", type=float, default=[0.3, 0.5, 0.7, 0.9])
    ap.add_argument(
        "--cooldown", type=float, default=2.0, help="seconds between events"
    )
    ap.add_argument("--max-negative-files", type=int, default=0)
    args = ap.parse_args()

    from openwakeword.model import Model

    model_path = Path(args.model)
    model = Model(wakeword_models=[str(model_path)], inference_framework="onnx")
    cache = model_path.parent / f"score_cache_{model_path.stem}"
    cache.mkdir(exist_ok=True)
    cooldown = int(args.cooldown * 16000 / CHUNK)

    pos_files = wav_files(args.pos)
    pos = [cached_scores(model, f, cache, lead=True) for f in pos_files]
    neg_files = wav_files(args.neg)
    if args.max_negative_files:
        neg_files = neg_files[: args.max_negative_files]
    neg = []
    for n, f in enumerate(neg_files, 1):
        neg.append(cached_scores(model, f, cache))
        print(f"  scored negative {n}/{len(neg_files)}: {f.name}", end="\r", flush=True)
    hours = sum(len(s) for s in neg) * CHUNK / 16000 / 3600

    print(f"\nmodel: {model_path}")
    print(f"positive clips: {len(pos)}   negative audio: {hours:.2f} hours")
    print(f"{'thr':>5} {'recall':>12} {'false accepts':>14} {'per hour':>9}")
    for thr in args.thresholds:
        hit = sum(1 for s in pos if len(s) and s.max() >= thr)
        events = sum(len(count_events(s, thr, cooldown)) for s in neg)
        rate = events / hours if hours else float("nan")
        recall = f"{hit}/{len(pos)}" + (f" {hit / len(pos):.0%}" if pos else "")
        print(f"{thr:>5} {recall:>12} {events:>14} {rate:>9.2f}")
        if events == 0 and hours:
            print(f"      zero events: true rate is probably under {3 / hours:.2f} /h")
    print("Bar to beat (not ours): recall >= 80% with <= 0.5 false accepts/hour.")
    if hours < 6:
        print(
            f"Only {hours:.1f} h of negatives: too little to show 0.5/h with zero events."
        )
    if pos:
        print("lowest-scoring positive clips (best score within each clip):")
        ranked = sorted((float(s.max()), f.name) for f, s in zip(pos_files, pos))
        for score, name in ranked[:6]:
            print(f"  {name}: {score:.2f}")
    first = []
    for f, s in zip(neg_files, neg):
        for i in count_events(s, args.thresholds[1], cooldown):
            first.append((float(s[i]), f.name, i * CHUNK / 16000))
    for score, name, sec in sorted(first, reverse=True)[:10]:
        print(f"  false accept: {name} at {sec:.1f}s score {score:.2f}")


if __name__ == "__main__":
    sys.exit(main())
