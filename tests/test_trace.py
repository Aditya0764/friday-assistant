import pytest

from friday import db
from friday.trace import Tracer


def test_step_is_logged_with_output(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    tracer = Tracer(conn)
    with tracer.step("demo", "in") as out:
        out["output"] = "done"
    rows = db.get_traces(conn, tracer.run_id)
    assert len(rows) == 1
    assert rows[0]["step"] == "demo"
    assert rows[0]["input"] == "in"
    assert rows[0]["output"] == "done"
    assert rows[0]["ms"] >= 0


def test_failing_step_is_logged_and_reraised(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    tracer = Tracer(conn)
    with pytest.raises(ValueError), tracer.step("fails", "x"):
        raise ValueError("boom")
    rows = db.get_traces(conn, tracer.run_id)
    assert rows[0]["output"] == "ERROR: boom"