import json
from types import SimpleNamespace

import httpx
import pytest

from friday import db
from friday.channels import telegram_bot as tb
from friday.graph import build_graph
from friday.skills.registry import build_registry

OWNER = "111"
STRANGER = "999"
TOKEN = "123:SECRETTOKEN"


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    def send_message(self, chat_id, text):
        if self.fail:
            raise tb.TelegramError("sendMessage: Telegram answered HTTP 500")
        self.sent.append((str(chat_id), text))


class FakeApp:
    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error

    def invoke(self, state):
        if self.error:
            raise self.error
        return {"reply": self.reply, "via": "llm"}


def fake_llm(messages):
    return SimpleNamespace(text="stub reply", provider="stub", model="stub", ms=0)


def update(update_id, chat_id, text=None, **extra):
    message = {"chat": {"id": int(chat_id)}, **extra}
    if text is not None:
        message["text"] = text
    return {"update_id": update_id, "message": message}


def make_client(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return tb.TelegramClient(TOKEN, http=http)


@pytest.fixture
def parts(tmp_path):
    path = tmp_path / "tg.db"
    conn = db.connect(path)
    app = build_graph(conn, build_registry(db_path=path), llm=fake_llm)
    yield conn, app, FakeClient()
    conn.close()


def test_skill_command_from_the_owner_gets_the_skill_reply(parts):
    conn, app, client = parts
    tb.handle_update(update(1, OWNER, "Echo hello Friday."), app, conn, OWNER, client)
    assert client.sent == [(OWNER, "hello friday")]


def test_other_sentences_go_to_the_llm_and_are_saved_as_telegram(parts):
    conn, app, client = parts
    tb.handle_update(update(1, OWNER, "Tell me a fun fact."), app, conn, OWNER, client)
    assert client.sent == [(OWNER, "stub reply")]
    rows = conn.execute("SELECT channel, role FROM messages ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [("telegram", "user"), ("telegram", "assistant")]


def test_messages_from_another_chat_are_ignored_completely(parts):
    conn, app, client = parts
    tb.handle_update(update(1, STRANGER, "Echo hello"), app, conn, OWNER, client)
    assert client.sent == []
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


def test_non_text_message_from_the_owner_gets_the_text_only_reply(parts):
    conn, app, client = parts
    tb.handle_update(update(1, OWNER, voice={"file_id": "x"}), app, conn, OWNER, client)
    assert client.sent == [(OWNER, tb.TEXT_ONLY)]


def test_update_without_a_message_is_skipped(parts):
    conn, app, client = parts
    tb.handle_update({"update_id": 1, "edited_message": {}}, app, conn, OWNER, client)
    assert client.sent == []


def test_a_crash_in_the_graph_gives_a_safe_reply_without_details(parts):
    conn, _, client = parts
    broken = FakeApp(error=RuntimeError("boom: internal details"))
    tb.handle_update(update(1, OWNER, "hello"), broken, conn, OWNER, client)
    assert client.sent == [(OWNER, tb.OOPS)]


def test_long_replies_are_cut_to_the_telegram_limit(parts):
    conn, _, client = parts
    tb.handle_update(update(1, OWNER, "hello"), FakeApp(reply="x" * 5000), conn, OWNER, client)
    assert len(client.sent[0][1]) == tb.MAX_REPLY_CHARS


def test_process_updates_returns_the_next_offset(parts):
    conn, app, client = parts
    updates = [update(5, OWNER, "Echo one"), update(6, OWNER, "Echo two")]
    assert tb.process_updates(updates, None, app, conn, OWNER, client) == 7
    assert tb.process_updates([], 7, app, conn, OWNER, client) == 7


def test_a_failed_send_does_not_stop_the_batch(parts):
    conn, app, _ = parts
    client = FakeClient(fail=True)
    updates = [update(5, OWNER, "Echo one"), update(6, OWNER, "Echo two")]
    assert tb.process_updates(updates, None, app, conn, OWNER, client) == 7


def test_network_error_does_not_leak_the_token():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(tb.TelegramError) as info:
        make_client(handler).send_message("1", "hi")
    assert TOKEN.split(":")[1] not in str(info.value)
    assert info.value.__suppress_context__


def test_http_error_reports_the_status_but_not_the_token():
    def handler(request):
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    with pytest.raises(tb.TelegramError) as info:
        make_client(handler).get_updates(None, timeout=0)
    assert "401" in str(info.value)
    assert TOKEN.split(":")[1] not in str(info.value)


def test_get_updates_returns_the_result_and_sends_the_offset():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 3}]})

    assert make_client(handler).get_updates(3, timeout=0) == [{"update_id": 3}]
    assert seen["offset"] == 3