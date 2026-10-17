"""The eval runner's database-effect check: expected_effect cells and the "no effect spec" rule."""

import importlib.util
import re
from datetime import datetime
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parent.parent / "evals"
_spec = importlib.util.spec_from_file_location("run_eval_100", EVALS / "run_eval_100.py")
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

NOW = runner.NOW
HEADER = "id,skill,text,setup,expected_skill,expected_result,notes,expected_effect\n"


def at(hour, minute=0, days=0):
    return runner.at(hour, minute, days)


def check(row_id, spec, lists_before, lists_after, rem_before=(), rem_after=()):
    parsed = runner.parse_effect(spec) if spec else None
    return runner.check_effect(
        row_id, lists_before, lists_after, list(rem_before), list(rem_after), parsed
    )


# ---------- parsing ----------


def test_parse_unchanged():
    assert runner.parse_effect("unchanged") == {"lists": None, "reminder": None}


def test_parse_list_is_full_final_state_and_empty_list_means_nothing_left():
    parsed = runner.parse_effect("list:grocery=rice|lentils")
    assert parsed == {"lists": {"grocery": ["rice", "lentils"]}, "reminder": None}
    assert runner.parse_effect("list:shopping=")["lists"] == {}


def test_parse_list_name_to_do_is_todo():
    assert runner.parse_effect("list:to do=call the dentist")["lists"] == {"todo": ["call the dentist"]}


def test_parse_reminder_absolute_and_any():
    due, needle = runner.parse_effect("rem:2026-10-17T10:20|Drink water")["reminder"]
    assert due == at(10, 20) and needle == "drink water"
    assert runner.parse_effect("rem:any|alarm")["reminder"] == (None, "alarm")


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "list:shopping",
        "list:=milk",
        "list:a=1;list:a=2",
        "rem:2026-10-17T10:20",
        "rem:soon|alarm",
        "rem:2026-10-17T10:20+05:30|alarm",
        "rem:any|a;rem:any|b",
        "forget it",
    ],
)
def test_parse_rejects_malformed_cells(bad):
    with pytest.raises(ValueError):
        runner.parse_effect(bad)


# ---------- checking ----------


def test_list_spec_passes_when_right_and_fails_when_not():
    ok, _ = check("HLD-01", "list:shopping=toothpaste", {}, {"shopping": ["toothpaste"]})
    assert ok
    ok, detail = check("HLD-01", "list:shopping=toothpaste", {}, {})
    assert not ok and "lists" in detail


def test_unchanged_spec_fails_when_something_was_saved():
    ok, _ = check("HLD-03", "unchanged", {"packing": ["socks"]}, {"packing": ["socks"]})
    assert ok
    ok, _ = check("HLD-03", "unchanged", {"packing": ["socks"]}, {"packing": []})
    assert not ok


def test_removal_spec_uses_final_state_after_setup():
    before = {"shopping": ["bread", "milk"]}
    assert check("HLD-04", "list:shopping=milk", before, {"shopping": ["milk"]})[0]
    assert not check("HLD-04", "list:shopping=milk", before, before)[0]


def test_list_spec_leaves_reminders_unchanged():
    ok, detail = check("X", "list:notes=a", {}, {"notes": ["a"]}, rem_after=[(at(11), "x")])
    assert not ok and "reminders" in detail


def test_reminder_spec_checks_time_and_text():
    spec = "rem:2026-10-17T10:20|drink water"
    assert check("HLD-07", spec, {}, {}, rem_after=[(at(10, 20), "Drink water")])[0]
    ok, detail = check("HLD-07", spec, {}, {}, rem_after=[(at(10, 30), "drink water")])
    assert not ok and "due" in detail
    ok, detail = check("HLD-07", spec, {}, {}, rem_after=[(at(10, 20), "stretch")])
    assert not ok and "lacks" in detail
    assert not check("HLD-07", spec, {}, {}, rem_after=[])[0]


def test_reminder_any_time_ignores_due_but_needs_exactly_one():
    spec = "rem:any|alarm"
    assert check("HLD-11", spec, {}, {}, rem_after=[(at(19), "alarm")])[0]
    two = [(at(19), "alarm"), (at(7, days=1), "alarm")]
    assert not check("HLD-11", spec, {}, {}, rem_after=two)[0]


def test_reminder_spec_leaves_lists_unchanged():
    ok, _ = check("X", "rem:any|alarm", {}, {"notes": ["a"]}, rem_after=[(at(19), "alarm")])
    assert not ok


def test_builtin_table_still_wins_for_eval_100_ids():
    assert runner.check_effect("LST-01", {}, {"shopping": ["bananas"]}, [], [])[0]
    assert not runner.check_effect("LST-01", {}, {}, [], [])[0]
    assert runner.check_effect("REM-01", {}, {}, [], [(at(17), "buy bread")])[0]
    assert runner.check_effect("CLK-01", {}, {}, [], [])[0]


# ---------- reading the CSV ----------


def write_csv(tmp_path, *rows):
    path = tmp_path / "rows.csv"
    path.write_text(HEADER + "".join(rows), encoding="utf-8")
    return path


def test_read_rows_flags_other_csvs_as_needing_a_spec(tmp_path):
    path = write_csv(tmp_path, 'Z-01,lists,add milk,,lists,"any:",n,list:shopping=milk\n')
    rows = runner.read_rows(path)
    assert rows[0]["effect_required"] is True
    assert runner.read_rows(runner.CSV_PATH)[0]["effect_required"] is False


def test_read_rows_exits_on_bad_spec(tmp_path):
    path = write_csv(tmp_path, 'Z-01,lists,add milk,,lists,"any:",n,list:shopping\n')
    with pytest.raises(SystemExit, match="bad expected_effect"):
        runner.read_rows(path)


def test_read_rows_exits_when_spec_collides_with_builtin(tmp_path):
    path = write_csv(tmp_path, 'LST-01,lists,add milk,,lists,"any:",n,unchanged\n')
    with pytest.raises(SystemExit, match="built-in"):
        runner.read_rows(path)


def test_heldout_csv_has_a_valid_spec_on_every_row():
    rows = runner.read_rows(EVALS / "heldout_30.csv")
    assert len(rows) == 30
    assert all(r["expected_effect"].strip() for r in rows)
    changing = {r["id"] for r in rows if r["expected_effect"] != "unchanged"}
    assert changing == {f"HLD-{n:02d}" for n in (1, 2, 4, 6, 7, 8, 9, 10, 11, 12)}


def test_heldout_todo_regex_accepts_todo_and_to_do():
    row = next(r for r in runner.read_rows(EVALS / "heldout_30.csv") if r["id"] == "HLD-05")
    for reply in (
        "On your todo list: call the dentist.",
        "On your to-do list: call the dentist.",
        "On your to do list: call the dentist.",
    ):
        assert runner.check_reply(row["expected_result"], reply)
    assert not re.search(row["expected_result"][3:], "On your shopping list: call the dentist.")


# ---------- the no-effect-spec rule, end to end (offline stubs) ----------


def make_row(**over):
    row = {
        "id": "Z-01", "skill": "lists", "text": "put toothpaste on my shopping list", "setup": "",
        "expected_skill": "lists", "expected_result": "has:toothpaste", "notes": "n",
        "expected_effect": "", "effect_required": True,
    }
    return {**row, **over}


def test_state_changing_row_without_spec_is_reported_not_passed():
    result = runner.run_row(make_row(), None)
    assert result["status"] == runner.NO_EFFECT_SPEC
    assert result["effect_detail"] == "no effect spec"


def test_same_row_with_right_spec_passes_and_with_wrong_spec_fails():
    good = runner.run_row(make_row(expected_effect="list:shopping=toothpaste"), None)
    assert good["status"] == "pass"
    wrong = runner.run_row(make_row(expected_effect="unchanged"), None)
    assert wrong["status"] == "fail"


def test_read_only_row_without_spec_is_not_flagged():
    row = make_row(
        text="what is the time right now", skill="clock", expected_skill="clock",
        expected_result="has:It is",
    )
    assert runner.run_row(row, None)["status"] == "pass"


def test_row_without_spec_is_fine_in_legacy_csv():
    result = runner.run_row(make_row(effect_required=False), None)
    assert result["status"] == "fail"  # judged as "unchanged", exactly as before


def test_now_is_the_fixed_saturday_ten_am():
    assert NOW == datetime(2026, 10, 17, 10, 0, tzinfo=NOW.tzinfo)
