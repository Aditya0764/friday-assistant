from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from friday import db
from friday.api.app import create_app


def fake_llm(messages):
    return SimpleNamespace(text="stub reply", provider="stub", model="stub", ms=0)


def broken_llm(messages):
    raise RuntimeError("secret internal details")


def seed(path, count):
    conn = db.connect(path)
    for i in range(1, count + 1):
        db.add_trace(conn, "run1", f"step{i}", "in", "out", i)
    conn.close()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "api.db"


@pytest.fixture
def client(db_path):
    return TestClient(create_app(db_path=db_path, llm=fake_llm))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_chat_skill_command(client):
    resp = client.post("/chat", json={"text": "Echo hello Friday."})
    body = resp.json()
    assert resp.status_code == 200
    assert body["reply"] == "hello friday"
    assert body["via"] == "rule"
    assert body["skill"] == "echo"
    assert body["run_id"]


def test_chat_llm_path_and_messages_saved_as_web(client, db_path):
    body = client.post("/chat", json={"text": "Tell me a fun fact."}).json()
    assert body["reply"] == "stub reply"
    assert body["via"] == "llm"
    assert body["provider"] == "stub"
    conn = db.connect(db_path)
    rows = conn.execute("SELECT channel, role FROM messages ORDER BY id").fetchall()
    conn.close()
    assert [tuple(r) for r in rows] == [("web", "user"), ("web", "assistant")]


@pytest.mark.parametrize("payload", [{"text": "   "}, {"text": ""}, {}, {"text": "x" * 2001}])
def test_chat_rejects_bad_input(client, payload):
    assert client.post("/chat", json=payload).status_code == 422


def test_chat_failure_gives_502_without_internal_details(db_path):
    broken = TestClient(create_app(db_path=db_path, llm=broken_llm))
    resp = broken.post("/chat", json={"text": "Tell me a fun fact."})
    assert resp.status_code == 502
    assert "secret" not in resp.text


def test_chat_remembers_the_previous_turn(db_path):
    seen = []

    def spy_llm(messages):
        seen.append(messages)
        return SimpleNamespace(text="stub reply", provider="stub", model="stub", ms=0)

    spy = TestClient(create_app(db_path=db_path, llm=spy_llm))
    spy.post("/chat", json={"text": "Tell me a fun fact."})
    spy.post("/chat", json={"text": "Is it true?"})
    # system prompt + (user, assistant) from the first turn + the new question
    assert len(seen[1]) == 4
    assert seen[1][1]["content"] == "Tell me a fun fact."


def test_trace_replays_the_last_rows_in_order(client, db_path):
    seed(db_path, 3)
    with client.websocket_connect("/trace?last=2") as ws:
        rows = [ws.receive_json(), ws.receive_json()]
    assert [r["step"] for r in rows] == ["step2", "step3"]
    assert rows[0]["run_id"] == "run1"
    assert rows[1]["ms"] == 3


def test_trace_streams_rows_that_arrive_after_connecting(client, db_path):
    seed(db_path, 2)  # old rows: must not be sent
    with client.websocket_connect("/trace") as ws:
        seed(db_path, 1)  # a new row (named step1) arrives while connected
        row = ws.receive_json()
    assert row["step"] == "step1"
    assert row["id"] == 3