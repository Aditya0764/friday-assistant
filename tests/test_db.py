from friday import db


def test_tables_are_created(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    names = {row["name"] for row in rows}
    assert {"messages", "reminders", "list_items", "traces", "documents"} <= names


def test_messages_round_trip_in_order(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.add_message(conn, "user", "hi")
    db.add_message(conn, "assistant", "hello")
    assert db.recent_messages(conn) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_recent_messages_respects_limit(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for i in range(5):
        db.add_message(conn, "user", f"m{i}")
    contents = [m["content"] for m in db.recent_messages(conn, limit=2)]
    assert contents == ["m3", "m4"]


def test_traces_round_trip_per_run(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.add_trace(conn, "r1", "llm", "hi", "hello", 12)
    db.add_trace(conn, "r2", "other", "x", "y", 1)
    rows = db.get_traces(conn, "r1")
    assert rows == [{"step": "llm", "input": "hi", "output": "hello", "ms": 12}]