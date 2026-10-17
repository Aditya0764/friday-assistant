"""100-command eval (P7-01): runs evals/eval_100.csv through Friday's graph, offline.

Nothing here calls Groq, Gemini or Spotify, and the network is blocked while it runs:
  - the LLM and the embedder are stubs, so chat rows only prove ROUTING (the reply is a stub);
  - the music player is a fake that records calls, so music rows prove routing and wording;
  - the clock is fixed (NOW below), so reminder times are exact;
  - every row gets its own throwaway database. Its `setup` commands run first, through the same
    graph. The real friday.db is never touched.
Each row is checked three ways: routing (expected_skill), the reply (expected_result), and the
database (lists and reminders rows: what was really saved or removed, not just what was said).

expected_result prefixes: exact: (whole reply, ignoring case), has: (substring, ignoring case),
re: (regex, as written), any: (any non-empty reply).
Docs rows that need a real LLM to answer are NOT counted: they go in their own section.

--router-model switches on the local DistilBERT router (models/router_v2, no network). Its slot
step needs the LLM, which is a stub here, so rows it would rescue still end as "say it again".

Run: set PYTHONPATH=.  then  python evals\\run_eval_100.py --label before
Writes evals/results/eval_100_<label>.json and .md. Refuses to overwrite an existing label.
Exit code is 0 whatever the scores are (only a bad command line or a label clash exits non-zero).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import socket
import tempfile
import time
import zlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from friday import db
from friday.graph import build_graph, run_turn
from friday.rag import store
from friday.rag.ingest import load_text
from friday.router.model import ModelClassifier
from friday.router.router import normalize
from friday.skills.base import SkillRegistry
from friday.skills.calc import CalcSkill
from friday.skills.catch import CatchSkill
from friday.skills.clock import ClockSkill
from friday.skills.docs import DocsSkill
from friday.skills.echo import EchoSkill
from friday.skills.lists import ListsSkill
from friday.skills.music import MusicSkill
from friday.skills.registry import build_registry
from friday.skills.remind import ReminderSkill

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "eval_100.csv"
DOCS = ROOT / "docs"
OUT = ROOT / "results"  # default for --out-dir

# A Saturday, 10:00 in a fixed zone, so "5 pm" is today and "6 30 am" is tomorrow.
NOW = datetime(2026, 10, 17, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
STUB_REPLY = "(stub reply)"
NOT_CHECKED = "not_checked_offline"
_READ_COMMAND = re.compile(
    r"(?:(?:can|could) you |please )?(?:read\b|keep reading|continue reading|carry on reading)"
)


def at(hour: int, minute: int = 0, days: int = 0) -> datetime:
    return (NOW + timedelta(days=days)).replace(hour=hour, minute=minute)


def after(**delta) -> datetime:
    return NOW + timedelta(**delta)


# What a correct assistant leaves in the database. These are written by hand from the CSV, not
# computed by the skills, so they are an independent check. A row that is not listed must leave
# the lists and the reminders exactly as its setup left them.
EXPECTED_LISTS = {
    "LST-01": {"shopping": ["bananas"]},
    "LST-02": {"grocery": ["eggs", "bread"]},
    "LST-03": {"packing": ["socks"]},
    "LST-04": {"groceries": ["eggs"]},
    "LST-05": {"todo": ["call the dentist"]},
    "LST-10": {"shopping": ["rice"]},
    "LST-11": {},
    "LST-12": {},
    "LST-13": {"notes": ["the demo is on friday"]},
}
# row id: (due time, text the saved message must contain)
EXPECTED_REMINDERS = {
    "REM-01": (at(17), "buy bread"),
    "REM-02": (after(minutes=10), "stretch"),
    "REM-03": (at(9, days=1), "submit the report"),
    "REM-04": (after(minutes=5), "timer"),
    "REM-05": (after(minutes=20), "timer"),
    "REM-06": (after(hours=1), "timer"),
    "REM-07": (at(6, 30, days=1), "alarm"),
    "REM-08": (at(7, days=1), "alarm"),
    "REM-09": (at(20), "vitamins"),
    "REM-10": (at(5, 45, days=1), "alarm"),
    "REM-11": (after(hours=1), "call the bank"),
    "REM-12": (at(15), "parcel arrives"),
    "REM-13": (at(20), "take out the trash"),
    "REM-14": (after(minutes=2), "timer"),
    "REM-15": (after(minutes=45), "message priya"),
}


# ---------- stand-ins (no network, no Spotify) ----------


def block_network() -> None:
    def refuse(*_args, **_kwargs):
        raise RuntimeError("network is blocked in the offline eval")

    socket.socket.connect = refuse  # type: ignore[method-assign]
    socket.create_connection = refuse  # type: ignore[assignment]


def stub_llm(_messages) -> SimpleNamespace:
    return SimpleNamespace(text=STUB_REPLY, provider="stub", model="stub", ms=0)


def stub_embed(texts: list[str]) -> np.ndarray:
    """Bag-of-words hashing into 64 dims: enough for the document store to work offline."""
    out = np.zeros((len(texts), 64), dtype="float32")
    for i, text in enumerate(texts):
        for word in re.findall(r"\w+", text.lower()):
            out[i, zlib.crc32(word.encode()) % 64] += 1
        out[i] /= np.linalg.norm(out[i]) or 1.0
    return out


class FakeScheduler:
    """Saves reminders in the row's database, like the real one, but schedules nothing."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def add(self, text: str, due_at: datetime) -> int:
        conn = db.connect(self._db_path)
        try:
            return db.add_reminder(conn, text, due_at)
        finally:
            conn.close()


class FakePlayer:
    def __init__(self) -> None:
        self.volume = 50
        self.calls: list[str] = []

    def play(self, rest, title="", artist=""):
        self.calls.append(f"play {rest}")
        return f"{title} by {artist}" if title and artist else rest

    def pause(self):
        self.calls.append("pause")

    def resume(self):
        self.calls.append("resume")

    def next(self):
        self.calls.append("next")

    def previous(self):
        self.calls.append("previous")

    def change_volume(self, direction: int) -> int:
        self.volume = min(100, max(0, self.volume + 10 * direction))
        self.calls.append(f"volume {self.volume}")
        return self.volume

    def set_volume(self, value: int) -> int:
        self.volume = min(100, max(0, value))
        self.calls.append(f"volume {self.volume}")
        return self.volume

    def now_playing(self):
        return "Test Song by Test Artist"


def build_eval_registry(db_path: Path, scheduler, player) -> SkillRegistry:
    """The same skills in the same order as build_registry, with the stand-ins plugged in."""
    registry = SkillRegistry()
    registry.register(EchoSkill())
    registry.register(ClockSkill(lambda: NOW))
    registry.register(ListsSkill(db_path))
    registry.register(DocsSkill(db_path, embed_fn=stub_embed, ask_fn=stub_llm))
    registry.register(CalcSkill())
    registry.register(ReminderSkill(scheduler, lambda: NOW))
    registry.register(MusicSkill(player))
    registry.register(CatchSkill(reminders=True, music=True))
    real = build_registry(scheduler, db_path, player).names()
    if registry.names() != real:  # the real registry changed: update this copy
        raise SystemExit(f"Skill order changed in build_registry: {real} vs {registry.names()}")
    return registry


# ---------- checks ----------


def check_reply(expected: str, reply: str) -> bool:
    """Does the reply meet expected_result? Prefixes are explained at the top of this file."""
    kind, _, body = expected.partition(":")
    if kind == "exact":
        return reply.strip().lower() == body.strip().lower()
    if kind == "has":
        return body.lower() in reply.lower()
    if kind == "re":
        return re.search(body, reply) is not None
    if kind == "any":
        return bool(reply.strip())
    raise ValueError(f"unknown expected_result prefix: {expected!r}")


def _list_key(name: str) -> str:
    return re.sub(r"\bto[ -]do\b", "todo", name)


def snapshot_lists(conn) -> dict[str, list[str]]:
    lists: dict[str, list[str]] = {}
    for row in conn.execute("SELECT list_name, item FROM list_items ORDER BY id"):
        lists.setdefault(_list_key(row["list_name"]), []).append(row["item"])
    return lists


def snapshot_reminders(conn) -> list[tuple[datetime, str]]:
    return [(r["due_at"], r["text"]) for r in db.pending_reminders(conn)]


def check_effect(row_id, lists_before, lists_after, rem_before, rem_after) -> tuple[bool, str]:
    """Did the database end up the way a correct assistant would leave it?"""
    want_lists = EXPECTED_LISTS.get(row_id, lists_before)
    if lists_after != want_lists:
        return False, f"lists: wanted {want_lists}, found {lists_after}"
    if row_id in EXPECTED_REMINDERS:
        due, needle = EXPECTED_REMINDERS[row_id]
        if len(rem_after) != 1:
            return False, f"reminders: wanted 1 saved, found {len(rem_after)}"
        saved_due, saved_text = rem_after[0]
        if saved_due != due:
            return False, f"reminder due {saved_due.isoformat()}, wanted {due.isoformat()}"
        if needle not in saved_text.lower():
            return False, f"reminder text {saved_text!r} lacks {needle!r}"
        return True, "reminder saved"
    if rem_after != rem_before:
        return False, f"reminders: wanted none saved, found {len(rem_after)}"
    return True, "lists changed as expected" if row_id in EXPECTED_LISTS else "nothing saved"


def is_docs_content(row: dict) -> bool:
    """A question about the document: only a real LLM can answer it, so it is not scored here."""
    return (
        row["expected_skill"] == "docs"
        and "doc:" in row["setup"]
        and not _READ_COMMAND.match(normalize(row["text"]))
    )


# ---------- running ----------


def run_setup(app, conn, setup: str) -> list[dict]:
    log = []
    for command in (part.strip() for part in setup.split("|")):
        if not command:
            continue
        if command.startswith("doc:"):
            name = command.removeprefix("doc:")
            try:
                store.add_document(conn, name, load_text(DOCS / name), embed_fn=stub_embed)
                log.append({"command": command, "ok": True, "reply": "document stored"})
            except Exception as exc:  # noqa: BLE001 - a broken setup is reported on the row
                log.append({"command": command, "ok": False, "reply": f"ERROR: {exc}"})
            continue
        state = run_turn(app, command)
        routed = state.get("skill_name") or "llm"
        log.append(
            {
                "command": command,
                "ok": routed not in ("llm", "catch"),
                "routed": routed,
                "reply": state.get("reply", ""),
            }
        )
    return log


def run_row(row: dict, classifier) -> dict:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = Path(tmp) / "row.db"
        conn = db.connect(path)
        try:
            player = FakePlayer()
            registry = build_eval_registry(path, FakeScheduler(path), player)
            app = build_graph(conn, registry, approve=None, llm=stub_llm, classifier=classifier)
            setup_log = run_setup(app, conn, row["setup"])
            lists_before, rem_before = snapshot_lists(conn), snapshot_reminders(conn)
            start = time.perf_counter()
            try:
                state = run_turn(app, row["text"])
            except Exception as exc:  # noqa: BLE001 - a crash is a failed row, not a dead run
                state = {"run_id": "", "skill_name": "", "reply": f"ERROR: {type(exc).__name__}: {exc}"}
            ms = round((time.perf_counter() - start) * 1000)
            lists_after, rem_after = snapshot_lists(conn), snapshot_reminders(conn)
            traces = db.get_traces(conn, state["run_id"])
            effect_ok, effect_detail = check_effect(
                row["id"], lists_before, lists_after, rem_before, rem_after
            )
        finally:
            conn.close()
    routed = state.get("skill_name") or "llm"
    reply = state.get("reply", "")
    router_trace = next((t["output"] for t in traces if t["step"] == "router"), "")
    routing_ok = routed == row["expected_skill"]
    result_ok = None if row["expected_skill"] == "llm" else check_reply(row["expected_result"], reply)
    setup_ok = all(item["ok"] for item in setup_log)
    if is_docs_content(row):
        status = NOT_CHECKED
    elif routing_ok and result_ok is not False and effect_ok and setup_ok:
        status = "pass"
    else:
        status = "fail"
    return {
        **row,
        "routed": routed,
        "router_trace": router_trace,
        "reply": reply,
        "routing_ok": routing_ok,
        "result_ok": result_ok,
        "effect_ok": effect_ok,
        "effect_detail": effect_detail,
        "setup_ok": setup_ok,
        "setup_log": setup_log,
        "player_calls": player.calls,
        "ms": ms,
        "status": status,
    }


# ---------- reports ----------


def tally(rows: list[dict]) -> dict:
    results = [r["result_ok"] for r in rows if r["result_ok"] is not None]
    return {
        "rows": len(rows),
        "routed_right": sum(r["routing_ok"] for r in rows),
        "result_right": sum(1 for x in results if x),
        "result_checked": len(results),
        "effect_right": sum(r["effect_ok"] for r in rows),
        "passed": sum(r["status"] == "pass" for r in rows),
    }


def summarize(rows: list[dict]) -> dict:
    checked = [r for r in rows if r["status"] != NOT_CHECKED]
    skills = list(dict.fromkeys(r["skill"] for r in rows))
    by_skill = {s: tally([r for r in checked if r["skill"] == s]) for s in skills}
    by_notes = {n: tally([r for r in checked if r["notes"] == n])
                for n in ("exact", "natural", "known problem")}
    return {
        "total_rows": len(rows),
        "checked": tally(checked),
        "not_checked_offline": len([r for r in rows if r["status"] == NOT_CHECKED]),
        "by_skill": by_skill,
        "by_notes": by_notes,
    }


def _cell(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def _tally_line(label: str, t: dict) -> str:
    return (
        f"| {label} | {t['rows']} | {t['routed_right']}/{t['rows']} "
        f"| {t['result_right']}/{t['result_checked']} | {t['effect_right']}/{t['rows']} "
        f"| {t['passed']}/{t['rows']} |"
    )


def write_reports(args, rows: list[dict], summary: dict) -> tuple[Path, Path]:
    json_path = args.out_dir / f"eval_100_{args.label}.json"
    md_path = args.out_dir / f"eval_100_{args.label}.md"
    meta = {
        "label": args.label,
        "date": str(date.today()),
        "router_model": args.router_model,
        "clock": NOW.isoformat(),
        "llm": "stub",
        "player": "fake",
    }
    with json_path.open("x", encoding="utf-8") as f:
        json.dump({"meta": meta, "summary": summary, "rows": rows}, f, indent=2)
    head = "| Group | Rows | Routed right | Reply right | DB effect right | Passed |"
    sep = "|---|---|---|---|---|---|"
    t = summary["checked"]
    lines = [
        f"# Eval 100: {args.label} ({meta['date']})",
        "",
        (
            f"Router model: {'ON (local, models/router_v2)' if args.router_model else 'off (rules only)'}. "
            f"LLM, embedder and music player are stubs; the clock is fixed at {NOW.isoformat()}. "
            "No network."
        ),
        "Chat rows (expected llm) are scored on routing only: the reply is a stub.",
        "A row passes only if routing, reply and database effect are all right.",
        "",
        "## Totals",
        "",
        f"- Checked rows: {t['rows']}. Passed: {t['passed']}. Failed: {t['rows'] - t['passed']}.",
        f"- Not checked offline (not counted as passes): {summary['not_checked_offline']}.",
        "",
        "## Per skill (checked rows only)",
        "",
        head,
        sep,
        *[_tally_line(s, v) for s, v in summary["by_skill"].items()],
        _tally_line("**all checked**", t),
        "",
        "## By phrasing note (checked rows only)",
        "",
        head,
        sep,
        *[_tally_line(n, v) for n, v in summary["by_notes"].items() if v["rows"]],
        "",
        "## Failed rows",
        "",
        "| Id | Text | Wanted | Routed | Reply | Why |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["status"] != "fail":
            continue
        why = []
        if not r["setup_ok"]:
            why.append("setup failed")
        if not r["routing_ok"]:
            why.append("routing")
        if r["result_ok"] is False:
            why.append("reply")
        if not r["effect_ok"]:
            why.append(f"db: {r['effect_detail']}")
        lines.append(
            f"| {r['id']} | {_cell(r['text'])} | {r['expected_skill']} "
            f"| {r['routed']} ({_cell(r['router_trace'])}) | {_cell(r['reply'])} | {_cell(', '.join(why))} |"
        )
    lines += [
        "",
        "## Not checked offline (document questions that need a real LLM)",
        "",
        "These are never counted as passes. Routing is shown so a wrong route is still visible.",
        "",
        "| Id | Text | Routed | Routing right | Reply (stub) |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        if r["status"] == NOT_CHECKED:
            lines.append(
                f"| {r['id']} | {_cell(r['text'])} | {r['routed']} | {r['routing_ok']} "
                f"| {_cell(r['reply'])} |"
            )
    lines += [
        "",
        "## Every row",
        "",
        "| Id | Status | Text | Routed | Reply |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['status']} | {_cell(r['text'])} | {r['routed']} | {_cell(r['reply'])} |"
        )
    with md_path.open("x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return json_path, md_path


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"{path.name}: duplicate ids")
    for r in rows:
        if r["expected_result"].partition(":")[0] not in ("exact", "has", "re", "any"):
            raise SystemExit(f"{path.name}: {r['id']} has a bad expected_result prefix")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True, help="name for this run, e.g. before or after")
    parser.add_argument("--router-model", action="store_true", help="use the local router model")
    parser.add_argument("--csv", type=Path, default=CSV_PATH, help="eval file (default eval_100.csv)")
    parser.add_argument("--out-dir", type=Path, default=OUT, help="where results go")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.label):
        raise SystemExit("--label may only use letters, digits, - and _")
    for suffix in (".json", ".md"):
        existing = args.out_dir / f"eval_100_{args.label}{suffix}"
        if existing.exists():
            raise SystemExit(f"Refusing to overwrite {existing}. Pick a new --label.")

    block_network()
    classifier = None
    if args.router_model:
        classifier = ModelClassifier(background=False)
        if classifier.error:
            raise SystemExit(f"Router model not loaded ({classifier.error}).")
    rows = []
    for row in read_rows(args.csv):
        done = run_row(row, classifier)
        rows.append(done)
        print(f"{done['id']:7} {done['status']:20} routed={done['routed']}")
    summary = summarize(rows)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = write_reports(args, rows, summary)
    t = summary["checked"]
    print(
        f"\nchecked {t['rows']}: passed {t['passed']}, failed {t['rows'] - t['passed']}; "
        f"not checked offline: {summary['not_checked_offline']}"
    )
    print(f"Wrote {md_path}\nWrote {json_path}")


if __name__ == "__main__":
    main()
