"""Telegram channel: text messages go through the same graph as voice.

Run: python -m friday.channels.telegram_bot
     python -m friday.channels.telegram_bot --find-chat-id   (one-off: shows your chat id)

The bot answers ONLY the chat in TELEGRAM_CHAT_ID. Messages from any other chat are ignored
without a reply. Without a chat id the bot refuses to start.

Skills here: the ones that need no running service (echo, clock, lists, docs, calc) plus the
LLM. Reminders and music need the voice app's scheduler and Spotify player, so they are not
available from Telegram yet. Voice notes are P5-02, so for now they get a "text only" reply.

The bot token is part of every Telegram URL, so errors are reported without the URL: only
the error type and the HTTP status. Never print the client or the URL.
"""

from __future__ import annotations

import sqlite3
import sys
import time

import httpx

from friday import db
from friday.config import get_settings
from friday.graph import build_graph, run_turn
from friday.prompt import FRIDAY_PROMPT
from friday.skills.registry import build_registry

API_URL = "https://api.telegram.org"
POLL_SECONDS = 30
RETRY_SECONDS = 5
MAX_REPLY_CHARS = 4000  # Telegram's limit is 4096
MEMORY_TURNS = 6  # one turn = your message + Friday's reply
TEXT_ONLY = "I only understand text messages for now."
OOPS = "Sorry, something went wrong on my side."


class TelegramError(Exception):
    """A Telegram call failed. The message never contains the bot token."""


class TelegramClient:
    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
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


def load_history(conn: sqlite3.Connection) -> list[dict]:
    """Last N turns from SQLite, starting on a user message (same rule as the voice loop)."""
    history = db.recent_messages(conn, MEMORY_TURNS * 2)
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


def handle_update(update: dict, app, conn: sqlite3.Connection, allowed_chat_id: str, client) -> None:
    """Handle one Telegram update. Only text from the allowed chat gets a reply."""
    message = update.get("message")
    if not message:
        return
    chat_id = str(message.get("chat", {}).get("id", ""))
    if chat_id != str(allowed_chat_id):
        print("Ignored a message from another chat.")
        return
    text = (message.get("text") or "").strip()
    if not text:
        client.send_message(chat_id, TEXT_ONLY)
        return
    try:
        history = load_history(conn)  # before saving the new message, so it is not sent twice
        db.add_message(conn, "user", text, channel="telegram")
        state = run_turn(app, text, history)
        reply = ((state.get("reply") or "").strip() or OOPS)[:MAX_REPLY_CHARS]
        db.add_message(conn, "assistant", reply, channel="telegram")
        who = state.get("skill_name") or state.get("provider", "llm")
        print(f"Telegram: {text!r} -> {reply!r} (via {state.get('via')}: {who})")
    except Exception as exc:  # noqa: BLE001 - one bad message must not stop the bot
        print(f"Turn failed: {type(exc).__name__}: {str(exc)[:200]}")
        reply = OOPS
    client.send_message(chat_id, reply)


def process_updates(updates: list[dict], offset, app, conn, allowed_chat_id, client):
    """Handle a batch of updates. Returns the offset for the next poll."""
    for update in updates:
        offset = update["update_id"] + 1
        try:
            handle_update(update, app, conn, allowed_chat_id, client)
        except TelegramError as exc:
            print(f"Couldn't send the reply: {exc}")
    return offset


def run(client, app, conn, allowed_chat_id) -> None:
    offset = None
    while True:
        try:
            updates = client.get_updates(offset)
        except TelegramError as exc:
            print(f"Couldn't reach Telegram: {exc}. Retrying in {RETRY_SECONDS} s.")
            time.sleep(RETRY_SECONDS)
            continue
        offset = process_updates(updates, offset, app, conn, allowed_chat_id, client)


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
    print("Telegram bot ready. Ctrl+C to stop.")
    try:
        run(client, app, conn, settings.telegram_chat_id)
    except KeyboardInterrupt:
        print("\nBye.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))