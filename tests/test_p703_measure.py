"""P7-03 measurement script: logic only, with fakes. No network, no models, no real clips."""

import importlib.util
import io
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("p703_measure", ROOT / "scripts" / "p703_measure.py")
p703 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p703)


def wav_bytes(seconds=0.5, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


def turn(row_id, mode, ms, via="rule", routed="lists", error=None, pass_no=1, seq=0, **kw):
    base = {"id": row_id, "mode": mode, "ms": ms, "via": via, "routed": routed, "error": error,
            "pass_no": pass_no, "seq": seq, "bucket": p703.bucket_for(via, [], 0),
            "reply": "ok", "reply_chars": 2, "llm_calls": [], "provider": "",
            "provider_failures": []}
    return {**base, **kw}


# ---------- numbers ----------


def test_p95_is_nearest_rank():
    assert p703.p95(range(1, 31)) == 29  # ceil(0.95*30)=29th smallest
    assert p703.p95([5]) == 5
    assert p703.p95([3, 1, 2]) == 3


def test_stats():
    s = p703.stats([10, 20, 30, 40])
    assert (s["n"], s["mean"], s["median"], s["max"], s["min"]) == (4, 25, 25, 40, 10)
    assert p703.stats([]) == {"n": 0}


@pytest.mark.parametrize(
    ("via", "steps", "calls", "bucket"),
    [
        ("rule", ["router", "safety", "skill", "reply"], 0, "rules skill"),
        ("rule", ["router", "safety", "skill", "reply"], 1, "rules skill + LLM inside"),
        ("model", ["router", "slots", "safety", "skill", "reply"], 1, "model + slot extraction"),
        ("model", ["router", "safety", "skill", "reply"], 0, "model, no slot step"),
        ("llm", ["router", "llm", "reply"], 1, "plain chat LLM"),
        ("", [], 0, "other"),
    ],
)
def test_bucket_for(via, steps, calls, bucket):
    assert p703.bucket_for(via, steps, calls) == bucket


# ---------- pairing and the decision number ----------


def test_pairs_decision_uses_only_via_model_and_lists_differing_routes():
    turns = [
        # rule row: same route, not via=model
        turn("A", "off", 100), turn("A", "on", 110),
        # model row: OFF went to the chat LLM, ON routed to lists via the model
        turn("B", "off", 1000, via="llm", routed="llm"),
        turn("B", "on", 1400, via="model", routed="lists"),
        turn("C", "off", 500, via="llm", routed="llm"),
        turn("C", "on", 700, via="model", routed="reminders"),
        # an errored ON turn is dropped from the pair
        turn("D", "off", 100), turn("D", "on", 9999, error={"kind": "timeout"}),
    ]
    out = p703.analyse_pairs(turns)
    assert out["pairs"] == 3
    assert out["model"]["n"] == 2 and out["model"]["mean"] == 300  # (400 + 200) / 2
    assert out["model_rows"] == 2
    assert out["all"]["mean"] == pytest.approx((10 + 400 + 200) / 3)
    assert [r["id"] for r in out["differing"]] == ["B", "C"]


def test_pairs_need_same_row_and_pass():
    turns = [turn("A", "off", 100, pass_no=1), turn("A", "on", 150, pass_no=2)]
    assert p703.analyse_pairs(turns)["pairs"] == 0


# ---------- the text stage ----------


def test_text_stage_interleaves_alternates_order_and_pauses_outside_timer():
    log = []
    rows = [{"id": "R1"}, {"id": "R2"}, {"id": "R3"}]

    def do_turn(row, clf):
        log.append(("turn", row["id"], clf))
        return turn(row["id"], "x", 1.0)

    turns, complete = p703.run_text_stage(
        rows, {"off": None, "on": "MODEL"}, do_turn, passes=2, pause=1.5,
        sleep=lambda s: log.append(("sleep", s)), say=lambda *_: None)
    assert complete and len(turns) == 12
    warm = log[: 2 * p703.WARMUP_TURNS * 2]  # sleep + turn per warm-up call
    assert [e[1] for e in warm if e[0] == "turn"] == ["R1", "R1", "R2", "R2"]
    assert all(e == ("sleep", 1.5) for e in log if e[0] == "sleep")
    # pass 1 row 0 is OFF first, row 1 is ON first; pass 2 flips
    modes = [(t["pass_no"], t["id"], t["mode"]) for t in turns]
    assert modes[:4] == [(1, "R1", "off"), (1, "R1", "on"), (1, "R2", "on"), (1, "R2", "off")]
    assert modes[6:8] == [(2, "R1", "on"), (2, "R1", "off")]
    assert [t["seq"] for t in turns] == list(range(12))


def test_text_stage_stops_after_three_errors_in_a_row():
    def do_turn(row, clf):
        return turn(row["id"], "x", 1.0, error={"kind": "network"})

    turns, complete = p703.run_text_stage(
        [{"id": "R1"}, {"id": "R2"}], {"off": None, "on": None}, do_turn, 1, 0,
        sleep=lambda s: None, say=lambda *_: None)
    assert not complete and len(turns) == 3


# ---------- real graph, stub LLM (no network, no models) ----------


@pytest.fixture(scope="module")
def runner():
    return p703.load_runner()


def stub_llm(runner):
    def fake_ask(messages):
        return SimpleNamespace(text="Sure.", provider="fake", model="fake-1", ms=1)

    return p703.TimedLLM(fake_ask, runner.describe)


def test_timed_turn_rule_row_and_chat_row(runner):
    llm = stub_llm(runner)
    rule = p703.timed_turn(
        runner, {"id": "T1", "text": "add eggs to my grocery list", "setup": ""}, None, llm,
        runner.stub_embed)
    assert rule["via"] == "rule" and rule["bucket"] == "rules skill"
    assert rule["error"] is None and rule["ms"] > 0 and rule["llm_calls"] == []
    chat = p703.timed_turn(
        runner, {"id": "T2", "text": "tell me a story about a dragon", "setup": ""}, None, llm,
        runner.stub_embed)
    assert chat["bucket"] == "plain chat LLM" and chat["provider"] == "fake"
    assert len(chat["llm_calls"]) == 1 and chat["llm_calls"][0]["provider"] == "fake"


def test_timed_turn_setup_runs_untimed_and_llm_failure_is_recorded(runner):
    def boom(messages):
        raise OSError("network guard: host 'x' is not allowed")

    llm = p703.TimedLLM(boom, runner.describe)
    row = {"id": "T3", "text": "tell me a story", "setup": "Add milk to my shopping list"}
    got = p703.timed_turn(runner, row, None, llm, runner.stub_embed)
    assert got["error"]["kind"] == "blocked_host"
    assert got["llm_calls"][0]["ok"] is False
    # setup's rule-only command did not leave calls in the record of the timed turn
    assert len(got["llm_calls"]) == 1


class FakeSTT:
    def __init__(self, text="add eggs to my grocery list"):
        self.text = text
        self.seen = []

    def transcribe(self, audio, vad=False):
        self.seen.append(vad)
        return SimpleNamespace(text=self.text, ms=1)


class FakeTTS:
    def __init__(self):
        self.texts = []

    def synthesize_wav(self, text):
        self.texts.append(text)
        return wav_bytes(0.25)


def test_full_turn_times_the_whole_chain_with_vad_on(runner):
    stt, tts = FakeSTT(), FakeTTS()
    tick = iter(range(0, 1000, 10))  # fake clock: every read is 10 s later
    rec = p703.full_turn(runner, Path("clip.wav"), "off", None, stub_llm(runner),
                         runner.stub_embed, stt, tts, clock=lambda: next(tick))
    assert stt.seen == [True] and len(tts.texts) == 1 and tts.texts[0]
    assert rec["status"] == "ok"
    assert rec["stt_ms"] == 10_000 and rec["graph_ms"] == 10_000 and rec["tts_ms"] == 10_000
    assert rec["total_ms"] == 30_000  # one timer, not a sum of the parts
    assert "clip.wav" not in repr(rec)


def test_full_turn_empty_transcript_and_error(runner):
    empty = p703.full_turn(runner, Path("c.wav"), "on", None, stub_llm(runner),
                           runner.stub_embed, FakeSTT(""), FakeTTS())
    assert empty["status"] == "empty_transcript" and "total_ms" not in empty

    class BadSTT:
        def transcribe(self, audio, vad=False):
            raise RuntimeError("decode")

    bad = p703.full_turn(runner, Path("c.wav"), "on", None, stub_llm(runner),
                         runner.stub_embed, BadSTT(), FakeTTS())
    assert bad["status"] == "error" and bad["error"]["type"] == "RuntimeError"


def test_full_stage_stops_after_three_errors():
    recs = iter([{"status": "error", "mode": "off"}] * 10)
    turns, ok = p703.run_full_stage(
        [Path(f"{i}.wav") for i in range(5)], {"off": None, "on": None},
        lambda clip, mode, clf: next(recs), 0, sleep=lambda s: None, say=lambda *_: None)
    assert not ok and len(turns) == 3


# ---------- router parts ----------


def test_forward_times_warms_up_and_counts():
    class Clf:
        def __init__(self):
            self.calls = 0

        def classify(self, text):
            self.calls += 1
            return ("other", 0.5)

    clf = Clf()
    out = p703.forward_times(clf, ["a", "b", "c"], repeats=2)
    assert len(out) == 6 and clf.calls == 3 + 6
    with pytest.raises(RuntimeError):
        p703.forward_times(SimpleNamespace(classify=lambda t: None), ["a"], 1)


def test_parse_child_output_takes_last_json_line():
    out = "Router model ready.\n{\"ready_s\": 4.25, \"error\": \"\"}\n"
    assert p703.parse_child_output(out) == {"ready_s": 4.25, "error": ""}
    assert p703.parse_child_output("nothing useful")["ready_s"] is None


# ---------- clips: privacy ----------


def test_find_clips_and_stt_stage_keep_only_numbers(tmp_path):
    for sub, name in (("clips", "secret_name_1.wav"), ("clips_speakers", "secret_name_2.wav")):
        (tmp_path / sub).mkdir()
        (tmp_path / sub / name).write_bytes(wav_bytes(1.0))
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "ignored.wav").write_bytes(wav_bytes(1.0))
    (tmp_path / "clips" / "notes.txt").write_text("x")
    clips = p703.find_clips(tmp_path)
    assert len(clips) == 2
    stt = FakeSTT("private words said by the user")
    clock = iter(x / 10 for x in range(1000))  # each pair of reads is 0.1 s apart
    out = p703.run_stt_stage(stt, clips, repeats=2, clock=lambda: next(clock))
    assert out["clips"] == 2 and len(out["timings_ms"]) == 4
    assert out["timings_ms"][0] == pytest.approx(100)
    assert out["lengths"] == [1.0, 1.0] and all(stt.seen)
    assert "secret_name" not in repr(out) and "private words" not in repr(out)
    assert out["rtf"][0] == pytest.approx(0.1)


def test_stt_stage_without_clips():
    assert p703.run_stt_stage(FakeSTT(), [], 3) == {"clips": 0}


def test_tts_stage_records_chars_and_audio_length():
    tts = FakeTTS()
    out = p703.run_tts_stage(tts, [("R1", "hello there"), ("R2", "ok")], repeats=3)
    assert len(tts.texts) == 1 + 6  # one discarded warm-up
    first = out["items"][0]
    assert first["chars"] == 11 and len(first["ms"]) == 3 and first["audio_s"] == 0.25


# ---------- RAM ----------


def test_peak_sampler_tracks_overall_and_phase_peaks():
    values = iter([10, 50, 30, 20, 99])
    s = p703.PeakSampler(lambda: next(values))
    with s.phase("a"):  # samples 10 on entry, 50 inside, 30 on exit
        s.sample_now()
    s.sample_now()  # 20, outside a phase
    assert s.phase_peaks["a"] == 50 and s.peak == 50
    s.sample_now()  # 99, outside a phase: raises the overall peak only
    assert s.phase_peaks["a"] == 50 and s.peak == 99 and s.samples == 5


def test_peak_sampler_thread_runs_and_stops():
    s = p703.PeakSampler(lambda: 7, interval=0.001)
    s.start()
    s.stop()
    assert s.peak == 7 and s.samples >= 1


def test_load_stages_records_each_load_and_survives_a_failure():
    snaps = iter({"rss": (i + 1) * p703.MIB, "uss": None, "peak_wset": None} for i in range(9))
    mem = SimpleNamespace(snapshot=lambda: next(snaps))

    def broken():
        raise ValueError("no model")

    stages, objs = p703.load_stages(
        [("one", lambda: "A"), ("two", broken), ("three", lambda: "C")], mem, say=lambda *_: None)
    assert [s["name"] for s in stages] == ["one", "two", "three"]
    assert stages[1]["error"] == "ValueError" and "two" not in objs
    assert objs == {"one": "A", "three": "C"} and stages[2]["rss"] == 3 * p703.MIB


# ---------- machine ----------


class FakePsutil:
    class Error(Exception):
        pass

    def __init__(self, battery):
        self._battery = battery

    def sensors_battery(self):
        return self._battery


def test_battery_refused_unless_allowed():
    on_battery = FakePsutil(SimpleNamespace(power_plugged=False, percent=80))
    with pytest.raises(SystemExit):
        p703.check_power(on_battery, allow_battery=False)
    assert p703.check_power(on_battery, allow_battery=True)["plugged"] is False
    plugged = FakePsutil(SimpleNamespace(power_plugged=True, percent=100))
    assert p703.check_power(plugged, False)["plugged"] is True
    assert p703.check_power(FakePsutil(None), False)["battery"] is False


def test_process_groups_sums_by_name_and_keeps_only_names():
    def proc(name, rss):
        return SimpleNamespace(info={"name": name, "memory_info": SimpleNamespace(rss=rss)})

    ps = SimpleNamespace(
        Error=FakePsutil.Error,
        process_iter=lambda attrs: [proc("chrome.exe", 300), proc("chrome.exe", 200),
                                    proc("code.exe", 400), proc("tiny.exe", 1)],
    )
    top = p703.process_groups(ps, top=2)
    assert top == [{"name": "chrome.exe", "rss": 500, "procs": 2},
                   {"name": "code.exe", "rss": 400, "procs": 1}]


# ---------- file name ----------


def test_output_path_refuses_overwrite_and_bad_labels(tmp_path):
    (tmp_path / "p703_taken.md").write_text("x")
    with pytest.raises(SystemExit):
        p703.output_path("taken", tmp_path)
    with pytest.raises(SystemExit):
        p703.output_path("bad label!", tmp_path)
    assert p703.output_path("fresh", tmp_path) == tmp_path / "p703_fresh.md"


# ---------- the report ----------


def make_data(peak_mib=5000):
    mb = p703.MIB
    turns = [
        turn("A", "off", 100, seq=0, bucket="rules skill"), turn("A", "on", 110, seq=1),
        turn("B", "off", 1000, via="llm", routed="llm", seq=2, provider="groq",
             llm_calls=[{"ok": True, "provider": "groq", "model": "m", "ms": 900}]),
        turn("B", "on", 1400, via="model", routed="lists", seq=3, provider="groq",
             bucket="model + slot extraction",
             llm_calls=[{"ok": True, "provider": "groq", "model": "m", "ms": 1200}]),
        turn("C", "off", 500, via="llm", routed="llm", seq=4),
        turn("C", "on", 700, via="model", routed="reminders", seq=5),
    ]
    return {
        "label": "t1", "date": "2026-10-17", "quick": True, "passes": 1, "repeats": 1,
        "pause_s": 1.0, "rows_n": 3, "hosts": ["api.groq.com"], "complete": True,
        "incomplete": [], "imports": ["numpy"],
        "system": {"total": 8000 * mb, "available": 2500 * mb, "cpu_count": 4, "cpu_physical": 2,
                   "cpu_mhz": 2000.0, "cpu_max_mhz": 3000.0, "cpu_percent": 5.0,
                   "power": {"battery": True, "plugged": True, "percent": 90},
                   "python": "3.13", "platform": "Windows-11",
                   "processes": [{"name": "code.exe", "rss": 400 * mb, "procs": 3}],
                   "available_end": 1900 * mb},
        "text_turns": turns,
        "router": {"cold": [{"ready_s": 4.5, "error": ""}], "forward": [10.0, 20.0],
                   "forward_texts": 2, "forward_repeats": 1},
        "stt": {"clips": 2, "lengths": [1.0, 3.0], "timings_ms": [800.0, 1200.0],
                "rtf": [0.8, 0.4], "repeats": 1, "empty_transcripts": 0, "errors": 0},
        "tts": {"items": [{"id": "B", "chars": 40, "ms": [300.0], "audio_s": 2.5}],
                "repeats": 1, "errors": 0},
        "full": [{"mode": "off", "status": "ok", "total_ms": 3333.0, "stt_ms": 900.0,
                  "graph_ms": 1500.0, "tts_ms": 400.0, "error": None},
                 {"mode": "on", "status": "empty_transcript", "error": None}],
        "stages": [{"name": "Whisper base.en", "ms": 1500.0, "error": "", "rss": 700 * mb,
                    "uss": 650 * mb, "peak_wset": None}],
        "ram": {"sampled_peak": 4900 * mb, "samples": 120, "peak_wset": peak_mib * mb,
                "phase_peaks": {"text turns": 4900 * mb}},
    }


def test_report_states_rules_first_and_numbers_come_from_data():
    text = p703.build_report(make_data())
    assert text.index("Decision rules") < text.index("## Conditions") < text.index("## 1.")
    # (a): model pairs B (+400) and C (+200): mean 300, n=2
    assert "n=2 pairs over 2 rows" in text and "**300 ms**" in text
    # all pairs: 10, 400, 200 -> mean 203
    assert "n=3; mean 203 ms" in text
    # (b)
    assert "Rule (b): peak = 5000 MiB, threshold 6144 MiB: NOT ABOVE" in text
    # n=2 model pairs is under 5, so rule (a) gets no verdict
    assert "Rule (a): n too small to apply rule (a)" in text
    assert "No playback, no Bluetooth, WAV ready, not audio start" in text
    assert "3333" in text  # the single-timer total, shown as measured
    assert "not added together" in text and "router-OFF turns ran with it" in text
    assert "p95 is nearest-rank" in text
    assert "| B | 40 | 300 | 2.5 |" in text


def test_report_ram_over_limit_and_no_clip_or_transcript_text():
    text = p703.build_report(make_data(peak_mib=7000))
    assert "Rule (b): peak = 7000 MiB, threshold 6144 MiB: ABOVE" in text
    assert ".wav" not in text and "clips\\" not in text.replace(r"data\clips*", "")


def test_report_partial_and_quick_banners_and_missing_parts():
    data = make_data()
    data.update(complete=False, incomplete=["text turns stopped after 3 errors in a row"])
    data.pop("stt"), data.pop("tts"), data.pop("full")
    text = p703.build_report(data)
    assert "PARTIAL RUN" in text and "QUICK RUN" in text
    assert "No clips found: not measured." in text and "Not measured." in text


# ---------- verdict lines ----------


def model_stats(mean_ms, n):
    return {"n": n, "mean": mean_ms}


def test_verdict_a_above_not_above_and_edge():
    assert p703.verdict_a(model_stats(612.3456, 8)) == (
        "Rule (a): mean added = 0.612 s, n = 8, threshold 0.5 s: ABOVE")
    assert p703.verdict_a(model_stats(120, 5)) == (
        "Rule (a): mean added = 0.120 s, n = 5, threshold 0.5 s: NOT ABOVE")
    assert p703.verdict_a(model_stats(500, 9)).endswith("NOT ABOVE")  # exactly 0.5 s is not MORE
    assert p703.verdict_a(model_stats(-40, 6)).startswith("Rule (a): mean added = -0.040 s")


def test_verdict_a_n_too_small():
    for n in (0, 4):
        line = p703.verdict_a(model_stats(9999, n) if n else {"n": 0})
        assert "n too small to apply rule (a)" in line
        assert "ABOVE" not in line


def test_verdict_b_above_not_above_and_edge():
    mb = p703.MIB
    assert p703.verdict_b(7000 * mb) == "Rule (b): peak = 7000 MiB, threshold 6144 MiB: ABOVE"
    assert p703.verdict_b(5000 * mb) == "Rule (b): peak = 5000 MiB, threshold 6144 MiB: NOT ABOVE"
    assert p703.verdict_b(6144 * mb).endswith("NOT ABOVE")
    assert p703.verdict_b(6144 * mb + 1024 * 1024).endswith(": ABOVE")
    assert "no verdict" in p703.verdict_b(None)


def test_report_verdict_a_above_and_not_above_and_no_recommendation():
    data = make_data()
    # five model pairs: rows M1..M5, each +700 ms (mean 0.700 s)
    extra = []
    for i in range(5):
        extra += [turn(f"M{i}", "off", 1000, via="llm", routed="llm"),
                  turn(f"M{i}", "on", 1700, via="model", routed="lists")]
    data["text_turns"] = extra
    text = p703.build_report(data)
    assert "Rule (a): mean added = 0.700 s, n = 5, threshold 0.5 s: ABOVE" in text
    for i in range(5):
        data["text_turns"][2 * i + 1]["ms"] = 1100
    text = p703.build_report(data)
    assert "Rule (a): mean added = 0.100 s, n = 5, threshold 0.5 s: NOT ABOVE" in text
    assert "turn the router" not in text.lower() and "recommend" not in text.lower()
