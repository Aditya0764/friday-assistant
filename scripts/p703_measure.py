"""P7-03: latency and RAM of Friday on this laptop, everything loaded together.

Run (from the repo root, venv on):  python scripts\\p703_measure.py --label quick1 --quick
Writes docs/p703_<label>.md. Refuses to overwrite an existing file. Every number in the report
is computed from what this run measured; nothing is typed in by hand.

What it measures (see the report for n and conditions of each):
  1. Graph time per turn (text in, reply text out) for the 30 texts of evals/heldout2_30.csv, real
     Groq/Gemini LLM, router OFF and ON, interleaved row by row (the router model stays loaded
     for the OFF turns too), fake music player, fixed clock, throwaway database per turn.
  2. Router cost: paired ON-minus-OFF time, cold start of the router model in a fresh process,
     and the model's own forward time.
  3. STT: faster-whisper base.en with Friday's settings (vad=True, like the wake/follow-up
     path) on the saved clips in data\\clips*. Read only. Only counts and times are reported,
     never file names or transcripts.
  4. TTS: Piper synthesize_wav (no playback) for the reply texts of step 1.
  5. Full turn: clip -> STT -> graph -> synthesize_wav, one timer around all of it. No
     playback, no Bluetooth, WAV ready, not audio start. The parts are never added together.
  6. RAM of this process (psutil) after each load, and the peak during the work.

Network: only api.groq.com and generativelanguage.googleapis.com (same guard as the eval
runner). Keys come only from Friday's settings loader. Spotify is never touched.
Refuses to run on battery unless --allow-battery.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import wave
from contextlib import contextmanager
from datetime import date
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from friday import db
from friday.graph import build_graph, run_turn
from friday.prompt import FRIDAY_PROMPT

EVALS = ROOT / "evals"
DOCS = ROOT / "docs"
DATA = ROOT / "data"
ROWS_CSV = EVALS / "heldout2_30.csv"
RAM_LIMIT_MIB = 6144  # "6 GB" as Task Manager counts it (6 x 1024 MiB)
RULE_A_THRESHOLD_S = 0.5  # fixed before any measurement
RULE_A_MIN_N = 5
MAX_ERRORS = 3  # in a row, then that stage stops
WARMUP_TURNS = 2
BUCKETS = (
    "rules skill",
    "rules skill + LLM inside",
    "model + slot extraction",
    "model, no slot step",
    "plain chat LLM",
    "other",
)
BIG_APPS = ("chrome", "spotify", "msedge", "teams", "whatsapp", "dropbox", "firefox")
MIB = 1024 * 1024


def load_runner():
    """The eval runner, loaded by path (it is not a package). Reused, never edited."""
    spec = importlib.util.spec_from_file_location("run_eval_100", EVALS / "run_eval_100.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("run_eval_100", module)
    spec.loader.exec_module(module)
    return module


# ---------- numbers ----------


def p95(values) -> float:
    """Nearest-rank 95th percentile: the ceil(0.95 n)-th smallest value."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def stats(values) -> dict:
    v = [float(x) for x in values]
    if not v:
        return {"n": 0}
    return {
        "n": len(v),
        "mean": statistics.fmean(v),
        "median": statistics.median(v),
        "p95": p95(v),
        "max": max(v),
        "min": min(v),
    }


def num(x) -> str:
    if x is None:
        return "n/a"
    return f"{x:.1f}" if abs(x) < 100 else f"{x:.0f}"


def mib(nbytes) -> str:
    return "n/a" if nbytes is None else f"{nbytes / MIB:.0f}"


# ---------- timing the LLM ----------


class TimedLLM:
    """Wraps the real friday.llm.ask: records provider and wall time of each call. No pause here."""

    def __init__(self, real_ask, describe) -> None:
        self._real = real_ask
        self._describe = describe
        self.calls: list[dict] = []
        self.errors: list[dict] = []
        self.provider_failures: list[dict] = []  # filled by the runner's install_taps

    def reset(self) -> None:
        self.calls, self.errors, self.provider_failures = [], [], []

    def __call__(self, messages):
        start = time.perf_counter()
        try:
            reply = self._real(messages)
        except Exception as exc:  # recorded, then re-raised
            info = self._describe(exc)
            self.errors.append(info)
            self.calls.append({"ok": False, "ms": (time.perf_counter() - start) * 1000, **info})
            raise
        self.calls.append(
            {
                "ok": True,
                "provider": reply.provider,
                "model": reply.model,
                "ms": (time.perf_counter() - start) * 1000,
            }
        )
        return reply


# ---------- one turn ----------


def bucket_for(via: str, steps: list[str], llm_calls: int) -> str:
    if via == "rule":
        return "rules skill + LLM inside" if llm_calls else "rules skill"
    if via == "model":
        return "model + slot extraction" if "slots" in steps else "model, no slot step"
    if via == "llm":
        return "plain chat LLM"
    return "other"


def build_apps(runner, path: Path, conn, llm, embed_fn, classifier):
    """(setup app with no router model, turn app with `classifier`), sharing one registry."""
    registry = runner.build_eval_registry(
        path, runner.FakeScheduler(path), runner.FakePlayer(), embed_fn, llm
    )
    common = {"approve": None, "llm": llm, "system_prompt": FRIDAY_PROMPT}
    return (
        build_graph(conn, registry, classifier=None, **common),
        build_graph(conn, registry, classifier=classifier, **common),
    )


def _llm_fields(llm: TimedLLM, state: dict) -> dict:
    ok = [c for c in llm.calls if c["ok"]]
    provider = state.get("provider") or (ok[-1]["provider"] if ok else "")
    return {
        "llm_calls": [dict(c) for c in llm.calls],
        "provider": provider,
        "provider_failures": [dict(f) for f in llm.provider_failures],
    }


def timed_turn(runner, row: dict, classifier, llm: TimedLLM, embed_fn) -> dict:
    """Time run_turn(row text). The row's setup commands run first, untimed, rules only."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = Path(tmp) / "turn.db"
        conn = db.connect(path)
        try:
            setup_app, app = build_apps(runner, path, conn, llm, embed_fn, classifier)
            if row.get("setup", "").strip():
                runner.run_setup(setup_app, conn, row["setup"], embed_fn)
            llm.reset()
            error = None
            state: dict = {}
            start = time.perf_counter()
            try:
                state = run_turn(app, row["text"])
            except Exception as exc:  # noqa: BLE001 - recorded, not fatal
                error = runner.describe(exc)
            ms = (time.perf_counter() - start) * 1000
            steps = [t["step"] for t in db.get_traces(conn, state["run_id"])] if state else []
        finally:
            conn.close()
    via = state.get("via", "")
    return {
        "id": row["id"],
        "ms": ms,
        "via": via,
        "routed": state.get("skill_name") or "llm",
        "bucket": bucket_for(via, steps, len(llm.calls)),
        "reply_chars": len(state.get("reply", "")),
        "reply": state.get("reply", ""),
        "error": error,
        **_llm_fields(llm, state),
    }


def run_text_stage(
    rows,
    classifiers: dict,
    do_turn,
    passes: int,
    pause: float,
    sleep=time.sleep,
    say=print,
    max_errors: int = MAX_ERRORS,
):
    """Warm-up turns (discarded), then `passes` passes over the rows.

    Off and ON are interleaved per row, and the order alternates by pass and row, so network
    drift hits both alike. The pause is outside the timer. Returns (turns, complete?).
    """
    for row in rows[:WARMUP_TURNS]:
        for mode in ("off", "on"):
            sleep(pause)
            do_turn(row, classifiers[mode])
    say(f"warm-up done ({WARMUP_TURNS} rows x 2 modes, discarded)")
    turns: list[dict] = []
    streak = 0
    for p in range(passes):
        for i, row in enumerate(rows):
            for mode in ("off", "on") if (p + i) % 2 == 0 else ("on", "off"):
                sleep(pause)
                turn = do_turn(row, classifiers[mode])
                turn.update(mode=mode, pass_no=p + 1, seq=len(turns))
                turns.append(turn)
                streak = streak + 1 if turn["error"] else 0
                if streak >= max_errors:
                    say(f"Stopping text turns: {streak} errors in a row.")
                    return turns, False
        say(f"pass {p + 1}/{passes} done ({len(turns)} turns so far)")
    return turns, True


# ---------- router cost ----------


def analyse_pairs(turns: list[dict]) -> dict:
    """Pair the OFF and ON turn of the same row and pass; both must have succeeded."""
    by_key: dict = {}
    for t in turns:
        by_key.setdefault((t["id"], t["pass_no"]), {})[t["mode"]] = t
    pairs = []
    for (row_id, pass_no), got in by_key.items():
        off, on = got.get("off"), got.get("on")
        if off and on and not off["error"] and not on["error"]:
            pairs.append(
                {"id": row_id, "pass": pass_no, "off": off, "on": on, "diff": on["ms"] - off["ms"]}
            )
    model = [p for p in pairs if p["on"]["via"] == "model"]
    differing: dict = {}
    for p in pairs:
        if p["off"]["routed"] != p["on"]["routed"]:
            d = differing.setdefault(
                p["id"], {"id": p["id"], "off": set(), "on": set(), "via": set(), "diffs": []}
            )
            d["off"].add(p["off"]["routed"])
            d["on"].add(p["on"]["routed"])
            d["via"].add(p["on"]["via"])
            d["diffs"].append(p["diff"])
    return {
        "pairs": len(pairs),
        "all": stats([p["diff"] for p in pairs]),
        "model": stats([p["diff"] for p in model]),
        "model_rows": len({p["id"] for p in model}),
        "differing": sorted(differing.values(), key=lambda d: d["id"]),
    }


def forward_times(classifier, texts: list[str], repeats: int, clock=time.perf_counter) -> list:
    """The model's own forward time (tokenize + forward + softmax) per text, in ms."""
    for _ in range(3):  # warm-up, discarded
        classifier.classify(texts[0])
    out = []
    for _ in range(repeats):
        for text in texts:
            start = clock()
            result = classifier.classify(text)
            out.append((clock() - start) * 1000)
            if result is None:
                raise RuntimeError("router model returned None (not ready)")
    return out


def parse_child_output(stdout: str) -> dict:
    """The child prints other lines too; the last line that is JSON is the result."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {"ready_s": None, "error": "no result line"}


def cold_start_once(timeout: float = 300) -> dict:
    """Seconds from ModelClassifier() to ready, in a fresh Python process (torch not imported)."""
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "PYTHONPATH": str(ROOT)}
    try:
        done = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--child-cold-start"],
            capture_output=True, text=True, timeout=timeout, env=env, cwd=ROOT, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ready_s": None, "error": "timeout"}
    return parse_child_output(done.stdout)


def child_cold_start() -> None:
    from friday.router.model import ModelClassifier

    start = time.perf_counter()
    clf = ModelClassifier(background=True)
    while not clf.ready and not clf.error and time.perf_counter() - start < 300:
        time.sleep(0.01)
    print(json.dumps({"ready_s": time.perf_counter() - start if clf.ready else None,
                      "error": clf.error}))


# ---------- STT, TTS, full turn ----------


def find_clips(data_dir: Path) -> list[Path]:
    return sorted(
        p for d in sorted(data_dir.glob("clips*")) if d.is_dir() for p in sorted(d.glob("*.wav"))
    )


def wav_seconds(source) -> float | None:
    try:
        with wave.open(str(source) if isinstance(source, Path) else BytesIO(source)) as w:
            return w.getnframes() / w.getframerate()
    except (wave.Error, EOFError, OSError):
        return None


def run_stt_stage(stt, clips: list[Path], repeats: int, clock=time.perf_counter) -> dict:
    """Transcribe every clip `repeats` times (vad=True) after one discarded warm-up run.

    Keeps only numbers: no file name and no transcript is stored.
    """
    if not clips:
        return {"clips": 0}
    stt.transcribe(clips[0], vad=True)
    lengths, timings, rtf, empty, errors = [], [], [], 0, 0
    for clip in clips:
        seconds = wav_seconds(clip)
        if seconds is not None:
            lengths.append(seconds)
        for _ in range(repeats):
            start = clock()
            try:
                heard = stt.transcribe(clip, vad=True)
            except Exception:  # noqa: BLE001 - recorded, not fatal
                errors += 1
                continue
            ms = (clock() - start) * 1000
            timings.append(ms)
            if seconds:
                rtf.append(ms / 1000 / seconds)
            empty += not heard.text.strip()
    return {"clips": len(clips), "lengths": lengths, "timings_ms": timings, "rtf": rtf,
            "repeats": repeats, "empty_transcripts": empty, "errors": errors}


def run_tts_stage(tts, items: list[tuple[str, str]], repeats: int, clock=time.perf_counter) -> dict:
    """items: (row id, reply text). One discarded warm-up synth, then `repeats` per reply."""
    if not items:
        return {"items": []}
    tts.synthesize_wav(items[0][1])
    out, errors = [], 0
    for row_id, text in items:
        times, audio = [], None
        for _ in range(repeats):
            start = clock()
            try:
                wav = tts.synthesize_wav(text)
            except Exception:  # noqa: BLE001 - recorded, not fatal
                errors += 1
                continue
            times.append((clock() - start) * 1000)
            audio = wav_seconds(wav)
        if times:
            out.append({"id": row_id, "chars": len(text), "ms": times, "audio_s": audio})
    return {"items": out, "repeats": repeats, "errors": errors}


def full_turn(runner, clip: Path, mode: str, classifier, llm: TimedLLM, embed_fn, stt, tts,
              clock=time.perf_counter) -> dict:
    """clip -> STT (vad=True) -> graph -> synthesize_wav under ONE timer. No playback."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = Path(tmp) / "full.db"
        conn = db.connect(path)
        try:
            _, app = build_apps(runner, path, conn, llm, embed_fn, classifier)
            llm.reset()
            rec: dict = {"mode": mode, "status": "ok", "error": None}
            state: dict = {}
            start = clock()
            try:
                heard = stt.transcribe(clip, vad=True)
                t1 = clock()
                rec["stt_ms"] = (t1 - start) * 1000
                if not heard.text.strip():
                    rec["status"] = "empty_transcript"
                else:
                    state = run_turn(app, heard.text)
                    t2 = clock()
                    rec["graph_ms"] = (t2 - t1) * 1000
                    tts.synthesize_wav(state.get("reply", ""))
                    t3 = clock()
                    rec["tts_ms"] = (t3 - t2) * 1000
                    rec["total_ms"] = (t3 - start) * 1000
            except Exception as exc:  # noqa: BLE001 - recorded, not fatal
                rec["status"], rec["error"] = "error", runner.describe(exc)
        finally:
            conn.close()
    rec["via"] = state.get("via", "")
    rec.update(_llm_fields(llm, state))
    return rec


def run_full_stage(clips, classifiers: dict, do_full, pause, sleep=time.sleep, say=print,
                   max_errors: int = MAX_ERRORS):
    turns: list[dict] = []
    streak = 0
    for i, clip in enumerate(clips):
        for mode in ("off", "on") if i % 2 == 0 else ("on", "off"):
            sleep(pause)
            rec = do_full(clip, mode, classifiers[mode])
            turns.append(rec)
            streak = streak + 1 if rec["status"] == "error" else 0
            if streak >= max_errors:
                say(f"Stopping full turns: {streak} errors in a row.")
                return turns, False
    return turns, True


# ---------- RAM ----------


class MemReader:
    """Memory of one process through psutil (an object with memory_info / memory_full_info)."""

    def __init__(self, proc) -> None:
        self._proc = proc

    def rss(self) -> int:
        return self._proc.memory_info().rss

    def snapshot(self) -> dict:
        info = self._proc.memory_info()
        try:
            uss = self._proc.memory_full_info().uss
        except Exception:  # noqa: BLE001 - recorded, not fatal
            uss = None
        return {"rss": info.rss, "uss": uss, "peak_wset": getattr(info, "peak_wset", None)}


class PeakSampler:
    """Reads the working set every `interval` s in a thread; keeps the max, overall and per phase."""

    def __init__(self, read, interval: float = 0.05) -> None:
        self._read = read
        self._interval = interval
        self.peak = 0
        self.samples = 0
        self.phase_peaks: dict[str, int] = {}
        self._phase: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def sample_now(self) -> None:
        value = self._read()
        self.samples += 1
        self.peak = max(self.peak, value)
        if self._phase:
            self.phase_peaks[self._phase] = max(self.phase_peaks.get(self._phase, 0), value)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.sample_now()
            self._stop.wait(self._interval)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="ram-sampler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        self.sample_now()

    @contextmanager
    def phase(self, name: str):
        self._phase = name
        self.phase_peaks.setdefault(name, 0)
        self.sample_now()
        try:
            yield
        finally:
            self.sample_now()
            self._phase = None


def load_stages(steps, mem: MemReader, say=print) -> tuple[list[dict], dict]:
    """Run each (name, loader) in order, recording the memory right after. Returns (stages, objects).

    A loader that fails is recorded with its error type and the run goes on without it.
    """
    stages, objects = [], {}
    for name, loader in steps:
        start = time.perf_counter()
        error = ""
        try:
            objects[name] = loader()
        except Exception as exc:  # noqa: BLE001 - recorded, not fatal
            error = type(exc).__name__
        stage = {"name": name, "ms": (time.perf_counter() - start) * 1000, "error": error,
                 **mem.snapshot()}
        stages.append(stage)
        say(f"loaded {name}: {mib(stage['rss'])} MiB {('ERROR ' + error) if error else ''}")
    return stages, objects


# ---------- machine context ----------


def check_power(psutil_mod, allow_battery: bool) -> dict:
    battery = psutil_mod.sensors_battery()
    if battery is None:
        return {"battery": False, "plugged": None, "percent": None}
    info = {"battery": True, "plugged": battery.power_plugged, "percent": battery.percent}
    if info["plugged"] is False and not allow_battery:
        raise SystemExit("On battery power: plug in the charger, or pass --allow-battery.")
    return info


def process_groups(psutil_mod, top: int = 8) -> list[dict]:
    """Biggest process names by summed working set. Names only: no command lines."""
    groups: dict[str, list[int]] = {}
    for proc in psutil_mod.process_iter(["name", "memory_info"]):
        try:
            info = proc.info
            groups.setdefault(info["name"] or "?", []).append(info["memory_info"].rss)
        except (psutil_mod.Error, AttributeError, TypeError):
            continue
    ranked = sorted(groups.items(), key=lambda kv: -sum(kv[1]))[:top]
    return [{"name": n, "rss": sum(v), "procs": len(v)} for n, v in ranked]


def system_context(psutil_mod, power: dict) -> dict:
    vm = psutil_mod.virtual_memory()
    freq = psutil_mod.cpu_freq()
    return {
        "total": vm.total,
        "available": vm.available,
        "cpu_count": psutil_mod.cpu_count(logical=True),
        "cpu_physical": psutil_mod.cpu_count(logical=False),
        "cpu_mhz": getattr(freq, "current", None),
        "cpu_max_mhz": getattr(freq, "max", None),
        "cpu_percent": psutil_mod.cpu_percent(interval=1.0),
        "power": power,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processes": process_groups(psutil_mod),
    }


# ---------- report ----------

STAT_HEAD = ["| Group | n | mean ms | median ms | p95 ms | max ms |", "|---|---|---|---|---|---|"]


def stat_line(label: str, values) -> str:
    s = stats(values)
    if not s["n"]:
        return f"| {label} | 0 | n/a | n/a | n/a | n/a |"
    return (f"| {label} | {s['n']} | {num(s['mean'])} | {num(s['median'])} "
            f"| {num(s['p95'])} | {num(s['max'])} |")


def p95_note(n: int) -> str:
    if n < 1:
        return ""
    return f"p95 is nearest-rank: with n={n} it is the {math.ceil(0.95 * n)}th smallest value."


def verdict_a(model_stats: dict) -> str:
    """Rule (a): ABOVE / NOT ABOVE the threshold, or no verdict when n is too small."""
    n = model_stats["n"]
    if n < RULE_A_MIN_N:
        return f"Rule (a): n too small to apply rule (a) (n = {n}, need {RULE_A_MIN_N})"
    mean_s = model_stats["mean"] / 1000
    word = "ABOVE" if mean_s > RULE_A_THRESHOLD_S else "NOT ABOVE"
    return (f"Rule (a): mean added = {mean_s:.3f} s, n = {n}, "
            f"threshold {RULE_A_THRESHOLD_S} s: {word}")


def verdict_b(peak_bytes) -> str:
    """Rule (b): ABOVE / NOT ABOVE the RAM threshold (strictly above counts)."""
    if peak_bytes is None:
        return "Rule (b): no peak was measured, no verdict"
    word = "ABOVE" if peak_bytes / MIB > RAM_LIMIT_MIB else "NOT ABOVE"
    return f"Rule (b): peak = {mib(peak_bytes)} MiB, threshold {RAM_LIMIT_MIB} MiB: {word}"


def build_report(d: dict) -> str:
    """The whole results file. Every number comes from `d` (what the run measured)."""
    L: list[str] = []
    turns = d.get("text_turns", [])
    pairs = analyse_pairs(turns)
    stages = d.get("stages", [])
    ram = d.get("ram", {})
    sysd = d.get("system", {})
    peak_os = ram.get("peak_wset")
    peak_used = peak_os if peak_os is not None else ram.get("sampled_peak")
    peak_src = "OS peak working set (psutil peak_wset)" if peak_os is not None else (
        "sampled peak of the working set (peak_wset not available here)")

    L += [f"# P7-03 results: {d['label']} ({d['date']})", ""]
    if d.get("quick"):
        L += ["**QUICK RUN: 1 pass, no repeats. Fewer samples; read the n column.**", ""]
    if not d.get("complete", True):
        L += [f"**PARTIAL RUN: {'; '.join(d.get('incomplete', []))}**", ""]

    L += [
        "## Decision rules (fixed before the run)",
        "",
        ("- **(a) Router latency cost:** the router model goes ON unless the mean added time "
        "(router ON minus router OFF, same row, same pass) over the paired turns whose ON turn "
        f"ended via=model is MORE than {RULE_A_THRESHOLD_S} s. Needs n >= {RULE_A_MIN_N} pairs. "
        "The all-turn mean is shown next to it and is NOT used. Rows whose routed skill "
        "differs between the modes are listed separately."),
        ("- **(b) RAM:** a peak working set of this Python process, with everything loaded "
        f"(Whisper, Piper, MiniLM, router model, wake word), above {RAM_LIMIT_MIB} MiB (6 GB) "
        "means not ON. System used RAM is context only."),
        "",
        "### Result of (a)",
        "",
    ]
    m, a = pairs["model"], pairs["all"]
    if m["n"]:
        L.append(f"- via=model pairs: n={m['n']} pairs over {pairs['model_rows']} rows; mean "
                 f"ON-minus-OFF = **{num(m['mean'])} ms** (median {num(m['median'])}, min "
                 f"{num(m['min'])}, max {num(m['max'])}).")
    else:
        L.append("- via=model pairs: n=0, so no number for (a).")
    if a["n"]:
        L.append(f"- All pairs (not used for the decision): n={a['n']}; mean "
                 f"{num(a['mean'])} ms, median {num(a['median'])} ms.")
    L += ["", verdict_a(m), "", "### Result of (b)", ""]
    if peak_used is not None:
        L.append(f"- Peak working set = {mib(peak_used)} MiB (source: {peak_src}).")
    L += ["", verdict_b(peak_used)]
    L += ["", "## Conditions", ""]
    if sysd:
        pw = sysd["power"]
        power = ("no battery reported" if not pw["battery"] else
                 f"battery {pw['percent']}%, plugged in: {pw['plugged']}")
        L += [
            (f"- Machine: {sysd['platform']}, Python {sysd['python']}; {sysd['cpu_physical']} cores "
            f"/ {sysd['cpu_count']} threads; CPU {num(sysd['cpu_mhz'])} MHz now "
            f"(max {num(sysd['cpu_max_mhz'])}); CPU busy {num(sysd['cpu_percent'])}% over 1 s "
            "before the run."),
            f"- Power: {power}.",
            (f"- System RAM at the start: total {mib(sysd['total'])} MiB, available "
            f"{mib(sysd['available'])} MiB (used {mib(sysd['total'] - sysd['available'])} MiB)."),
        ]
        if sysd.get("available_end") is not None:
            L.append(f"- System RAM available at the end: {mib(sysd['available_end'])} MiB.")
        L += [("- Biggest process groups at the start (working set summed per name; shared pages "
              "can be counted twice; names only):"), "",
              "| Name | Processes | Working set MiB |", "|---|---|---|"]
        L += [f"| {p['name']} | {p['procs']} | {mib(p['rss'])} |" for p in sysd["processes"]]
        L.append("")
    L += [
        (f"- Rows: {d['rows_n']} from evals/heldout2_30.csv. Passes: {d['passes']}. Repeats for "
        f"local parts: {d['repeats']}. Pause between turns: {d['pause_s']} s (outside the timers)."),
        (f"- LLM: live Groq, Gemini as backup, through friday.llm.ask with Friday's system prompt. "
        f"Network allowed only to {', '.join(d['hosts'])}. Embedder local. Music player fake; "
        "Spotify never touched; clock fixed. A throwaway database per turn."),
        "- Setup commands of a row run first (untimed, rules only, no router model).",
        ("- **The router model was loaded for the whole run, so the router-OFF turns ran with it "
        "in memory (interleaved with the ON turns).** The RAM stages below are in load order: "
        "the stage before the router load is the row 'MiniLM embedder'."),
        ("- The wake-word detector was loaded and fed one silent chunk, then left idle: no audio "
        "was streamed through it during the timings."),
        f"- Modules already imported before the first load: {', '.join(d.get('imports', [])) or 'n/a'}.",
        (f"- Warm-up: {WARMUP_TURNS} rows x 2 modes discarded before the text turns; 1 discarded "
        "run before STT and TTS."),
        "",
    ]

    # --- latency of the graph
    L += ["## 1. Graph time per turn (text in, reply text out)", "",
          ("Timer around run_turn only: includes the real LLM network time. "
          f"Rows: {d['rows_n']}, passes: {d['passes']}."), ""]
    for mode, name in (("off", "Router OFF"), ("on", "Router ON")):
        mine = [t for t in turns if t["mode"] == mode]
        ok = [t for t in mine if not t["error"]]
        L += [f"### {name}", "",
              f"Turns run: {len(mine)}; errors excluded from the stats: {len(mine) - len(ok)}.",
              ""]
        if ok:
            first = min(ok, key=lambda t: t["seq"])
            L += [*STAT_HEAD, stat_line("all turns", [t["ms"] for t in ok])]
            for b in BUCKETS:
                sel = [t["ms"] for t in ok if t["bucket"] == b]
                if sel:
                    L.append(stat_line(f"ended: {b}", sel))
            L += ["", p95_note(len(ok)), (f"First timed turn in this mode: {num(first['ms'])} ms "
                  f"({first['bucket']})."), ""]
            with_llm = [t for t in ok if t["provider"]]
            if with_llm:
                L += ["By the provider that answered (turns that called the LLM):", "", *STAT_HEAD]
                for prov in sorted({t["provider"] for t in with_llm}):
                    L.append(stat_line(prov, [t["ms"] for t in with_llm if t["provider"] == prov]))
                L.append("")
    calls = [c for t in turns for c in t["llm_calls"]]
    fails = [f for t in turns for f in t["provider_failures"]]
    answered = {p: sum(1 for c in calls if c.get("provider") == p)
                for p in sorted({c["provider"] for c in calls if c.get("provider")})}
    kinds = {f"{p}/{k}": sum(1 for f in fails if f["provider"] == p and f["kind"] == k)
             for p, k in sorted({(f["provider"], f["kind"]) for f in fails})}
    L += [("LLM calls in the timed turns: "
          f"{len(calls)}; answered by {answered or 'none'}; calls that failed on every "
          f"provider: {sum(1 for c in calls if not c['ok'])}; provider failures (including ones "
          f"the backup covered): {kinds or 'none'}."), ""]

    # --- router cost
    L += ["## 2. Router cost", ""]
    L += [("Paired by row and pass (both turns must have succeeded). The ON turn and the OFF turn "
          "of a via=model row do different work (slot extraction vs a chat answer), so the "
          "difference is the cost of the route taken, not of the model alone."), "",
          "| Pairs | n | mean ms | median ms | min ms | max ms |", "|---|---|---|---|---|---|"]
    for label, s in (("via=model (decision)", m), ("all pairs", a)):
        if s["n"]:
            L.append(f"| {label} | {s['n']} | {num(s['mean'])} | {num(s['median'])} "
                     f"| {num(s['min'])} | {num(s['max'])} |")
        else:
            L.append(f"| {label} | 0 | n/a | n/a | n/a | n/a |")
    L += ["", "Rows whose routed skill differs between OFF and ON (not averaged together):", ""]
    if pairs["differing"]:
        L += ["| Row | OFF routed | ON routed | ON via | pairs | mean ON-OFF ms |",
              "|---|---|---|---|---|---|"]
        for r in pairs["differing"]:
            L.append(f"| {r['id']} | {'/'.join(sorted(r['off']))} | {'/'.join(sorted(r['on']))} "
                     f"| {'/'.join(sorted(r['via']))} | {len(r['diffs'])} "
                     f"| {num(statistics.fmean(r['diffs']))} |")
    else:
        L.append("None.")
    router = d.get("router", {})
    cold = [c for c in router.get("cold", [])]
    L += ["", "### Cold start of the router model", ""]
    if cold:
        okc = [c["ready_s"] for c in cold if c.get("ready_s") is not None]
        L.append(f"- Fresh Python process, time from ModelClassifier() to ready (includes "
                 f"importing torch and transformers and loading the weights). Runs: {len(cold)}; "
                 f"ready times in s: {', '.join(f'{x:.2f}' for x in okc) or 'none'}; "
                 f"failures: {len(cold) - len(okc)}. The disk cache was not cleared, so the first "
                 "run may be slower than the rest. Interpreter start and the friday import are "
                 "not counted.")
    else:
        L.append("- Not measured.")
    L += ["", "### Model forward time (tokenize + forward + softmax, in-process, warm)", ""]
    fw = router.get("forward", [])
    if fw:
        L += [*STAT_HEAD, stat_line(f"classify() on {router['forward_texts']} texts x "
                                    f"{router['forward_repeats']} repeats", fw), "", p95_note(len(fw))]
    else:
        L.append("Not measured.")
    L.append("")

    # --- STT
    L += ["## 3. STT (faster-whisper base.en, int8, CPU, vad=True)", ""]
    s = d.get("stt", {"clips": 0})
    if s.get("clips"):
        lens = stats(s["lengths"])
        L += [(f"- Clips: {s['clips']} (saved wake/follow-up clips in data\\clips*, read only; "
              f"{len(s['lengths'])} lengths readable). Repeats per clip: {s['repeats']}, so "
              f"{len(s['timings_ms'])} timings from {s['clips']} distinct clips."),
              f"- Clip length: min {num(lens.get('min'))} s, max {num(lens.get('max'))} s, "
              f"mean {num(lens.get('mean'))} s." if lens["n"] else "- Clip length unavailable.",
              (f"- Empty transcripts: {s['empty_transcripts']} of {len(s['timings_ms'])} timings; "
              f"errors: {s['errors']}. No file name or transcript is kept."), "",
              *STAT_HEAD, stat_line("transcribe()", s["timings_ms"]), "", p95_note(len(s["timings_ms"]))]
        if s["rtf"]:
            L.append(f"Transcribe time / clip length: mean {statistics.fmean(s['rtf']):.2f}, "
                     f"median {statistics.median(s['rtf']):.2f} (n={len(s['rtf'])}).")
    else:
        L.append("No clips found: not measured.")
    st_load = next((x for x in stages if x["name"] == "Whisper base.en"), None)
    if st_load:
        L.append(f"Model load: {num(st_load['ms'])} ms (one run).")
    L.append("")

    # --- TTS
    L += ["## 4. TTS (Piper en_US-amy-medium, synthesize_wav, no playback)", ""]
    t = d.get("tts", {"items": []})
    if t["items"]:
        pooled = [x for it in t["items"] for x in it["ms"]]
        L += [(f"- Texts: {len(t['items'])} (replies from the router-OFF turns of pass 1). "
              f"Repeats each: {t['repeats']}. Errors: {t['errors']}."), "",
              *STAT_HEAD, stat_line("synthesize_wav()", pooled), "", p95_note(len(pooled)), "",
              "| Row | text chars | mean synth ms | audio s |", "|---|---|---|---|"]
        for it in sorted(t["items"], key=lambda x: x["chars"]):
            L.append(f"| {it['id']} | {it['chars']} | {num(statistics.fmean(it['ms']))} "
                     f"| {num(it['audio_s'])} |")
    else:
        L.append("Not measured.")
    L.append("")

    # --- full turn
    L += ["## 5. Full turn: clip -> STT -> graph -> synthesize_wav", "",
          ("**No playback, no Bluetooth, WAV ready, not audio start.** One timer around the "
          "whole chain, one pass per router mode, real LLM. The parts below are measured inside "
          "the same turns and are shown separately: they are not added together here."), ""]
    ft = d.get("full", [])
    if ft:
        for mode, name in (("off", "Router OFF"), ("on", "Router ON")):
            mine = [x for x in ft if x["mode"] == mode]
            ok = [x for x in mine if x["status"] == "ok"]
            L += [f"### {name}", "",
                  (f"Turns: {len(mine)}; ok: {len(ok)}; empty transcript: "
                  f"{sum(x['status'] == 'empty_transcript' for x in mine)}; errors: "
                  f"{sum(x['status'] == 'error' for x in mine)} (not in the stats)."), ""]
            if ok:
                L += [*STAT_HEAD, stat_line("whole turn (one timer)", [x["total_ms"] for x in ok]),
                      stat_line("part: STT", [x["stt_ms"] for x in ok]),
                      stat_line("part: graph", [x["graph_ms"] for x in ok]),
                      stat_line("part: TTS", [x["tts_ms"] for x in ok]), "",
                      p95_note(len(ok)), ""]
    else:
        L += ["Not measured.", ""]

    # --- RAM
    L += ["## 6. RAM of this process (psutil)", "",
          ("Working set (RSS) after each load, in load order. USS (memory only this process "
          "owns) where Windows allowed it."), "",
          "| After loading | load ms | working set MiB | USS MiB | error |", "|---|---|---|---|---|"]
    for x in stages:
        L.append(f"| {x['name']} | {num(x['ms'])} | {mib(x['rss'])} | {mib(x['uss'])} "
                 f"| {x['error'] or ''} |")
    L += ["", (f"- Peak during the work (sampled every 50 ms, {ram.get('samples', 0)} samples, a "
          f"short spike can be missed): {mib(ram.get('sampled_peak'))} MiB."),
          (f"- OS peak working set since the process started (includes load spikes): "
          f"{mib(peak_os)} MiB."), "- Sampled peak per phase:", "",
          "| Phase | peak working set MiB |", "|---|---|"]
    L += [f"| {k} | {mib(v)} |" for k, v in ram.get("phase_peaks", {}).items()]
    L.append("")

    # --- per row
    L += ["## 7. Per row (all passes)", "",
          "| Row | OFF median ms | ON median ms | OFF routed | ON routed (via) |",
          "|---|---|---|---|---|"]
    for row_id in dict.fromkeys(t["id"] for t in turns):
        def med(mode, row_id=row_id):
            v = [t["ms"] for t in turns if t["id"] == row_id and t["mode"] == mode
                 and not t["error"]]
            return num(statistics.median(v)) if v else "n/a"

        def routes(mode, row_id=row_id):
            v = {f"{t['routed']} ({t['via']})" for t in turns
                 if t["id"] == row_id and t["mode"] == mode and not t["error"]}
            return "/".join(sorted(v)) or "n/a"

        L.append(f"| {row_id} | {med('off')} | {med('on')} | {routes('off')} | {routes('on')} |")

    L += ["", "## What this does not show", "",
          "- Every LLM-bound number depends on the network and the provider at that minute.",
          ("- Parts (STT, graph, TTS) are separate measurements; only section 5 is a full turn, "
          "and it ends at a WAV in memory, not at sound from the speaker."),
          ("- RAM here is this process only. It is not comparable with docs/ram.md, which was "
          "read by eye from Task Manager for the whole system."),
          "- The clips are the owner's voice on this laptop; other voices and noise may differ.",
          ""]
    return "\n".join(L)


# ---------- main ----------


def output_path(label: str, out_dir: Path) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", label):
        raise SystemExit("--label may only use letters, digits, - and _")
    path = out_dir / f"p703_{label}.md"
    if path.exists():
        raise SystemExit(f"Refusing to overwrite {path}. Pick a new --label.")
    return path


def main() -> None:
    if "--child-cold-start" in sys.argv:
        child_cold_start()
        return
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True, help="results go to docs/p703_<label>.md")
    parser.add_argument("--quick", action="store_true", help="1 pass, no repeats")
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=3, help="repeats for the local parts")
    parser.add_argument("--allow-battery", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=DOCS)
    args = parser.parse_args()
    passes, repeats = (1, 1) if args.quick else (args.passes, args.repeats)
    out = output_path(args.label, args.out_dir)

    import psutil

    power = check_power(psutil, args.allow_battery)
    print("Before starting: close Chrome, Spotify and other big apps. Keep the charger in.")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    runner = load_runner()
    runner.preflight_keys()
    runner.NetworkGuard(runner.LIVE_HOSTS).install()
    system = system_context(psutil, power)
    open_apps = [p["name"] for p in system["processes"] if p["name"].lower().startswith(BIG_APPS)]
    if open_apps:
        print(f"WARNING: big apps are running: {', '.join(open_apps)}. The numbers will say so.")

    rows = runner.read_rows(ROWS_CSV)
    clips = find_clips(DATA)
    print(f"{len(rows)} rows, {len(clips)} clips found.")

    data: dict = {
        "label": args.label, "date": str(date.today()), "quick": args.quick, "passes": passes,
        "repeats": repeats, "pause_s": runner.PAUSE_S, "rows_n": len(rows),
        "hosts": sorted(runner.LIVE_HOSTS), "system": system, "complete": True, "incomplete": [],
    }
    # cold start first, while this process is still small
    data["router"] = {"cold": [cold_start_once() for _ in range(1 if args.quick else 3)]}
    print(f"router cold start: {data['router']['cold']}")

    mem = MemReader(psutil.Process())
    watched = ("torch", "transformers", "faster_whisper", "piper", "sentence_transformers",
               "onnxruntime", "openwakeword", "langgraph")
    data["imports"] = [m for m in watched if m in sys.modules]
    baseline = {"name": "Python + Friday imports", "ms": 0.0, "error": "", **mem.snapshot()}

    def load_stt():
        from friday.voice.stt import SpeechToText

        return SpeechToText()

    def load_tts():
        from friday.voice.tts import TextToSpeech

        return TextToSpeech()

    def load_embedder():
        from friday.rag.embedder import embed

        embed(["warm up sentence"])
        return embed

    def load_router():
        from friday.router.model import ModelClassifier

        clf = ModelClassifier(background=False)
        if clf.error:
            raise RuntimeError(clf.error)
        return clf

    def load_wake():
        from friday.voice.wakeword import CHUNK, WakeWordDetector

        det = WakeWordDetector()
        det.feed(np.zeros(CHUNK, dtype=np.int16))
        return det

    stages, objs = load_stages(
        [("Whisper base.en", load_stt), ("Piper amy-medium", load_tts),
         ("MiniLM embedder", load_embedder), ("Router model (DistilBERT)", load_router),
         ("Wake-word detector", load_wake)],
        mem,
    )
    data["stages"] = [baseline, *stages]
    router_model = objs.get("Router model (DistilBERT)")
    if router_model is None:
        raise SystemExit("Router model did not load, so the router comparison cannot run.")

    from friday.llm import ask as real_ask

    llm = TimedLLM(real_ask, runner.describe)
    runner.install_taps(llm)
    embed_fn = objs.get("MiniLM embedder", runner.stub_embed)
    classifiers = {"off": None, "on": router_model}
    sampler = PeakSampler(mem.rss)
    sampler.start()

    with sampler.phase("text turns"):
        turns, complete = run_text_stage(
            rows, classifiers, lambda row, clf: timed_turn(runner, row, clf, llm, embed_fn),
            passes, runner.PAUSE_S)
    data["text_turns"] = turns
    if not complete:
        data["complete"] = False
        data["incomplete"].append("text turns stopped after 3 errors in a row")

    with sampler.phase("router forward"):
        texts = [runner.normalize(r["text"]) for r in rows]
        try:
            data["router"].update(forward=forward_times(router_model, texts, repeats),
                                  forward_texts=len(texts), forward_repeats=repeats)
        except RuntimeError as exc:
            print(f"forward time not measured: {exc}")

    stt = objs.get("Whisper base.en")
    tts = objs.get("Piper amy-medium")
    if stt:
        with sampler.phase("STT"):
            data["stt"] = run_stt_stage(stt, clips, repeats)
    if tts:
        first_off = [t for t in turns if t["mode"] == "off" and t["pass_no"] == 1
                     and not t["error"] and t["reply"].strip()]
        with sampler.phase("TTS"):
            data["tts"] = run_tts_stage(tts, [(t["id"], t["reply"]) for t in first_off], repeats)
    if stt and tts and clips and complete:
        with sampler.phase("full turns"):
            full, ok = run_full_stage(
                clips, classifiers,
                lambda clip, mode, clf: full_turn(runner, clip, mode, clf, llm, embed_fn, stt, tts),
                runner.PAUSE_S)
        data["full"] = full
        if not ok:
            data["complete"] = False
            data["incomplete"].append("full turns stopped after 3 errors in a row")

    sampler.stop()
    snap = mem.snapshot()
    data["ram"] = {"sampled_peak": sampler.peak, "samples": sampler.samples,
                   "phase_peaks": sampler.phase_peaks, "peak_wset": snap["peak_wset"]}
    data["system"]["available_end"] = psutil.virtual_memory().available

    text = build_report(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
