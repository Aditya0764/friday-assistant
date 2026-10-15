"""Telegram channel: text messages and voice notes go through the same graph as voice.

Run: python -m friday.channels.telegram_bot
     python -m friday.channels.telegram_bot --find-chat-id   (one-off: shows your chat id)

The bot answers ONLY the chat in TELEGRAM_CHAT_ID. Messages from any other chat are ignored
without a reply. Without a chat id the bot refuses to start.

Voice notes: Telegram sends OGG/Opus. The file goes to a temporary folder and faster-whisper
reads it (it decodes through PyAV, so no ffmpeg should be needed; untested until the first
real note). The text is handled like a typed message. The reply is text and starts with
what Whisper heard, so a mishearing is easy to spot. The Whisper model loads on the first
voice note (slow once). Notes longer than MAX_VOICE_SECONDS are refused.

Skills here: the ones that need no running service (echo, clock, lists, docs, calc) plus the
LLM. Reminders and music need the voice app's scheduler and Spotify player, so they are not
available from Telegram yet.

The bot token is part of every Telegram URL, so errors are reported without the URL: only
the error type and the HTTP status. Never print the client or a URL.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from friday import db
from friday.config import get_settings
from friday.graph import build_graph, run_turn
from friday.history import load_history
from friday.prompt import FRIDAY_PROMPT
from friday.skills.registry import build_registry

API_URL = "https://api.telegram.org"
POLL_SECONDS = 30
RETRY_SECONDS = 5
MAX_REPLY_CHARS = 4000  # Telegram's limit is 4096
MAX_VOICE_SECONDS = 60
TEXT_ONLY = "I understand text messages and voice notes for now."
VOICE_TOO_LONG = "That voice note is too long. Please keep it under a minute."
NO_SPEECH = "I couldn't hear anything in that voice note."
OOPS = "Sorry, something went wrong on my side."

Transcribe = Callable[[str], str]


class TelegramError(Exception):
    """A Telegram call failed. The message never contains the bot token."""


class TelegramClient:
    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
        self._token = token
        self._base = f"{API_URL}/bot{token}"
        self._http = http or httpx.Client()

    def __repr__(self) -> str:
        return "TelegramClient(...)"

    def _call(self, method: str, payload: dict, timeout: float):
        try:
            resp = self._http.post(f"{self._base}/{method}", json=payload, timeout=timeout)
        except httpx.HTTPError as exc:
            # "from None": the original error carries the URL (and so the token).
            raise TelegramError(f"{method}: network error ({type(exc).__name__})") from None
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if resp.status_code != 200 or not data.get("ok"):
            raise TelegramError(f"{method}: Telegram answered HTTP {resp.status_code}")
        return data.get("result")

    def get_updates(self, offset: int | None, timeout: int = POLL_SECONDS) -> list[dict]:
        payload: dict = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload, timeout + 10) or []

    def send_message(self, chat_id: str, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text}, 15)

    def get_file_path(self, file_id: str) -> str:
        result = self._call("getFile", {"file_id": file_id}, 15)
        path = result.get("file_path") if isinstance(result, dict) else None
        if not path:
            raise TelegramError("getFile: no file path in the answer")
        return path

    def download_file(self, file_path: str) -> bytes:
        try:
            resp = self._http.get(f"{API_URL}/file/bot{self._token}/{file_path}", timeout=60)
        except httpx.HTTPError as exc:
            raise TelegramError(f"download: network error ({type(exc).__name__})") from None
        if resp.status_code != 200:
            raise TelegramError(f"download: Telegram answered HTTP {resp.status_code}")
        return resp.content


def transcribe_file(path: str) -> str:
    """Speech to text with the shared Whisper model (it loads on the first voice note)."""
    from friday.voice.decode import decode_audio_file
    from friday.voice.stt import get_stt

    return get_stt().transcribe(decode_audio_file(path)).text


def _hear_voice(voice: dict, client, transcribe: Transcribe) -> str:
    """Download a voice note, run it through speech to text, return the text."""
    file_path = client.get_file_path(voice["file_id"])
    audio = client.download_file(file_path)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        path = Path(folder) / "voice.oga"
        path.write_bytes(audio)
        return transcribe(str(path)).strip()


def handle_update(
    update: dict,
    app,
    conn: sqlite3.Connection,
    allowed_chat_id: str,
    client,
    transcribe: Transcribe | None = None,
) -> None:
    """Handle one Telegram update. Only the allowed chat gets a reply."""
    message = update.get("message")
    if not message:
        return
    chat_id = str(message.get("chat", {}).get("id", ""))
    if chat_id != str(allowed_chat_id):
        print("Ignored a message from another chat.")
        return

    text = (message.get("text") or "").strip()
    voice = message.get("voice")
    heard = ""  # what Whisper heard, set only for voice notes
    channel = "telegram"
    if not text and voice and transcribe:
        if voice.get("duration", 0) > MAX_VOICE_SECONDS:
            client.send_message(chat_id, VOICE_TOO_LONG)
            return
        try:
            heard = _hear_voice(voice, client, transcribe)
        except Exception as exc:  # noqa: BLE001 - one bad voice note must not stop the bot
            print(f"Voice note failed: {type(exc).__name__}: {str(exc)[:200]}")
            client.send_message(chat_id, OOPS)
            return
        if not heard:
            client.send_message(chat_id, NO_SPEECH)
            return
        text = heard
        channel = "telegram_voice"
    if not text:
        client.send_message(chat_id, TEXT_ONLY)
        return

    try:
        history = load_history(conn)  # before saving the new message, so it is not sent twice
        db.add_message(conn, "user", text, channel=channel)
        state = run_turn(app, text, history)
        reply = ((state.get("reply") or "").strip() or OOPS)[:MAX_REPLY_CHARS]
        db.add_message(conn, "assistant", reply, channel=channel)
        shown = f'You said: "{heard}"\n\n{reply}' if heard else reply
        who = state.get("skill_name") or state.get("provider", "llm")
        print(f"Telegram ({channel}): {text!r} -> {reply!r} (via {state.get('via')}: {who})")
    except Exception as exc:  # noqa: BLE001 - one bad message must not stop the bot
        print(f"Turn failed: {type(exc).__name__}: {str(exc)[:200]}")
        shown = OOPS
    client.send_message(chat_id, shown[:MAX_REPLY_CHARS])


def process_updates(
    updates: list[dict],
    offset,
    app,
    conn,
    allowed_chat_id,
    client,
    transcribe: Transcribe | None = None,
):
    """Handle a batch of updates. Returns the offset for the next poll."""
    for update in updates:
        offset = update["update_id"] + 1
        try:
            handle_update(update, app, conn, allowed_chat_id, client, transcribe)
        except TelegramError as exc:
            print(f"Couldn't send the reply: {exc}")
    return offset


def run(client, app, conn, allowed_chat_id, transcribe: Transcribe | None = None) -> None:
    offset = None
    while True:
        try:
            updates = client.get_updates(offset)
        except TelegramError as exc:
            print(f"Couldn't reach Telegram: {exc}. Retrying in {RETRY_SECONDS} s.")
            time.sleep(RETRY_SECONDS)
            continue
        offset = process_updates(updates, offset, app, conn, allowed_chat_id, client, transcribe)


def find_chat_id(client) -> tuple[str, str]:
    """Wait for the first message to the bot and return (chat id, sender's first name)."""
    print("Send any message to your bot from your phone now. Waiting...")
    offset = None
    while True:
        for update in client.get_updates(offset):
            offset = update["update_id"] + 1
            message = update.get("message")
            if message:
                name = message.get("from", {}).get("first_name", "?")
                return str(message["chat"]["id"]), name


def main(argv: list[str]) -> int:
    settings = get_settings()
    if not settings.telegram_bot_token:
        print("TELEGRAM_BOT_TOKEN is missing in .env.")
        return 1
    client = TelegramClient(settings.telegram_bot_token)

    if "--find-chat-id" in argv[1:]:
        try:
            chat_id, name = find_chat_id(client)
        except TelegramError as exc:
            print(exc)
            return 1
        except KeyboardInterrupt:
            print("\nStopped.")
            return 1
        print(f"Got a message from {name!r}, chat id {chat_id}.")
        print(f"If that is you, add this line to .env:  TELEGRAM_CHAT_ID={chat_id}")
        return 0

    if not settings.telegram_chat_id:
        print("TELEGRAM_CHAT_ID is missing in .env, so the bot doesn't know whose messages to answer.")
        print("Run this once to find it:  python -m friday.channels.telegram_bot --find-chat-id")
        return 1

    conn = db.connect()
    registry = build_registry()  # no scheduler and no Spotify player: those live in the voice app
    app = build_graph(conn, registry, system_prompt=FRIDAY_PROMPT)
    print(f"Skills: {', '.join(registry.names())}")
    print("Reminders and music are not available from Telegram yet.")
    print("Voice notes: on (Whisper loads when the first one arrives, so that one is slow).")
    print("Telegram bot ready. Ctrl+C to stop.")
    try:
        run(client, app, conn, settings.telegram_chat_id, transcribe_file)
    except KeyboardInterrupt:
        print("\nBye.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))