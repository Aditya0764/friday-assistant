import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from friday import db
from friday.channels import telegram_bot as tb
from friday.graph import build_graph
from friday.skills.registry import build_registry

OWNER = "111"
STRANGER = "999"
SECRET = "SECRETTOKEN"
TOKEN = f"123:{SECRET}"


class FakeClient:
    def __init__(self, fail: bool = False, download_error: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.downloaded: list[str] = []
        self.fail = fail
        self.download_error = download_error

    def send_message(self, chat_id, text):
        if self.fail:
            raise tb.TelegramError("sendMessage: Telegram answered HTTP 500")
        self.sent.append((str(chat_id), text))

    def get_file_path(self, file_id):
        return f"voice/{file_id}.oga"

    def download_file(self, file_path):
        if self.download_error:
            raise tb.TelegramError("download: Telegram answered HTTP 500")
        self.downloaded.append(file_path)
        return b"fake-audio"


class FakeApp:
    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error

    def invoke(self, state):
        if self.error:
            raise self.error
        return {"reply": self.reply, "via": "llm"}


class Transcriber:
    """Stands in for Whisper: records what file it was given and returns fixed text."""

    def __init__(self, text: str = "echo hello friday", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[tuple[str, bytes]] = []

    def __call__(self, path):
        if self.error:
            raise self.error
        self.calls.append((Path(path).name, Path(path).read_bytes()))
        return self.text


def fake_llm(messages):
    return SimpleNamespace(text="stub reply", provider="stub", model="stub", ms=0)


def update(update_id, chat_id, text=None, **extra):
    message = {"chat": {"id": int(chat_id)}, **extra}
    if text is not None:
        message["text"] = text
    return {"update_id": update_id, "message": message}


def voice_update(update_id, chat_id, duration=3):
    return update(update_id, chat_id, voice={"file_id": "abc", "duration": duration})


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


def test_a_photo_gets_the_text_only_reply(parts):
    conn, app, client = parts
    tb.handle_update(update(1, OWNER, photo=[{"file_id": "x"}]), app, conn, OWNER, client)
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


def test_voice_note_is_transcribed_and_answered(parts):
    conn, app, client = parts
    heard = Transcriber()
    tb.handle_update(voice_update(1, OWNER), app, conn, OWNER, client, heard)
    assert client.sent == [(OWNER, 'You said: "echo hello friday"\n\nhello friday')]
    assert heard.calls == [("voice.oga", b"fake-audio")]


def test_voice_turn_is_saved_as_telegram_voice_without_the_you_said_line(parts):
    conn, app, client = parts
    tb.handle_update(voice_update(1, OWNER), app, conn, OWNER, client, Transcriber())
    rows = conn.execute("SELECT channel, role, content FROM messages ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [
        ("telegram_voice", "user", "echo hello friday"),
        ("telegram_voice", "assistant", "hello friday"),
    ]


def test_voice_note_that_is_too_long_is_refused_before_download(parts):
    conn, app, client = parts
    heard = Transcriber()
    update_ = voice_update(1, OWNER, duration=tb.MAX_VOICE_SECONDS + 1)
    tb.handle_update(update_, app, conn, OWNER, client, heard)
    assert client.sent == [(OWNER, tb.VOICE_TOO_LONG)]
    assert client.downloaded == []
    assert heard.calls == []


def test_voice_note_with_no_speech_gets_a_message_and_saves_nothing(parts):
    conn, app, client = parts
    tb.handle_update(voice_update(1, OWNER), app, conn, OWNER, client, Transcriber(text="  "))
    assert client.sent == [(OWNER, tb.NO_SPEECH)]
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


def test_voice_note_from_another_chat_is_ignored_before_download(parts):
    conn, app, client = parts
    tb.handle_update(voice_update(1, STRANGER), app, conn, OWNER, client, Transcriber())
    assert client.sent == []
    assert client.downloaded == []


def test_voice_download_failure_gives_a_safe_reply(parts):
    conn, app, _ = parts
    client = FakeClient(download_error=True)
    tb.handle_update(voice_update(1, OWNER), app, conn, OWNER, client, Transcriber())
    assert client.sent == [(OWNER, tb.OOPS)]


def test_transcription_crash_gives_a_safe_reply_without_details(parts):
    conn, app, client = parts
    broken = Transcriber(error=RuntimeError("boom: internal details"))
    tb.handle_update(voice_update(1, OWNER), app, conn, OWNER, client, broken)
    assert client.sent == [(OWNER, tb.OOPS)]


def test_voice_note_without_a_transcriber_gets_the_text_only_reply(parts):
    conn, app, client = parts
    tb.handle_update(voice_update(1, OWNER), app, conn, OWNER, client)
    assert client.sent == [(OWNER, tb.TEXT_ONLY)]


def test_process_updates_passes_the_transcriber_on(parts):
    conn, app, client = parts
    offset = tb.process_updates([voice_update(8, OWNER)], None, app, conn, OWNER, client, Transcriber())
    assert offset == 9
    assert client.sent[0][1].endswith("hello friday")


def test_network_error_does_not_leak_the_token():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(tb.TelegramError) as info:
        make_client(handler).send_message("1", "hi")
    assert SECRET not in str(info.value)
    assert info.value.__suppress_context__


def test_http_error_reports_the_status_but_not_the_token():
    def handler(request):
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    with pytest.raises(tb.TelegramError) as info:
        make_client(handler).get_updates(None, timeout=0)
    assert "401" in str(info.value)
    assert SECRET not in str(info.value)


def test_get_updates_returns_the_result_and_sends_the_offset():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 3}]})

    assert make_client(handler).get_updates(3, timeout=0) == [{"update_id": 3}]
    assert seen["offset"] == 3


def test_get_file_path_reads_the_result():
    def handler(request):
        return httpx.Response(200, json={"ok": True, "result": {"file_path": "voice/a.oga"}})

    assert make_client(handler).get_file_path("abc") == "voice/a.oga"


def test_download_returns_the_bytes_from_the_file_endpoint():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, content=b"abc")

    assert make_client(handler).download_file("voice/a.oga") == b"abc"
    assert seen["path"] == f"/file/bot{TOKEN}/voice/a.oga"


def test_download_network_error_does_not_leak_the_token():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(tb.TelegramError) as info:
        make_client(handler).download_file("voice/a.oga")
    assert SECRET not in str(info.value)
    assert info.value.__suppress_context__


def test_download_http_error_reports_the_status_only():
    def handler(request):
        return httpx.Response(404)

    with pytest.raises(tb.TelegramError) as info:
        make_client(handler).download_file("voice/a.oga")
    assert "404" in str(info.value)
    assert SECRET not in str(info.value)