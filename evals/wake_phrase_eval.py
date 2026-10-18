"""Wake-phrase leftover eval on saved wake clips (dev set only, no held-out claim).

Run from the repo root:  python evals/wake_phrase_eval.py
Reads data/clips/*.wav, changes nothing. Every clip dated DAY is "Hey Friday, what time is it?".

Methods (all fixed before looking at results):
  0  current: transcribe(vad=True) + strip_wake_phrase
  d1 initial_prompt="Hey Friday."  + strip
  d2 hotwords="Hey Friday"         + strip
  e  word_timestamps, drop words that END before trigger + MARGIN_S, then strip
  c  regex strip; only if it removed nothing, drop a leading clause of at most 3 words ending
     in a comma (text only)
The trigger offset is NOT in the saved clip: it is found by replaying the clip through a fresh
wake detector (80 ms chunks) and taking the chunk where it fires.
"""

from __future__ import annotations

import re
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from friday.voice.endpoint import CHUNK_SECONDS, rms, speech_threshold
from friday.voice.phrase import strip_wake_phrase
from friday.voice.stt import get_stt
from friday.voice.wakeword import CHUNK, WakeWordDetector

CLIPS = Path("data") / "clips"
DAY = "20261019"
GOLD = "what time is it"
MARGIN_S = 0.2
CHAIR = "20261019-031007_follow_up.wav"


def load(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").copy()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", text.lower())).strip()


def drop_lead_clause(text: str) -> str:
    m = re.match(r"^\s*([^,]+),\s*(.+)$", text)
    if m and len(m.group(1).split()) <= 3:
        return m.group(2).strip()
    return text


def guarded(raw: str) -> str:
    """Regex strip; only if it removed nothing, drop a short leading clause."""
    stripped = strip_wake_phrase(raw)
    return stripped if stripped != raw.strip() else drop_lead_clause(raw)


def trigger_s(audio: np.ndarray, detector: WakeWordDetector) -> float | None:
    detector.reset()
    for i in range(len(audio) // CHUNK):
        _, fired = detector.feed(audio[i * CHUNK : (i + 1) * CHUNK])
        if fired:
            return (i + 1) * CHUNK_SECONDS  # end of the chunk that fired
    return None


def run(model, audio: np.ndarray, **kw):
    f32 = np.ascontiguousarray(audio, dtype=np.float32) / 32768.0
    segs, _ = model.transcribe(f32, language="en", vad_filter=True, **kw)
    return list(segs)


def text_of(segs) -> str:
    return " ".join(s.text.strip() for s in segs).strip()


def words_after(segs, cut: float) -> str:
    words = [w for s in segs for w in (s.words or []) if w.end >= cut]
    return "".join(w.word for w in words).strip()


def main() -> None:
    stt = get_stt()
    model = stt._model
    detector = WakeWordDetector()
    wakes = sorted(CLIPS.glob(f"{DAY}-*_wake*.wav"))
    follows = sorted(CLIPS.glob("*_follow_up*.wav"))
    print(f"wake clips on {DAY}: n={len(wakes)}   follow_up clips (all dates): n={len(follows)}")

    names = ["0 current", "d1 prompt", "d2 hotwords", "e timestamps", "c comma guard", "e no regex"]
    ok = {n: 0 for n in names}
    rows = []
    no_trigger = 0
    for p in wakes:
        a = load(p)
        t = trigger_s(a, detector)
        if t is None:
            no_trigger += 1
        s0 = run(model, a)
        base = strip_wake_phrase(text_of(s0))
        d1 = strip_wake_phrase(text_of(run(model, a, initial_prompt="Hey Friday.")))
        d2 = strip_wake_phrase(text_of(run(model, a, hotwords="Hey Friday")))
        se = run(model, a, word_timestamps=True)
        # no trigger found -> cannot cut; fall back to the plain transcript
        e = strip_wake_phrase(words_after(se, t + MARGIN_S) if t is not None else text_of(se))
        c = guarded(text_of(s0))
        e_raw = words_after(se, t + MARGIN_S) if t is not None else text_of(se)
        outs = dict(zip(names, [base, d1, d2, e, c, e_raw], strict=True))
        for n, v in outs.items():
            ok[n] += norm(v) == GOLD
        rows.append((p.name, len(a) / 16000, t, text_of(s0), outs))

    print("\nRESULTS  (correct = lower-cased, no punctuation == 'what time is it')")
    for n in names:
        print(f"  {n:14s} {ok[n]:2d} of {len(wakes)}")
    print(f"  clips where the replay found no trigger: {no_trigger} of {len(wakes)}")

    print("\nPER CLIP (raw = Whisper text before strip; * = differs from method 0)")
    for name, secs, t, raw, outs in rows:
        tt = "none" if t is None else f"{t:.2f}"
        print(f"{name[9:]}  {secs:4.1f}s trig {tt}s  raw={raw!r}")
        for n in names:
            flag = "OK " if norm(outs[n]) == GOLD else "BAD"
            mark = "*" if outs[n] != outs["0 current"] else " "
            print(f"    {mark}{n:14s} {flag} {outs[n]!r}")

    print(f"\nTRIGGER OFFSET: min {min(r[2] for r in rows if r[2]):.2f}s, "
          f"max {max(r[2] for r in rows if r[2]):.2f}s (a full pre-roll is 19 chunks = 1.52 s)")

    # ---- negatives: follow_up clips ----
    print(f"\nFOLLOW_UP clips n={len(follows)}: method 0 vs d1, d2, c (e needs a trigger: not applicable)")
    same = {"d1 prompt": 0, "d2 hotwords": 0, "c comma guard": 0}
    for p in follows:
        a = load(p)
        b = strip_wake_phrase(text_of(run(model, a)))
        d1 = strip_wake_phrase(text_of(run(model, a, initial_prompt="Hey Friday.")))
        d2 = strip_wake_phrase(text_of(run(model, a, hotwords="Hey Friday")))
        c = guarded(text_of(run(model, a)))
        for n, v in (("d1 prompt", d1), ("d2 hotwords", d2), ("c comma guard", c)):
            same[n] += v == b
            if v != b:
                print(f"    {p.name[9:]} {n}: {b!r} -> {v!r}")
    for n, k in same.items():
        print(f"  {n:14s} identical to method 0 on {k} of {len(follows)}")

    # ---- chair clip + no_speech_prob / avg_logprob ----
    print(f"\nCHAIR clip {CHAIR}")
    chair = load(CLIPS / CHAIR)
    thr = speech_threshold(0.0)
    print(f"  loud chunks at the minimum threshold {thr}: "
          f"{sum(rms(chair[i*CHUNK:(i+1)*CHUNK]) >= thr for i in range(len(chair)//CHUNK))}")
    for label, kw in (("0", {}), ("d1", {"initial_prompt": "Hey Friday."}),
                      ("d2", {"hotwords": "Hey Friday"})):
        segs = run(model, chair, **kw)
        print(f"  {label}: text={strip_wake_phrase(text_of(segs))!r} segments="
              f"{[(s.text.strip(), round(s.no_speech_prob, 3), round(s.avg_logprob, 3)) for s in segs]}")
    print("\nno_speech_prob / avg_logprob per segment on real speech clips (method 0)")
    probs = []
    for p in wakes + follows:
        if p.name == CHAIR:
            continue
        for s in run(model, load(p)):
            probs.append((s.no_speech_prob, s.avg_logprob, p.name[9:], s.text.strip()))
    nsp = [x[0] for x in probs]
    alp = [x[1] for x in probs]
    print(f"  segments n={len(probs)}: no_speech_prob max {max(nsp):.3f}, "
          f"avg_logprob min {min(alp):.3f}")
    worst = sorted(probs, key=lambda x: -x[0])[:3] + sorted(probs, key=lambda x: x[1])[:3]
    for x in worst:
        print(f"    nsp {x[0]:.3f} alp {x[1]:.3f} {x[2]} {x[3]!r}")

    # ---- unit strings for the strip rule and the comma guard ----
    print("\nSTRIP RULE on typed strings (regex, then regex+comma guard)")
    for s in ["Hey Friday, play Blinding Lights, by The Weeknd", "Friday the 13th is a movie",
              "play Blinding Lights", "Hey Freddy, what time is it", "Hey friend, set a timer, five minutes",
              "Hey Freddy what time is it", "what is on friday"]:
        r = strip_wake_phrase(s)
        print(f"  {s!r}\n      regex -> {r!r}   regex+guard -> {guarded(s)!r}")


if __name__ == "__main__":
    main()
