"""Measure voice-to-voice latency over 20 valid runs and write docs/latency.md.

Run `python -m friday.voice.latency`. Each round: hold the key, say the SAME short
sentence every time (for example "What is the capital of France?"), release, and
let Friday answer. Too-short clips, empty transcripts and failed LLM calls are
retried and not counted.

Voice-to-voice = key release -> first reply sentence ready to play.
It does NOT include audio-device or Bluetooth delay (not visible to the code).
"""

from __future__ import annotations

import math
import statistics
import time
from datetime import date
from pathlib import Path

from friday import db
from friday.llm import ask
from friday.trace import Tracer
from friday.voice.audio import DEFAULT_KEY, record_while_held
from friday.voice.stt import get_stt
from friday.voice.tts import get_tts

RUNS = 20
MIN_SECONDS = 0.3
VOICE_HINT = "\n\n(Reply in 1 to 3 short sentences, plain text, no markdown.)"
OUT = Path(__file__).resolve().parents[2] / "docs" / "latency.md"


def p95(values: list[int]) -> int:
    """Nearest-rank 95th percentile."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def write_report(rows: list[dict]) -> None:
    v2v = [r["v2v"] for r in rows]
    providers = {}
    for r in rows:
        providers[r["provider"]] = providers.get(r["provider"], 0) + 1

    lines = [
        "# Voice-to-voice latency",
        "",
        (
            f"Measured {date.today().isoformat()} on the HP i3 laptop, 8 GB RAM. "
            f"{len(rows)} valid runs, same spoken sentence each time."
        ),
        "",
        (
            "Voice-to-voice = key release until the first reply sentence is ready to play "
            "(STT + LLM + first TTS sentence + small overhead)."
        ),
        "Not included: audio-device and Bluetooth delay (not visible to the code).",
        "",
        "## Summary",
        "",
        f"- Mean: {statistics.mean(v2v):.0f} ms",
        f"- Median: {statistics.median(v2v):.0f} ms",
        f"- p95 (nearest rank, 19th of 20 sorted): {p95(v2v)} ms",
        f"- Min / max: {min(v2v)} / {max(v2v)} ms",
        f"- Mean STT: {statistics.mean(r['stt'] for r in rows):.0f} ms",
        f"- Mean LLM: {statistics.mean(r['llm'] for r in rows):.0f} ms",
        f"- Mean TTS first sentence: {statistics.mean(r['tts_first'] for r in rows):.0f} ms",
        f"- LLM providers used: {providers}",
        "- The earlier estimate was about 2.5 s. This file holds the measured numbers.",
        "",
        "## Runs",
        "",
        "| # | STT ms | LLM ms | TTS first ms | Total ms | Provider |",
        "|---|--------|--------|--------------|----------|----------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['n']} | {r['stt']} | {r['llm']} | {r['tts_first']} "
            f"| {r['v2v']} | {r['provider']} |"
        )
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    conn = db.connect()
    print("Loading models (once)...")
    stt = get_stt()
    tts = get_tts()
    rows: list[dict] = []
    print(f"Ready. {RUNS} valid runs needed. Hold [{DEFAULT_KEY}], speak, release.")

    try:
        while len(rows) < RUNS:
            n = len(rows) + 1
            print(f"\nRun {n}/{RUNS}: waiting for key...")
            cap = record_while_held()
            released = time.perf_counter()
            if cap.seconds < MIN_SECONDS:
                print("Too short, not counted.")
                continue

            tracer = Tracer(conn)
            with tracer.step("stt", f"{cap.seconds:.1f} s of audio") as out:
                heard = stt.transcribe(cap.audio)
                out["output"] = heard.text
            if not heard.text:
                print("Heard nothing, not counted.")
                continue

            try:
                with tracer.step("llm", heard.text) as out:
                    reply = ask([{"role": "user", "content": heard.text + VOICE_HINT}])
                    out["output"] = f"{reply.provider}/{reply.model}: {reply.text}"
            except Exception as exc:  # noqa: BLE001 - a failed run is retried, not counted
                print(f"LLM failed, not counted: {exc}")
                continue

            before_tts = time.perf_counter()
            spoken = tts.speak(reply.text)
            v2v = int((before_tts - released) * 1000) + spoken.first_audio_ms
            tracer.log("tts", reply.text, f"first audio ready {spoken.first_audio_ms} ms", v2v)

            rows.append(
                {
                    "n": n,
                    "stt": heard.ms,
                    "llm": reply.ms,
                    "tts_first": spoken.first_audio_ms,
                    "v2v": v2v,
                    "provider": reply.provider,
                }
            )
            print(f"You: {heard.text!r} -> total {v2v} ms (STT {heard.ms}, LLM {reply.ms})")
    except KeyboardInterrupt:
        print("\nStopped early. Nothing written (needs 20 valid runs).")
        return

    write_report(rows)
    print(f"\nDone. Wrote {OUT}")


if __name__ == "__main__":
    main()