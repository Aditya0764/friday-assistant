"""P7-04: record the 30 commands of held-out set #2 from the microphone.

For each line of evals/heldout2_30.txt it shows the ID and the sentence. Press Enter to start
recording, speak, press Enter to stop. The take is saved as <out-dir>/<ID>.wav (16 kHz, mono,
16-bit), through the same MicHub Friday's wake word and push-to-talk use. Say the command only,
not the wake phrase.

  s + Enter   skip this row          q + Enter   quit (run again later to resume)
  --redo ID   record ID again (repeatable). Without it an existing WAV is NEVER overwritten.
              A redo is written to a temp file and swapped in only after you stop.

Rows that already have a WAV are skipped, so just run the script again to resume.
Do not run it while the Friday voice loop is running: both want the microphone.
The default folder data/spoken/heldout2 is git-ignored. Audio is never copied elsewhere.

Run: set PYTHONPATH=.  then  python scripts\\record_heldout2.py
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import threading
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TXT = ROOT / "evals" / "heldout2_30.txt"
CSV_PATH = ROOT / "evals" / "heldout2_30.csv"
OUT = ROOT / "data" / "spoken" / "heldout2"
SAMPLE_RATE = 16000
MIN_SECONDS = 0.3
SILENT_PEAK = 300  # int16 peak below this is close to silence (full scale is 32767)


def load_sentences(txt: Path = TXT, csv_path: Path = CSV_PATH) -> list[tuple[str, str]]:
    """(ID, sentence) per line of the txt. Line N must be row HLD2-NN of the CSV, same text."""
    lines = [ln.strip() for ln in txt.read_text(encoding="utf-8").splitlines() if ln.strip()]
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(lines) != len(rows):
        raise SystemExit(f"{txt.name} has {len(lines)} lines but {csv_path.name} has {len(rows)} rows.")
    out = []
    for n, (line, row) in enumerate(zip(lines, rows, strict=True), start=1):
        if row["id"] != f"HLD2-{n:02d}" or row["text"].strip() != line:
            raise SystemExit(f"Line {n} of {txt.name} does not match row {row['id']} of {csv_path.name}.")
        out.append((row["id"], line))
    return out


def record_take(hub, wait_for_stop) -> np.ndarray:
    """Collect int16 chunks from the hub from now until wait_for_stop() returns."""
    hub.flush()
    chunks: list[np.ndarray] = []
    stop = threading.Event()

    def collect() -> None:
        while not stop.is_set():
            chunk = hub.read(0.1)
            if chunk is not None:
                chunks.append(chunk)

    thread = threading.Thread(target=collect, daemon=True)
    thread.start()
    try:
        wait_for_stop()
    finally:
        stop.set()
        thread.join()
    while (chunk := hub.read(0.0)) is not None:  # what arrived while stopping
        chunks.append(chunk)
    return np.concatenate(chunks).astype(np.int16) if chunks else np.zeros(0, dtype=np.int16)


def write_wav(path: Path, audio: np.ndarray) -> None:
    """Write 16 kHz mono 16-bit audio to a temp file, then move it into place."""
    tmp = path.with_name(path.name + ".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.astype(np.int16).tobytes())
    os.replace(tmp, path)


def warnings_for(audio: np.ndarray, hub) -> list[str]:
    out = []
    seconds = len(audio) / SAMPLE_RATE
    if seconds < MIN_SECONDS:
        out.append(f"very short ({seconds:.2f} s)")
    elif int(np.abs(audio.astype(np.int32)).max()) < SILENT_PEAK:
        out.append("almost silent")
    if getattr(hub, "dropped", 0) or getattr(hub, "overflows", 0):
        out.append(f"mic lost audio (dropped {hub.dropped}, overflows {hub.overflows})")
    return out


def run(sentences, out_dir: Path, redo: set[str], hub, ask=input, say=print) -> dict:
    """Walk the sentences. Returns counts: recorded, skipped, existing."""
    counts = {"recorded": 0, "skipped": 0, "existing": 0}
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(sentences)
    for n, (row_id, sentence) in enumerate(sentences, start=1):
        path = out_dir / f"{row_id}.wav"
        if path.exists() and row_id not in redo:
            counts["existing"] += 1
            say(f"[{n}/{total}] {row_id}: already recorded, skipping.")
            continue
        say(f"\n[{n}/{total}] {row_id}   say:  {sentence}")
        answer = ask("  Enter = start, s = skip, q = quit: ").strip().lower()
        if answer == "q":
            say("Stopping. Run again to resume.")
            break
        if answer == "s":
            counts["skipped"] += 1
            continue
        say("  Recording... press Enter to stop.")
        audio = record_take(hub, lambda: ask(""))
        for warning in warnings_for(audio, hub):
            say(f"  WARNING: {warning}")
        write_wav(path, audio)
        counts["recorded"] += 1
        say(f"  Saved {row_id}.wav ({len(audio) / SAMPLE_RATE:.1f} s).")
    return counts


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--redo", action="append", default=[], metavar="ID",
                        help="record this ID again, replacing its WAV (repeatable)")
    parser.add_argument("--out-dir", type=Path, default=OUT, help="where the WAVs go")
    args = parser.parse_args(argv)
    sentences = load_sentences()
    known = {row_id for row_id, _ in sentences}
    redo = {r.strip().upper() for r in args.redo}
    if redo - known:
        raise SystemExit(f"--redo: unknown ids {sorted(redo - known)}")

    from friday.voice.mic import MicHub

    with MicHub() as hub:
        counts = run(sentences, args.out_dir, redo, hub)
    print(f"\nrecorded {counts['recorded']}, skipped {counts['skipped']}, "
          f"already there {counts['existing']}.")


if __name__ == "__main__":
    main()
