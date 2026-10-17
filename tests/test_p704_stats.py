"""P7-04 router stats script: fakes only. No real result files, no network, no models."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("p704_stats", ROOT / "scripts" / "p704_stats.py")
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)


def row(trace, routed, status="pass", calls=0, expected="lists"):
    return {
        "router_trace": trace,
        "routed": routed,
        "status": status,
        "llm_calls": [{"ok": True}] * calls,
        "expected_skill": expected,
    }


MIXED = [
    row("rule: lists", "lists"),
    row("rule: calc", "calc", "fail", expected="calc"),
    row("rule: docs", "docs", calls=1, expected="docs"),
    row("rule: docs", "docs", expected="docs"),
    row("model: catch [model lists_notes 1.00]", "lists", calls=1),
    row("model: catch [model timers_reminders 1.00]", "catch", "fail", calls=1, expected="reminders"),
    row("rule: catch [model other 1.00]", "catch", expected="catch"),
    row("llm: llm [model other 0.99]", "llm", calls=1, expected="llm"),
    row("llm: llm", "llm", calls=1, expected="llm"),
]


def write_inputs(d, rows_by_file=None):
    d.mkdir(exist_ok=True)
    for name, _ in stats.INPUTS:
        rows = (rows_by_file or {}).get(name, MIXED)
        (d / name).write_text(json.dumps({"meta": {}, "summary": {}, "rows": rows}), encoding="utf-8")


def test_classify_each_category():
    got = [stats.classify(r) for r in MIXED]
    assert got == ["A", "A", "DOCS", "A", "B", "C2", "C1", "D", "D"]


def test_counts_and_passes():
    text = "\n".join(stats.file_section("x.json", "development set", MIXED))
    assert "n rows = 9" in text
    assert "(via=rule, routed skill is not catch) | 3 | 3/9 = 33.3% | 2/3 |" in text
    assert "(via=rule, routed=docs, llm_calls > 0) | 1 | 1/9 = 11.1% | 1/1 |" in text
    assert "(via=model, a real skill answered) | 1 | 1/9 = 11.1% | 1/1 |" in text
    assert "(via=rule, routed=catch) | 1 | 1/9 = 11.1% | 1/1 |" in text
    assert "(via=model, routed=catch) | 1 | 1/9 = 11.1% | 0/1 |" in text
    assert "(via=llm) | 2 | 2/9 = 22.2% | 2/2 |" in text


def test_abc_sentence():
    text = "\n".join(stats.file_section("x.json", "l", MIXED))
    assert "This is not the same as correct actions." in text


def test_exact_abc_numbers():
    # A: lists, calc, docs(0 calls) = 3; B = 1; C = 2; docs-skill = 1; D = 2
    text = "\n".join(stats.file_section("x.json", "l", MIXED))
    assert "A + B + C = 6/9 = 66.7%" in text
    assert "A + B + C + docs-skill = 7/9 = 77.8%" in text


def test_no_llm_call_line():
    text = "\n".join(stats.file_section("x.json", "l", MIXED))
    assert "(len(llm_calls) == 0): 4/9 = 44.4%" in text


def test_slot_call_distribution_is_reported_not_assumed():
    rows = [row("model: catch [model music 1.00]", "music", calls=0, expected="music")]
    text = "\n".join(stats.file_section("x.json", "l", rows))
    assert "B rows by number of LLM calls: {0: 1}" in text


def test_crosstab_raw_counts():
    text = "\n".join(stats.file_section("x.json", "l", MIXED))
    assert "Model class vs expected skill (raw counts)" in text
    assert "| model class | catch | lists | llm | reminders | total |" in text
    assert "| lists_notes | 0 | 1 | 0 | 0 | 1 |" in text
    assert "| other | 1 | 0 | 1 | 0 | 2 |" in text
    assert "agree" not in text.lower()


def test_crosstab_skipped_without_model_class():
    rows = [row("rule: lists", "lists"), row("llm: llm", "llm", calls=1)]
    text = "\n".join(stats.file_section("x.json", "l", rows))
    assert "no model class recorded in this file, skipped" in text


def test_unclassified_fails_totals():
    with pytest.raises(stats.StatsError):
        stats.file_section("x.json", "l", [row("garbage", "lists")])
    with pytest.raises(stats.StatsError):
        stats.file_section("x.json", "l", [])


def test_other_status_not_counted_as_passed():
    rows = [row("rule: lists", "lists", status="error")]
    text = "\n".join(stats.file_section("x.json", "l", rows))
    assert "other than pass/fail" in text
    assert "| 1 | 1/1 = 100.0% | 0/1 |" in text


def test_counts_next_to_every_percentage():
    text = "\n".join(stats.file_section("x.json", "l", MIXED))
    for pct in re.findall(r"\S+ = \d+\.\d%", text):
        assert re.match(r"\d+/\d+ = ", pct)
    assert not re.search(r"(?<![/=] )\b\d+\.\d%", text.replace("= ", "=_"))


def test_report_has_definitions_and_labels(tmp_path):
    write_inputs(tmp_path / "r")
    report = stats.build_report(tmp_path / "r")
    assert "fixed before any" in report and "18 Oct 2026" in report
    assert "Input: development set." in report
    assert "Input: typed held-out, clean." in report
    assert "Input: spoken, one speaker, read from a screen." in report


def test_main_writes_once_then_refuses(tmp_path, capsys):
    write_inputs(tmp_path / "r")
    out = tmp_path / "p704_stats.md"
    assert stats.main(["--results-dir", str(tmp_path / "r"), "--out", str(out)]) == 0
    first = out.read_text(encoding="utf-8")
    assert stats.main(["--results-dir", str(tmp_path / "r"), "--out", str(out)]) == 1
    assert out.read_text(encoding="utf-8") == first
    assert "refusing to overwrite" in capsys.readouterr().err


def test_existing_output_untouched(tmp_path):
    write_inputs(tmp_path / "r")
    out = tmp_path / "p704_stats.md"
    out.write_text("keep me", encoding="utf-8")
    assert stats.main(["--results-dir", str(tmp_path / "r"), "--out", str(out)]) == 1
    assert out.read_text(encoding="utf-8") == "keep me"


def test_failed_totals_write_nothing(tmp_path):
    bad = {stats.INPUTS[3][0]: [row("garbage", "lists")]}
    write_inputs(tmp_path / "r", bad)
    out = tmp_path / "p704_stats.md"
    assert stats.main(["--results-dir", str(tmp_path / "r"), "--out", str(out)]) == 1
    assert not out.exists()


def test_missing_input_writes_nothing(tmp_path):
    write_inputs(tmp_path / "r")
    (tmp_path / "r" / stats.INPUTS[0][0]).unlink()
    out = tmp_path / "p704_stats.md"
    assert stats.main(["--results-dir", str(tmp_path / "r"), "--out", str(out)]) == 1
    assert not out.exists()
