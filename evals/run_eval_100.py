"""100-command eval (P7-01): runs evals/eval_100.csv through Friday's graph.

By default it is fully offline: nothing calls Groq, Gemini or Spotify, and the network is blocked.
  - the LLM and the embedder are stubs, so chat rows only prove ROUTING (the reply is a stub);
  - the music player is a fake that records calls, so music rows prove routing and wording;
  - the clock is fixed (NOW below), so reminder times are exact;
  - every row gets its own throwaway database. Its `setup` commands run first, through the same
    graph. The real friday.db is never touched.
Each row is checked three ways: routing (expected_skill), the reply (expected_result), and the
database (lists and reminders rows: what was really saved or removed, not just what was said).

expected_result prefixes: exact: (whole reply, ignoring case), has: (substring, ignoring case),
re: (regex, as written), any: (any non-empty reply).
Offline, docs questions that need a real LLM are NOT counted: they go in their own section.

--router-model switches on the local DistilBERT router (models/router_v2, no network). Its slot
step needs an LLM, so offline (stub) the rows it would rescue still end as "say it again".

--live-llm uses the real LLM (Groq, Gemini as backup, through friday.llm.ask) for chat answers,
docs answers and, with --router-model, slot extraction. Friday's own settings loader reads the
keys; this script never opens or prints them. The network guard then allows ONLY the Groq and
Gemini hosts, so Spotify and everything else stay blocked. The document embedder stays local
(HF_HUB_OFFLINE=1). The music player is still fake. Docs questions are graded in this mode.
An LLM or network failure is a RUNNER ERROR (not counted as pass or fail), never a Friday
failure. After 3 runner errors in a row the run stops and writes partial results.
One sample per row: LLM answers vary between runs, so read the replies, not just the counts.

--only ID,ID,...  runs just those rows (for a small smoke test).

--wav-dir DIR (spoken test, P7-04) runs each row on what Friday HEARD instead of the typed text.
DIR/<row id>.wav is decoded with friday.voice.decode, then transcribed by Friday's own
SpeechToText (vad=True, change with --no-vad). The STT only ever gets an array, never a path.
Transcripts are cached in a JSON (default <out-dir>/eval_100_heard_<DIR name>.json, or --transcripts)
keyed by the WAV's hash, so a router OFF run and a router ON run see IDENTICAL text and the second
run loads no Whisper at all. Only setup commands stay typed. A row with no WAV (or one that will not
decode) is no_audio: left out of the totals and listed. An empty transcript is a failed row, counted
(the graph is not called, as in the voice loop). Reports gain a "Heard" column. Without --wav-dir
nothing changes. No audio is ever copied or written to the results.

Run: set PYTHONPATH=.  then  python evals\\run_eval_100.py --label before
Writes evals/results/eval_100_<label>.json and .md. Refuses to overwrite an existing label.
Exit code is 0 whatever the scores are. Non-zero only for a bad command line, a label clash, a
bad expected_effect cell, or rows that have no effect spec (exit 2, see below).

expected_effect (optional CSV column): what a correct assistant leaves in the database. eval_100
rows use the hand-written tables below; any other CSV must give a spec for every row that saves
or removes something. Clauses are separated by ";", items inside a clause by "|":
  unchanged                      lists and reminders end exactly as setup left them
  list:<name>=<item>|<item>      the FULL final contents of that list ("list:x=" means empty)
  rem:<due>|<text>               exactly one pending reminder; <due> is a local time in the fixed
                                 zone, e.g. 2026-10-17T10:20, or "any"; <text> is a lowercase
                                 substring of the saved text
A row with list: clauses but no rem: clause must leave reminders unchanged, and the other way round.
Outside eval_100.csv, a row with no spec whose reply sounds state-changing (or whose database
changed) gets the status no_effect_spec: it is never silently treated as "unchanged", is not
counted as a pass or a fail, and makes the run exit 2.
"""

from __future__ import annotations

import argparse
import csv
import functools
import hashlib
import json
import os
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
from friday.prompt import FRIDAY_PROMPT
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
RUNNER_ERROR = "runner_error"
NO_EFFECT_SPEC = "no_effect_spec"
NO_AUDIO = "no_audio"
LIVE_HOSTS = frozenset({"api.groq.com", "generativelanguage.googleapis.com"})
PAUSE_S = 1.0  # between live LLM calls, to be gentle with rate limits
MAX_RUNNER_ERRORS = 3  # in a row, then the run stops
# Wording of a reply that says something was saved or removed. Used only to notice a row that
# needs an effect spec but has none.
_CHANGE_WORDING = re.compile(
    r"\b(?:added|removed|deleted|noted|remind you|alarm set|timer set)\b", re.IGNORECASE
)
_READ_COMMAND = re.compile(
    r"(?:(?:can|could) you |please )?(?:read\b|keep reading|continue reading|carry on reading)"
)
# Wording heuristic only: a plain-LLM reply that sounds like it DID a skill's job. Not scored.
_CLAIM_PATTERNS = [
    re.compile(
        r"\bi(?:'ve| have)? (?:added|saved|set|started|created|noted|removed|deleted|"
        r"scheduled|paused|skipped|muted|turned)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:i'll|i will) (?:remind|wake|set|add|play|save|note)\b", re.IGNORECASE),
    re.compile(r"\b(?:now )?playing\b", re.IGNORECASE),
    re.compile(r"\b(?:volume|timer|alarm|reminder) (?:is |has been |was )?(?:now )?(?:set|at)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:okay|ok|sure|done|got it)\b.{0,30}\b(?:added|saved|set|playing|paused|skipped|"
        r"reminder|timer|alarm)\b",
        re.IGNORECASE,
    ),
]


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


# ---------- network guard ----------


class NetworkGuard:
    """Refuses every connection except to the allowed hosts (none at all when offline).

    A host name is allowed only if it is in `allowed`; its resolved addresses are remembered and
    a connect to any other address is refused. Every refusal is recorded in `blocked`.
    """

    def __init__(self, allowed=frozenset()) -> None:
        self.allowed = frozenset(allowed)
        self.ips: set[str] = set()
        self.blocked: list[str] = []

    def check_host(self, host) -> None:
        name = host.decode() if isinstance(host, bytes) else str(host)
        if name not in self.allowed:
            self.blocked.append(name)
            raise OSError(f"network guard: host {name!r} is not allowed")

    def check_ip(self, address) -> None:
        ip = address[0] if isinstance(address, tuple) else str(address)
        if ip not in self.ips:
            self.blocked.append(str(ip))
            raise OSError(f"network guard: address {ip!r} is not allowed")

    def install(self) -> None:
        guard = self
        real_getaddrinfo = socket.getaddrinfo
        real_connect = socket.socket.connect
        real_connect_ex = socket.socket.connect_ex

        def getaddrinfo(host, *args, **kwargs):
            guard.check_host(host)
            found = real_getaddrinfo(host, *args, **kwargs)
            guard.ips.update(item[4][0] for item in found)
            return found

        def connect(sock, address):
            guard.check_ip(address)
            return real_connect(sock, address)

        def connect_ex(sock, address):
            guard.check_ip(address)
            return real_connect_ex(sock, address)

        socket.getaddrinfo = getaddrinfo
        socket.socket.connect = connect  # type: ignore[method-assign]
        socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]


def describe(exc: BaseException) -> dict:
    """What kind of failure this is. Only the type and a status number are kept, never the text."""
    chain: list[BaseException] = []
    err: BaseException | None = exc
    while err is not None and len(chain) < 6:
        chain.append(err)
        err = err.__cause__ or err.__context__
    codes = []
    for item in chain:
        response = getattr(item, "response", None)
        codes += [
            getattr(item, "status_code", None),
            getattr(item, "code", None),
            getattr(response, "status_code", None),
        ]
    status = next((c for c in codes if isinstance(c, int)), None)
    names = " ".join(type(item).__name__ for item in chain)
    texts = " ".join(str(item) for item in chain)  # looked at, never stored
    if "network guard" in texts:
        kind = "blocked_host"
    elif status == 429 or "RateLimit" in names or "ResourceExhausted" in names:
        kind = "rate_limit"
    elif status in (401, 403) or "Authentication" in names or "PermissionDenied" in names or (
        "API_KEY" in texts
    ):
        kind = "auth"
    elif any(isinstance(item, TimeoutError) for item in chain) or "Timeout" in names:
        kind = "timeout"
    elif (status or 0) >= 500:
        kind = "provider_error"
    elif "Connection" in names or any(isinstance(item, OSError) for item in chain):
        kind = "network"
    else:
        kind = "other"
    return {"kind": kind, "type": type(exc).__name__, "status": status}


def claim_snippet(reply: str) -> str:
    """The first phrase in a reply that sounds like a done action, or ''. A heuristic."""
    for pattern in _CLAIM_PATTERNS:
        match = pattern.search(reply)
        if match:
            return match.group(0)
    return ""


class Probe:
    """Wraps the real LLM and embedder for a live run and records what happened per row."""

    def __init__(self, real_ask, real_embed, guard: NetworkGuard, pause: float = PAUSE_S) -> None:
        self._real_ask = real_ask
        self._real_embed = real_embed
        self._guard = guard
        self._pause = pause
        self.calls: list[dict] = []
        self.errors: list[dict] = []
        self.provider_failures: list[dict] = []
        self.blocked: list[str] = []
        self._blocked_from = 0

    def start_row(self) -> None:
        self.calls, self.errors, self.provider_failures = [], [], []
        self._blocked_from = len(self._guard.blocked)

    def end_row(self) -> None:
        self.blocked = self._guard.blocked[self._blocked_from :]

    def ask(self, messages):
        time.sleep(self._pause)
        try:
            reply = self._real_ask(messages)
        except Exception as exc:  # recorded as a runner error, then re-raised
            info = describe(exc)
            self.errors.append(info)
            self.calls.append({"ok": False, **info})
            raise
        self.calls.append(
            {"ok": True, "provider": reply.provider, "model": reply.model, "ms": reply.ms}
        )
        return reply

    def embed(self, texts):
        try:
            return self._real_embed(texts)
        except Exception as exc:  # recorded as a runner error, then re-raised
            self.errors.append({**describe(exc), "kind": "embedder"})
            raise


def install_taps(probe: Probe) -> None:
    """Record every provider failure inside friday.llm.ask, even when the backup then answers."""
    import friday.llm as llm_module

    for name, provider in (("_call_groq", "groq"), ("_call_gemini", "gemini")):
        original = getattr(llm_module, name)

        @functools.wraps(original)
        def tapped(*args, _original=original, _provider=provider, **kwargs):
            try:
                return _original(*args, **kwargs)
            except Exception as exc:
                probe.provider_failures.append({"provider": _provider, **describe(exc)})
                raise

        setattr(llm_module, name, tapped)


# ---------- stand-ins (no Spotify, no real LLM unless --live-llm) ----------


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


def build_eval_registry(db_path: Path, scheduler, player, embed_fn, ask_fn) -> SkillRegistry:
    """The same skills in the same order as build_registry, with the stand-ins plugged in."""
    registry = SkillRegistry()
    registry.register(EchoSkill())
    registry.register(ClockSkill(lambda: NOW))
    registry.register(ListsSkill(db_path))
    registry.register(DocsSkill(db_path, embed_fn=embed_fn, ask_fn=ask_fn))
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


def parse_effect(spec: str) -> dict:
    """Parse an expected_effect cell. Raises ValueError with the reason if it is malformed.

    Returns {"lists": None | {list: [items]}, "reminder": None | (due or None for any, needle)}.
    None for lists or reminder means "must be unchanged".
    """
    spec = spec.strip()
    if spec == "unchanged":
        return {"lists": None, "reminder": None}
    lists: dict[str, list[str]] | None = None
    reminder = None
    for clause in (c.strip() for c in spec.split(";")):
        kind, _, body = clause.partition(":")
        if kind == "list":
            name, eq, items = body.partition("=")
            key = _list_key(name.strip().lower())
            if not eq or not key:
                raise ValueError(f"bad list clause {clause!r}, want list:<name>=<item>|<item>")
            lists = {} if lists is None else lists
            if key in lists:
                raise ValueError(f"list {key!r} given twice")
            lists[key] = [i.strip() for i in items.split("|") if i.strip()]
        elif kind == "rem":
            due_text, bar, needle = body.partition("|")
            if not bar or not needle.strip():
                raise ValueError(f"bad rem clause {clause!r}, want rem:<due>|<text>")
            if reminder is not None:
                raise ValueError("only one rem clause is allowed")
            due = None
            if due_text.strip() != "any":
                try:
                    due = datetime.fromisoformat(due_text.strip())
                except ValueError as exc:
                    raise ValueError(f"bad due time {due_text!r}: {exc}") from exc
                if due.tzinfo is not None:
                    raise ValueError(f"due time {due_text!r} must not carry a zone")
                due = due.replace(tzinfo=NOW.tzinfo)
            reminder = (due, needle.strip().lower())
        else:
            raise ValueError(f"unknown clause {clause!r}")
    return {"lists": {k: v for k, v in (lists or {}).items() if v} if lists is not None else None,
            "reminder": reminder}


def builtin_effect(row_id: str) -> dict | None:
    """The hand-written expectation for an eval_100 row, in the same form parse_effect returns."""
    if row_id not in EXPECTED_LISTS and row_id not in EXPECTED_REMINDERS:
        return None
    return {"lists": EXPECTED_LISTS.get(row_id), "reminder": EXPECTED_REMINDERS.get(row_id)}


def check_effect(
    row_id, lists_before, lists_after, rem_before, rem_after, spec: dict | None = None
) -> tuple[bool, str]:
    """Did the database end up the way a correct assistant would leave it?

    The built-in table wins, then the row's parsed expected_effect, then "nothing changes".
    """
    effect = builtin_effect(row_id) or spec or {"lists": None, "reminder": None}
    want_lists = lists_before if effect["lists"] is None else effect["lists"]
    if lists_after != want_lists:
        return False, f"lists: wanted {want_lists}, found {lists_after}"
    if effect["reminder"] is not None:
        due, needle = effect["reminder"]
        if len(rem_after) != 1:
            return False, f"reminders: wanted 1 saved, found {len(rem_after)}"
        saved_due, saved_text = rem_after[0]
        if due is not None and saved_due != due:
            return False, f"reminder due {saved_due.isoformat()}, wanted {due.isoformat()}"
        if needle not in saved_text.lower():
            return False, f"reminder text {saved_text!r} lacks {needle!r}"
        return True, "reminder saved"
    if rem_after != rem_before:
        return False, f"reminders: wanted none saved, found {len(rem_after)}"
    return True, "lists changed as expected" if effect["lists"] is not None else "nothing saved"


def lacks_effect_spec(row, spec, changed, routed, reply) -> bool:
    """A row that needs an effect spec (not eval_100) but has none, and may have saved something."""
    if not row.get("effect_required") or spec is not None or builtin_effect(row["id"]):
        return False
    claims = routed in ("lists", "reminders") and _CHANGE_WORDING.search(reply) is not None
    return changed or claims


def is_docs_content(row: dict) -> bool:
    """A question about the document: only a real LLM can answer it."""
    return (
        row["expected_skill"] == "docs"
        and "doc:" in row["setup"]
        and not _READ_COMMAND.match(normalize(row["text"]))
    )


# ---------- running ----------


def run_setup(app, conn, setup: str, embed_fn) -> list[dict]:
    log = []
    for command in (part.strip() for part in setup.split("|")):
        if not command:
            continue
        if command.startswith("doc:"):
            name = command.removeprefix("doc:")
            try:
                store.add_document(conn, name, load_text(DOCS / name), embed_fn=embed_fn)
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


def run_row(row: dict, classifier, probe: Probe | None = None) -> dict:
    """Run one row. With a probe the LLM and embedder are real (live); without, they are stubs."""
    live = probe is not None
    llm = probe.ask if probe else stub_llm
    embed_fn = probe.embed if probe else stub_embed
    if probe:
        probe.start_row()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = Path(tmp) / "row.db"
        conn = db.connect(path)
        try:
            player = FakePlayer()
            registry = build_eval_registry(path, FakeScheduler(path), player, embed_fn, llm)
            app = build_graph(
                conn, registry, approve=None, llm=llm, system_prompt=FRIDAY_PROMPT,
                classifier=classifier,
            )
            try:
                setup_log = run_setup(app, conn, row["setup"], embed_fn)
            except Exception as exc:  # noqa: BLE001 - a crash in setup is reported on the row
                setup_log = [{"command": row["setup"], "ok": False, "reply": f"ERROR: {exc}"}]
            lists_before, rem_before = snapshot_lists(conn), snapshot_reminders(conn)
            start = time.perf_counter()
            try:
                state = run_turn(app, row["text"])
            except Exception as exc:  # noqa: BLE001 - a crash is a failed row, not a dead run
                state = {"run_id": "", "skill_name": "", "reply": f"ERROR: {type(exc).__name__}: {exc}"}
            ms = round((time.perf_counter() - start) * 1000)
            lists_after, rem_after = snapshot_lists(conn), snapshot_reminders(conn)
            traces = db.get_traces(conn, state["run_id"])
            spec_text = row.get("expected_effect", "").strip()
            spec = parse_effect(spec_text) if spec_text else None
            effect_ok, effect_detail = check_effect(
                row["id"], lists_before, lists_after, rem_before, rem_after, spec
            )
            changed = lists_after != lists_before or rem_after != rem_before
        finally:
            conn.close()
    if probe:
        probe.end_row()
    routed = state.get("skill_name") or "llm"
    reply = state.get("reply", "")
    router_trace = next((t["output"] for t in traces if t["step"] == "router"), "")
    routing_ok = routed == row["expected_skill"]
    result_ok = None if row["expected_skill"] == "llm" else check_reply(row["expected_result"], reply)
    no_spec = lacks_effect_spec(row, spec, changed, routed, reply)
    if no_spec:  # the default "unchanged" check above means nothing for this row
        effect_ok, effect_detail = True, "no effect spec"
    setup_ok = all(item["ok"] for item in setup_log)
    runner_errors = (probe.errors if probe else []) + (
        [{"kind": "blocked_host", "type": "NetworkGuard", "status": None}]
        if probe and probe.blocked and not probe.errors
        else []
    )
    if runner_errors:
        status = RUNNER_ERROR
    elif not live and is_docs_content(row):
        status = NOT_CHECKED
    elif no_spec:
        status = NO_EFFECT_SPEC
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
        "llm_calls": probe.calls if probe else [],
        "provider_failures": probe.provider_failures if probe else [],
        "runner_errors": runner_errors,
        "blocked_hosts": probe.blocked if probe else [],
        "action_claim": claim_snippet(reply) if live and routed == "llm" else None,
        "ms": ms,
        "status": status,
    }


def run_all(rows, classifier, probe=None, max_errors=MAX_RUNNER_ERRORS, say=print):
    """Run the rows in order. Returns (finished rows, complete?)."""
    done: list[dict] = []
    streak = 0
    for row in rows:
        result = run_row(row, classifier, probe)
        done.append(result)
        say(f"{result['id']:7} {result['status']:20} routed={result['routed']}")
        streak = streak + 1 if result["status"] == RUNNER_ERROR else 0
        if streak >= max_errors:
            say(f"\nStopping: {streak} runner errors in a row.")
            return done, False
    return done, True


# ---------- spoken rows (--wav-dir) ----------


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_transcripts(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("entries", {})


def save_transcripts(path: Path, entries: dict) -> None:
    """Atomic, so an interrupted run leaves a valid cache and the next run resumes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"entries": entries}, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def transcribe_rows(rows, wav_dir: Path, stt_factory, decode, vad: bool, cache_path: Path,
                    model_name: str, say=print) -> dict[str, dict]:
    """What Friday heard for each row: {id: {"state": "ok" | "no_audio", "heard", "detail"}}.

    A cached transcript is reused when the WAV's hash, the vad flag and the STT model all match, so
    a second run never transcribes again (and never loads the model). `stt_factory` is only called
    when something really has to be transcribed.
    """
    entries = load_transcripts(cache_path)
    stt = None
    out: dict[str, dict] = {}
    for row in rows:
        row_id = row["id"]
        wav = wav_dir / f"{row_id}.wav"
        if not wav.is_file():
            out[row_id] = {"state": NO_AUDIO, "heard": "", "detail": "no WAV file"}
            continue
        digest = file_sha256(wav)
        cached = entries.get(row_id)
        if (cached and cached["sha256"] == digest and cached["vad"] == vad
                and cached["model"] == model_name):
            out[row_id] = {"state": "ok", "heard": cached["heard"], "detail": "cached"}
            continue
        if cached:
            say(f"WARNING: {row_id}: WAV, vad or model changed since it was cached; transcribing "
                "again. Earlier runs used the OLD text: re-run both router OFF and ON.")
        try:
            audio = decode(wav)
        except Exception as exc:  # noqa: BLE001 - a recording fault, not a Friday failure
            out[row_id] = {"state": NO_AUDIO, "heard": "",
                           "detail": f"could not decode ({type(exc).__name__})"}
            continue
        if stt is None:
            stt = stt_factory()
        heard = stt.transcribe(audio, vad=vad).text.strip()
        entries[row_id] = {"sha256": digest, "vad": vad, "model": model_name, "heard": heard}
        save_transcripts(cache_path, entries)
        out[row_id] = {"state": "ok", "heard": heard, "detail": "transcribed"}
    return out


def empty_result(row: dict, status: str, detail: str) -> dict:
    """A row the graph never ran on (empty transcript, or no audio). Same keys as run_row."""
    return {
        **row,
        "routed": "",
        "router_trace": "",
        "reply": "",
        "routing_ok": False,
        "result_ok": None if row["expected_skill"] == "llm" else False,
        "effect_ok": False,
        "effect_detail": detail,
        "setup_ok": True,
        "setup_log": [],
        "player_calls": [],
        "llm_calls": [],
        "provider_failures": [],
        "runner_errors": [],
        "blocked_hosts": [],
        "action_claim": None,
        "ms": 0,
        "status": status,
    }


def run_all_spoken(rows, heard: dict, classifier, probe=None, max_errors=MAX_RUNNER_ERRORS,
                   say=print):
    """Like run_all, but each row runs on its transcript. Returns (finished rows, complete?)."""
    done: list[dict] = []
    streak = 0
    for row in rows:
        h = heard[row["id"]]
        if h["state"] == NO_AUDIO:
            result = empty_result(row, NO_AUDIO, h["detail"])
        elif not h["heard"]:
            result = empty_result(row, "fail", "empty transcript")
        else:
            result = run_row({**row, "text": h["heard"]}, classifier, probe)
            result["text"] = row["text"]  # the sentence that was meant; `heard` is what Friday got
        result["heard"] = h["heard"]
        done.append(result)
        say(f"{result['id']:7} {result['status']:20} routed={result['routed']}")
        streak = streak + 1 if result["status"] == RUNNER_ERROR else 0
        if streak >= max_errors:
            say(f"\nStopping: {streak} runner errors in a row.")
            return done, False
    return done, True


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
    checked = [r for r in rows if r["status"] in ("pass", "fail")]
    skills = list(dict.fromkeys(r["skill"] for r in rows))
    by_skill = {s: tally([r for r in checked if r["skill"] == s]) for s in skills}
    by_notes = {n: tally([r for r in checked if r["notes"] == n])
                for n in ("exact", "natural", "known problem")}
    calls = [c for r in rows for c in r["llm_calls"]]
    failures = [f for r in rows for f in r["provider_failures"]]
    return {
        "total_rows": len(rows),
        "checked": tally(checked),
        "runner_errors": sum(r["status"] == RUNNER_ERROR for r in rows),
        "not_checked_offline": sum(r["status"] == NOT_CHECKED for r in rows),
        "no_effect_spec": sum(r["status"] == NO_EFFECT_SPEC for r in rows),
        "by_skill": by_skill,
        "by_notes": by_notes,
        "llm": {
            "calls": len(calls),
            "answered_by": {p: sum(1 for c in calls if c.get("provider") == p)
                            for p in sorted({c["provider"] for c in calls if c.get("provider")})},
            "calls_failed_for_good": sum(1 for c in calls if not c["ok"]),
            "provider_failures": {
                f"{p}/{k}": sum(1 for f in failures if f["provider"] == p and f["kind"] == k)
                for p, k in sorted({(f["provider"], f["kind"]) for f in failures})
            },
        },
    }


def _cell(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def _tally_line(label: str, t: dict) -> str:
    return (
        f"| {label} | {t['rows']} | {t['routed_right']}/{t['rows']} "
        f"| {t['result_right']}/{t['result_checked']} | {t['effect_right']}/{t['rows']} "
        f"| {t['passed']}/{t['rows']} |"
    )


def write_reports(args, rows: list[dict], summary: dict, meta: dict) -> tuple[Path, Path]:
    json_path = args.out_dir / f"eval_100_{args.label}.json"
    md_path = args.out_dir / f"eval_100_{args.label}.md"
    with json_path.open("x", encoding="utf-8") as f:
        json.dump({"meta": meta, "summary": summary, "rows": rows}, f, indent=2)
    live = meta["live_llm"]
    head = "| Group | Rows | Routed right | Reply right | DB effect right | Passed |"
    sep = "|---|---|---|---|---|---|"
    t = summary["checked"]
    model = "ON (local, models/router_v2)" if args.router_model else "off (rules only)"
    if live:
        setup_line = (
            f"Router model: {model}. LLM: LIVE (Groq, Gemini backup) with Friday's system prompt. "
            f"Network allowed only to {', '.join(sorted(LIVE_HOSTS))}. Embedder local; music player "
            f"fake; Spotify never touched; clock fixed at {NOW.isoformat()}. One sample per row."
        )
        chat_line = "Chat rows (expected llm) are scored on routing only: READ their real replies."
    else:
        setup_line = (
            f"Router model: {model}. LLM, embedder and music player are stubs; the clock is fixed "
            f"at {NOW.isoformat()}. No network."
        )
        chat_line = "Chat rows (expected llm) are scored on routing only: the reply is a stub."
    spoken = bool(meta.get("wav_dir"))
    spoken_lines = []
    if spoken:
        sp = meta["spoken"]
        spoken_lines = [
            (
                f"Spoken test: each row ran on what Friday HEARD ({sp['transcribed']} transcribed, "
                f"{sp['empty']} empty transcripts counted as failures, {sp['no_audio']} with no "
                f"audio left out of the totals). STT {meta['stt_model']}, vad={meta['vad']}. "
                f"Transcripts: {meta['transcripts_file']} (sha256 {meta['transcripts_sha256'][:12]}). "
                "Setup commands stay typed."
            ),
        ]
    lines = [
        f"# Eval 100: {args.label} ({meta['date']})",
        "",
        (
            f"**Passed {t['passed']} | Failed {t['rows'] - t['passed']} | "
            f"Runner errors {summary['runner_errors']}**"
        ),
    ]
    if not meta["complete"]:
        lines += [
            "",
            (
                f"**PARTIAL RUN: stopped after {MAX_RUNNER_ERRORS} runner errors in a row; "
                f"{meta['rows_run']} of {meta['rows_total']} rows ran.**"
            ),
        ]
    lines += [
        "",
        setup_line,
        chat_line,
        *spoken_lines,
        (
            "A row passes only if routing, reply and database effect are all right. A runner "
            "error (LLM, network or embedder problem) is not a Friday failure and is not in "
            "the totals."
        ),
        "",
        "## Totals",
        "",
        (
            f"- Checked rows: {t['rows']}. Passed: {t['passed']}. Failed: {t['rows'] - t['passed']}. "
            f"Runner errors: {summary['runner_errors']}."
        ),
        f"- Not checked offline (not counted as passes): {summary['not_checked_offline']}.",
        (
            f"- No effect spec (not passed, not failed; fix the CSV): {summary['no_effect_spec']}."
        ),
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
        "| Id | Text | Heard | Wanted | Routed | Reply | Why |" if spoken
        else "| Id | Text | Wanted | Routed | Reply | Why |",
        "|---|---|---|---|---|---|---|" if spoken else "|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["status"] != "fail":
            continue
        why = []
        if spoken and not r["heard"]:
            why.append("empty transcript")
        else:
            if not r["setup_ok"]:
                why.append("setup failed")
            if not r["routing_ok"]:
                why.append("routing")
            if r["result_ok"] is False:
                why.append("reply")
            if not r["effect_ok"]:
                why.append(f"db: {r['effect_detail']}")
        heard_cell = f" {_cell(r['heard'])} |" if spoken else ""
        lines.append(
            f"| {r['id']} | {_cell(r['text'])} |{heard_cell} {r['expected_skill']} "
            f"| {r['routed']} ({_cell(r['router_trace'])}) | {_cell(r['reply'])} | {_cell(', '.join(why))} |"
        )
    lines += [
        "",
        "## Runner errors (not Friday failures; not in the totals)",
        "",
        "| Id | Text | Kind | Detail |",
        "|---|---|---|---|",
    ]
    for r in rows:
        if r["status"] == RUNNER_ERROR:
            err = r["runner_errors"][0]
            detail = f"{err['type']}, status {err['status']}"
            if r["blocked_hosts"]:
                detail += f", blocked: {', '.join(sorted(set(r['blocked_hosts'])))}"
            lines.append(f"| {r['id']} | {_cell(r['text'])} | {err['kind']} | {_cell(detail)} |")
    if spoken:
        lines += [
            "",
            "## No audio (not in the totals; record or fix these WAVs)",
            "",
            "| Id | Text | Why |",
            "|---|---|---|",
        ]
        for r in rows:
            if r["status"] == NO_AUDIO:
                lines.append(f"| {r['id']} | {_cell(r['text'])} | {_cell(r['effect_detail'])} |")
    lines += [
        "",
        "## Rows with no effect spec (not in the totals; add expected_effect to the CSV)",
        "",
        "| Id | Text | Routed | Reply |",
        "|---|---|---|---|",
    ]
    for r in rows:
        if r["status"] == NO_EFFECT_SPEC:
            lines.append(
                f"| {r['id']} | {_cell(r['text'])} | {r['routed']} | {_cell(r['reply'])} |"
            )
    if not live:
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
    else:
        llm = summary["llm"]
        lines += [
            "",
            "## LLM usage",
            "",
            f"- Calls made by Friday: {llm['calls']}. Answered by: {llm['answered_by'] or 'none'}.",
            f"- Calls that failed on every provider: {llm['calls_failed_for_good']}.",
            (
                "- Provider failures (including ones the backup covered): "
                f"{llm['provider_failures'] or 'none'}."
            ),
            f"- Hosts the guard blocked: {meta['blocked_hosts'] or 'none'}.",
            "",
            "## Wording warnings (heuristic, NOT scored)",
            "",
            (
                "A reply from the plain LLM that sounds like it did a skill's job (matched by a "
                "simple wording pattern, so it can miss real cases and flag harmless ones). "
                "Read the replies yourself."
            ),
            "",
            "| Id | Text | Matched phrase | Reply |",
            "|---|---|---|---|",
        ]
        for r in rows:
            if r["action_claim"]:
                lines.append(
                    f"| {r['id']} | {_cell(r['text'])} | {_cell(r['action_claim'])} "
                    f"| {_cell(r['reply'])} |"
                )
    lines += [
        "",
        "## Every row",
        "",
        "| Id | Status | Text | Heard | Routed | Reply |" if spoken
        else "| Id | Status | Text | Routed | Reply |",
        "|---|---|---|---|---|---|" if spoken else "|---|---|---|---|---|",
    ]
    for r in rows:
        heard_cell = f" {_cell(r['heard'])} |" if spoken else ""
        lines.append(
            f"| {r['id']} | {r['status']} | {_cell(r['text'])} |{heard_cell} {r['routed']} "
            f"| {_cell(r['reply'])} |"
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
    effect_required = path.resolve() != CSV_PATH.resolve()
    for r in rows:
        r.setdefault("expected_effect", "")
        r["effect_required"] = effect_required
        if r["expected_effect"].strip():
            if builtin_effect(r["id"]):
                raise SystemExit(f"{path.name}: {r['id']} has an expected_effect and a built-in one")
            try:
                parse_effect(r["expected_effect"])
            except ValueError as exc:
                raise SystemExit(f"{path.name}: {r['id']} has a bad expected_effect: {exc}") from exc
        if r["expected_result"].partition(":")[0] not in ("exact", "has", "re", "any"):
            raise SystemExit(f"{path.name}: {r['id']} has a bad expected_result prefix")
    return rows


def preflight_keys() -> None:
    """Say only whether each key is set. The values are never read into a message."""
    from friday.config import get_settings

    try:
        settings = get_settings()
        groq, gemini = bool(settings.groq_api_key), bool(settings.gemini_api_key)
    except Exception as exc:
        raise SystemExit(f"Friday's settings did not load ({type(exc).__name__}).") from exc
    print(f"Groq key: {'set' if groq else 'MISSING'}. Gemini key: {'set' if gemini else 'MISSING'}.")
    if not (groq or gemini):
        raise SystemExit("No LLM key is set, so a live run cannot work.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True, help="name for this run, e.g. before or after")
    parser.add_argument("--router-model", action="store_true", help="use the local router model")
    parser.add_argument("--live-llm", action="store_true",
                        help="use the real Groq/Gemini LLM (network allowed to those hosts only)")
    parser.add_argument("--only", default="", help="comma-separated row ids, e.g. CHT-01,REM-09")
    parser.add_argument("--csv", type=Path, default=CSV_PATH, help="eval file (default eval_100.csv)")
    parser.add_argument("--out-dir", type=Path, default=OUT, help="where results go")
    parser.add_argument("--wav-dir", type=Path, default=None,
                        help="spoken test: run each row on the transcript of <dir>/<row id>.wav")
    parser.add_argument("--vad", action=argparse.BooleanOptionalAction, default=True,
                        help="voice-activity filter in the STT (spoken test only; default on)")
    parser.add_argument("--transcripts", type=Path, default=None,
                        help="transcript cache (default <out-dir>/eval_100_heard_<wav-dir name>.json)")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.label):
        raise SystemExit("--label may only use letters, digits, - and _")
    for suffix in (".json", ".md"):
        existing = args.out_dir / f"eval_100_{args.label}{suffix}"
        if existing.exists():
            raise SystemExit(f"Refusing to overwrite {existing}. Pick a new --label.")
    rows = read_rows(args.csv)
    total_rows = len(rows)
    if args.only:
        wanted = [i.strip().upper() for i in args.only.split(",") if i.strip()]
        unknown = [i for i in wanted if i not in {r["id"] for r in rows}]
        if unknown:
            raise SystemExit(f"--only: unknown ids {unknown}")
        rows = [r for r in rows if r["id"] in wanted]
    if args.wav_dir and not args.wav_dir.is_dir():
        raise SystemExit(f"--wav-dir {args.wav_dir} is not a folder.")

    guard = NetworkGuard(LIVE_HOSTS if args.live_llm else frozenset())
    guard.install()
    heard = None
    transcripts_path = None
    if args.wav_dir:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")  # Whisper must come from the local cache
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from friday.voice.decode import decode_audio_file
        from friday.voice.stt import DEFAULT_MODEL, get_stt

        transcripts_path = args.transcripts or args.out_dir / f"eval_100_heard_{args.wav_dir.name}.json"
        heard = transcribe_rows(rows, args.wav_dir, lambda: get_stt(DEFAULT_MODEL),
                                decode_audio_file, args.vad, transcripts_path, DEFAULT_MODEL)
        print(f"Transcripts: {transcripts_path}")
    probe = None
    if args.live_llm:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        preflight_keys()
        from friday.llm import ask as real_ask
        from friday.rag.embedder import embed as real_embed

        probe = Probe(real_ask, real_embed, guard)
        install_taps(probe)
        print(f"Live LLM: network allowed only to {', '.join(sorted(LIVE_HOSTS))}.")
    classifier = None
    if args.router_model:
        classifier = ModelClassifier(background=False)
        if classifier.error:
            raise SystemExit(f"Router model not loaded ({classifier.error}).")

    if heard is None:
        done, complete = run_all(rows, classifier, probe)
    else:
        done, complete = run_all_spoken(rows, heard, classifier, probe)
    summary = summarize(done)
    meta = {
        "label": args.label,
        "date": str(date.today()),
        "router_model": args.router_model,
        "live_llm": args.live_llm,
        "allowed_hosts": sorted(LIVE_HOSTS) if args.live_llm else [],
        "pause_s": PAUSE_S if args.live_llm else 0,
        "only": args.only,
        "clock": NOW.isoformat(),
        "llm": "live" if args.live_llm else "stub",
        "player": "fake",
        "complete": complete,
        "rows_run": len(done),
        "rows_total": total_rows if not args.only else len(rows),
        "blocked_hosts": sorted(set(guard.blocked)),
    }
    if heard is not None:
        meta.update(
            wav_dir=str(args.wav_dir),
            vad=args.vad,
            stt_model=DEFAULT_MODEL,
            transcripts_file=transcripts_path.name,
            transcripts_sha256=file_sha256(transcripts_path) if transcripts_path.exists() else "",
            spoken={
                "transcribed": sum(1 for r in done if r.get("heard")),
                "empty": sum(1 for r in done if r["status"] == "fail" and not r.get("heard")),
                "no_audio": sum(r["status"] == NO_AUDIO for r in done),
            },
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = write_reports(args, done, summary, meta)
    t = summary["checked"]
    print(
        f"\nchecked {t['rows']}: passed {t['passed']}, failed {t['rows'] - t['passed']}; "
        f"runner errors: {summary['runner_errors']}; "
        f"not checked offline: {summary['not_checked_offline']}"
    )
    print(f"Wrote {md_path}\nWrote {json_path}")
    if summary["no_effect_spec"]:
        ids = ", ".join(r["id"] for r in done if r["status"] == NO_EFFECT_SPEC)
        print(f"\nWARNING: {summary['no_effect_spec']} rows have no effect spec: {ids}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
