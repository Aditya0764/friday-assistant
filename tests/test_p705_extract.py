"""P7-05 extractor: runs on the committed training/*.md and on altered copies. No network, no models."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("p705_extract", ROOT / "scripts" / "p705_extract.py")
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)

FILES = ("finetune_results.md", "eval_report.md", "own_phrasing_results.md")


def texts():
    return [(ROOT / "training" / f).read_text(encoding="utf-8") for f in FILES]


def test_real_files_parse():
    data = ex.extract(*texts())
    r5, r6 = data["router5"], data["router6"]
    assert [c["epoch"] for c in r5["curve"]] == [1, 2, 3, 4]
    assert r5["best_epoch"] == 3
    assert r5["confusion_total"] == r5["test_rows_stated"] == 2974
    assert r5["model"] == "models/router_distilbert"
    assert [(r["correct"], r["total"]) for r in r6["runs"]] == [(62, 90), (77, 90), (73, 90)]
    assert r6["model"] == "models/router_v2" and r6["deployed_run"] == "B"
    assert sum(c["support"] for c in r6["run_b_per_class"]) == 90
    json.dumps(data)


def test_header_change_fails():
    fine, report, own = texts()
    with pytest.raises(ex.ExtractError, match="header changed"):
        ex.extract(fine.replace("| dev macro-F1 |", "| dev F1 |"), report, own)


def test_missing_heading_fails():
    fine, report, own = texts()
    with pytest.raises(ex.ExtractError, match="heading not found"):
        ex.extract(fine, report.replace("## Confusion matrix", "## Matrix"), own)


def test_dropped_row_fails():
    fine, report, own = texts()
    row = next(ln for ln in fine.splitlines() if ln.startswith("| 4 |"))
    with pytest.raises(ex.ExtractError, match="expected 4 epochs"):
        ex.extract(fine.replace(row + "\n", ""), report, own)


def test_non_number_fails():
    fine, report, own = texts()
    with pytest.raises(ex.ExtractError, match="not a number"):
        ex.extract(fine.replace("| 0.3949 |", "| n/a |"), report, own)


def test_run_b_support_must_add_up():
    fine, report, own = texts()
    with pytest.raises(ex.ExtractError, match="does not add up"):
        ex.extract(fine, report, own.replace("9 of 14", "9 of 15"))


def test_main_writes_nothing_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "TRAINING", tmp_path)
    monkeypatch.setattr(ex, "OUT", tmp_path / "out" / "r.json")
    assert ex.main() == 1
    assert not (tmp_path / "out").exists()


def test_main_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "OUT", tmp_path / "out" / "r.json")
    assert ex.main() == 0
    assert json.loads((tmp_path / "out" / "r.json").read_text(encoding="utf-8"))["router6"]["deployed_run"] == "B"
