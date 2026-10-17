"""P7-04 spoken test of held-out set #2: recorder and --wav-dir mode, with fakes only.
No microphone, no network, no models, no real recordings."""

import importlib.util
import io
import json
import re
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rec = load("record_heldout2", ROOT / "scripts" / "record_heldout2.py")
runner = load("run_eval_100_p704", ROOT / "evals" / "run_eval_100.py")


# ---------- fakes ----------


class FakeHub:
    """Like MicHub: read() gives int16 chunks of 1280, then None."""

    def __init__(self, chunks=3, level=2000):
        self.queue = [np.full(1280, level, dtype=np.int16) for _ in range(chunks)]
        self.dropped = 0
        self.overflows = 0
        self.flushed = 0

    def flush(self):
        self.flushed += 1

    def read(self, timeout=1.0):
        return self.queue.pop(0) if self.queue else None


class Answers:
    """Stands in for input(): returns the scripted answers in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def __call__(self, prompt=""):
        self.prompts.append(prompt)
        return self.answers.pop(0)


class FakeSTT:
    """Like Friday's SpeechToText: a path is NOT acceptable, only a float32 array."""

    def __init__(self, text="add eggs to my grocery list"):
        self.text = text
        self.vads = []

    def transcribe(self, audio, vad=False):
        if isinstance(audio, (str, Path)):
            raise TypeError("open() got an unexpected keyword argument 'metadata_errors'")
        assert isinstance(audio, np.ndarray) and audio.dtype == np.float32
        self.vads.append(vad)
        return SimpleNamespace(text=self.text, ms=1)


def fake_decode(path):
    return np.zeros(16000, dtype=np.float32)


def wav_file(path, seconds=0.5, rate=16000, byte=b"\x01\x00"):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(byte * int(seconds * rate))
    Path(path).write_bytes(buf.getvalue())


def row(row_id="R1", text="add eggs to my grocery list", **kw):
    base = {"id": row_id, "skill": "lists", "text": text, "setup": "", "expected_skill": "lists",
            "expected_result": "any:", "notes": "exact", "expected_effect": "list:grocery=eggs",
            "effect_required": True}
    return {**base, **kw}


# ---------- recorder ----------


def test_real_txt_matches_csv_rows():
    sentences = rec.load_sentences()
    assert len(sentences) == 30 and sentences[0][0] == "HLD2-01" and sentences[-1][0] == "HLD2-30"


def test_txt_csv_mismatch_aborts(tmp_path):
    txt, csv_path = tmp_path / "a.txt", tmp_path / "a.csv"
    txt.write_text("hello there\n", encoding="utf-8")
    csv_path.write_text("id,text\nHLD2-01,something else\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        rec.load_sentences(txt, csv_path)


def test_record_saves_16k_mono_16bit_wav(tmp_path):
    ask = Answers("", "")  # Enter to start, Enter to stop
    hub = FakeHub(chunks=3)
    counts = rec.run([("HLD2-01", "add eggs")], tmp_path, set(), hub, ask=ask, say=lambda *_: None)
    assert counts["recorded"] == 1 and hub.flushed == 1
    with wave.open(str(tmp_path / "HLD2-01.wav")) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
        assert w.getnframes() == 3 * 1280


def test_existing_wav_is_never_overwritten_without_redo(tmp_path):
    wav_file(tmp_path / "HLD2-01.wav", byte=b"\x07\x00")
    before = (tmp_path / "HLD2-01.wav").read_bytes()
    ask = Answers()  # must not be asked anything
    counts = rec.run([("HLD2-01", "x")], tmp_path, set(), FakeHub(), ask=ask, say=lambda *_: None)
    assert counts["existing"] == 1 and ask.prompts == []
    assert (tmp_path / "HLD2-01.wav").read_bytes() == before


def test_redo_replaces_and_leaves_no_temp_file(tmp_path):
    wav_file(tmp_path / "HLD2-01.wav", seconds=0.1)
    old = (tmp_path / "HLD2-01.wav").read_bytes()
    rec.run([("HLD2-01", "x")], tmp_path, {"HLD2-01"}, FakeHub(chunks=2),
            ask=Answers("", ""), say=lambda *_: None)
    assert (tmp_path / "HLD2-01.wav").read_bytes() != old
    assert [p.name for p in tmp_path.iterdir()] == ["HLD2-01.wav"]


def test_skip_quit_and_resume(tmp_path):
    sentences = [("HLD2-01", "a"), ("HLD2-02", "b"), ("HLD2-03", "c")]
    counts = rec.run(sentences, tmp_path, set(), FakeHub(), say=lambda *_: None,
                     ask=Answers("s", "", "", "q"))
    assert counts["skipped"] == 1 and counts["recorded"] == 1
    assert [p.name for p in tmp_path.iterdir()] == ["HLD2-02.wav"]
    # resume: 02 exists, 01 and 03 are asked again
    counts = rec.run(sentences, tmp_path, set(), FakeHub(), say=lambda *_: None,
                     ask=Answers("", "", "", ""))
    assert counts["existing"] == 1 and counts["recorded"] == 2


def test_short_silent_and_lossy_takes_warn_but_save(tmp_path):
    said = []
    hub = FakeHub(chunks=1, level=0)
    hub.dropped = 2
    rec.run([("HLD2-01", "x")], tmp_path, set(), hub, ask=Answers("", ""), say=said.append)
    text = " ".join(said)
    assert "very short" in text and "lost audio" in text and (tmp_path / "HLD2-01.wav").exists()
    said.clear()
    rec.run([("HLD2-02", "x")], tmp_path, set(), FakeHub(chunks=10, level=0),
            ask=Answers("", ""), say=said.append)
    assert "almost silent" in " ".join(said)


# ---------- transcripts and the cache ----------


def make_wavs(tmp_path, ids=("R1", "R2")):
    for i in ids:
        wav_file(tmp_path / f"{i}.wav")


def test_stt_only_gets_arrays_and_vad_is_passed_through(tmp_path):
    make_wavs(tmp_path, ["R1"])
    stt = FakeSTT()
    out = runner.transcribe_rows([row("R1")], tmp_path, lambda: stt, fake_decode, False,
                                 tmp_path / "c.json", "base.en", say=lambda *_: None)
    assert out["R1"]["heard"] == "add eggs to my grocery list" and stt.vads == [False]
    with pytest.raises(TypeError):
        stt.transcribe(tmp_path / "R1.wav", vad=True)


def test_runner_source_never_hands_a_path_to_the_stt():
    source = (ROOT / "evals" / "run_eval_100.py").read_text(encoding="utf-8")
    first_args = re.findall(r"\.transcribe\((\w+)", source)
    assert first_args == ["audio"]


def test_second_pass_uses_cache_and_never_builds_the_stt(tmp_path):
    make_wavs(tmp_path)
    cache = tmp_path / "heard.json"
    rows = [row("R1"), row("R2")]
    first = runner.transcribe_rows(rows, tmp_path, lambda: FakeSTT("first text"), fake_decode,
                                   True, cache, "base.en", say=lambda *_: None)

    def never():
        raise AssertionError("the STT must not be loaded on the second pass")

    second = runner.transcribe_rows(rows, tmp_path, never, fake_decode, True, cache, "base.en",
                                    say=lambda *_: None)
    assert {k: v["heard"] for k, v in first.items()} == {k: v["heard"] for k, v in second.items()}
    assert all(v["detail"] == "cached" for v in second.values())
    assert [p.name for p in tmp_path.glob("*.tmp")] == []


def test_changed_wav_vad_or_model_is_transcribed_again_with_a_warning(tmp_path):
    make_wavs(tmp_path, ["R1"])
    cache = tmp_path / "heard.json"
    args = (tmp_path, lambda: FakeSTT("old"), fake_decode)
    runner.transcribe_rows([row("R1")], *args, True, cache, "base.en", say=lambda *_: None)
    said = []
    wav_file(tmp_path / "R1.wav", byte=b"\x09\x00")  # re-recorded
    out = runner.transcribe_rows([row("R1")], tmp_path, lambda: FakeSTT("new"), fake_decode, True,
                                 cache, "base.en", say=said.append)
    assert out["R1"]["heard"] == "new" and "OLD text" in " ".join(said)
    out = runner.transcribe_rows([row("R1")], tmp_path, lambda: FakeSTT("novad"), fake_decode,
                                 False, cache, "base.en", say=lambda *_: None)
    assert out["R1"]["heard"] == "novad"
    out = runner.transcribe_rows([row("R1")], tmp_path, lambda: FakeSTT("m2"), fake_decode, False,
                                 cache, "tiny.en", say=lambda *_: None)
    assert out["R1"]["heard"] == "m2"


def test_missing_and_undecodable_wavs_are_no_audio(tmp_path):
    wav_file(tmp_path / "R2.wav")

    def decode(path):
        raise ValueError("no audio")

    out = runner.transcribe_rows([row("R1"), row("R2")], tmp_path, FakeSTT, decode, True,
                                 tmp_path / "c.json", "base.en", say=lambda *_: None)
    assert out["R1"]["state"] == out["R2"]["state"] == "no_audio"
    assert "ValueError" in out["R2"]["detail"]


# ---------- spoken rows ----------


def spoken_rows(heard_map, rows):
    return runner.run_all_spoken(rows, heard_map, None, None, say=lambda *_: None)


def ok(text):
    return {"state": "ok", "heard": text, "detail": "x"}


def test_empty_result_has_the_same_keys_as_run_row():
    real = runner.run_row(row("R1", expected_effect="list:grocery=eggs"), None)
    fake = runner.empty_result(row("R1"), "fail", "empty transcript")
    assert set(fake) == set(real)


def test_spoken_run_scores_heard_text_and_keeps_typed_sentence():
    done, complete = spoken_rows({"R1": ok("add eggs to my grocery list")}, [row("R1")])
    r = done[0]
    assert complete and r["status"] == "pass"
    assert r["text"] == "add eggs to my grocery list" and r["heard"] == "add eggs to my grocery list"


def test_misheard_row_fails_on_the_transcript():
    done, _ = spoken_rows({"R1": ok("what time is it")}, [row("R1")])
    r = done[0]
    assert r["status"] == "fail" and r["heard"] == "what time is it"
    assert r["text"] == "add eggs to my grocery list" and r["routed"] == "clock"


def test_empty_transcript_is_a_counted_failure_and_graph_not_called(monkeypatch):
    monkeypatch.setattr(runner, "run_row", lambda *a, **k: pytest.fail("graph must not run"))
    done, _ = spoken_rows({"R1": ok("")}, [row("R1")])
    assert done[0]["status"] == "fail" and done[0]["heard"] == ""
    summary = runner.summarize(done)
    assert summary["checked"]["rows"] == 1 and summary["checked"]["passed"] == 0


def test_no_audio_is_left_out_of_the_totals(monkeypatch):
    monkeypatch.setattr(runner, "run_row", lambda *a, **k: pytest.fail("graph must not run"))
    heard = {"R1": {"state": "no_audio", "heard": "", "detail": "no WAV file"}}
    done, _ = spoken_rows(heard, [row("R1")])
    assert done[0]["status"] == "no_audio"
    summary = runner.summarize(done)
    assert summary["checked"]["rows"] == 0 and summary["runner_errors"] == 0


def test_off_and_on_see_identical_text(tmp_path, monkeypatch):
    make_wavs(tmp_path, ["R1"])
    cache = tmp_path / "heard.json"
    rows = [row("R1")]
    stts = [FakeSTT("first"), FakeSTT("DIFFERENT")]
    seen = []
    monkeypatch.setattr(runner, "run_row",
                        lambda r, c, p=None: seen.append(r["text"]) or runner.empty_result(r, "fail", "x"))
    for mode in ("off", "on"):
        heard = runner.transcribe_rows(rows, tmp_path, lambda: stts.pop(0), fake_decode, True,
                                       cache, "base.en", say=lambda *_: None)
        runner.run_all_spoken(rows, heard, mode, None, say=lambda *_: None)
    assert seen == ["first", "first"] and len(stts) == 1


# ---------- reports ----------


def write(tmp_path, label, rows, meta_extra):
    args = SimpleNamespace(label=label, out_dir=tmp_path, router_model=False)
    meta = {"date": "2026-10-18", "live_llm": False, "complete": True, "rows_run": len(rows),
            "rows_total": len(rows), "blocked_hosts": [], **meta_extra}
    summary = runner.summarize(rows)
    return runner.write_reports(args, rows, summary, meta)


def test_spoken_report_has_heard_column_and_no_audio_section(tmp_path):
    heard = {"R1": ok("add eggs to my grocery list"), "R2": ok("what time is it"),
             "R3": ok(""), "R4": {"state": "no_audio", "heard": "", "detail": "no WAV file"}}
    rows = [row(i) for i in heard]
    done, _ = spoken_rows(heard, rows)
    meta = {"wav_dir": "data/spoken/x", "vad": True, "stt_model": "base.en",
            "transcripts_file": "h.json", "transcripts_sha256": "ab" * 32,
            "spoken": {"transcribed": 2, "empty": 1, "no_audio": 1}}
    json_path, md_path = write(tmp_path, "sp", done, meta)
    text = md_path.read_text(encoding="utf-8")
    assert "| Id | Status | Text | Heard | Routed | Reply |" in text
    assert "| Id | Text | Heard | Wanted | Routed | Reply | Why |" in text
    assert "empty transcript" in text and "## No audio" in text and "R4" in text
    assert "1 empty transcripts counted as failures, 1 with no audio" in text
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert [r["heard"] for r in saved["rows"]] == ["add eggs to my grocery list", "what time is it",
                                                  "", ""]


def test_typed_report_is_unchanged_by_the_spoken_additions(tmp_path):
    done, _ = runner.run_all([row("R1")], None, say=lambda *_: None)
    _, md_path = write(tmp_path, "typed", done, {})
    text = md_path.read_text(encoding="utf-8")
    assert "Heard" not in text and "No audio" not in text and "Spoken test" not in text
    assert "| Id | Status | Text | Routed | Reply |" in text
    assert "| Id | Text | Wanted | Routed | Reply | Why |" in text
    assert "heard" not in done[0]
