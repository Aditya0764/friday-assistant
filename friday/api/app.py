"""Friday's HTTP API for the dashboard: /chat (text through the same graph) and /trace.

Run:  python -m uvicorn friday.api.app:app --host 127.0.0.1 --port 8000
Keep it on 127.0.0.1: there is no login, so only this laptop should reach it.

  GET  /health   -> {"status": "ok"}
  POST /chat     -> {"text": "..."} returns reply, run_id, via, skill, provider
  WS   /trace    -> streams trace rows as Friday works; /trace?last=20 replays the last 20 first

Each request opens its own SQLite connection (a connection can't be shared between threads).
Skills here are the ones that need no running service (no reminders or music, like Telegram).
Not built yet: /voice (needs speech to text) and /documents upload (needs the embedder).
The upload will be /documents because FastAPI already uses /docs for its own help page.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from friday import db
from friday.graph import build_graph, run_turn
from friday.history import load_history
from friday.prompt import FRIDAY_PROMPT
from friday.skills.registry import build_registry

MAX_TEXT_CHARS = 2000
TRACE_POLL_SECONDS = 0.3
MAX_REPLAY = 500
EMPTY_REPLY = "Sorry, I have nothing to say to that."


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class ChatOut(BaseModel):
    reply: str
    run_id: str
    via: str  # "rule" or "llm"
    skill: str  # the skill that answered, empty when the LLM did
    provider: str  # the LLM provider, empty when a skill answered


def create_app(db_path: Path | None = None, llm=None) -> FastAPI:
    """Build the API. db_path and llm are for tests; the defaults are the real ones."""
    api = FastAPI(title="Friday API")

    def graph_for(conn):
        registry = build_registry(db_path=db_path)
        extra = {"llm": llm} if llm else {}
        return build_graph(conn, registry, system_prompt=FRIDAY_PROMPT, **extra)

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @api.post("/chat", response_model=ChatOut)
    def chat(body: ChatIn) -> ChatOut:
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="Empty message.")
        conn = db.connect(db_path)
        try:
            history = load_history(conn)  # before saving, so the new message is not sent twice
            db.add_message(conn, "user", text, channel="web")
            state = run_turn(graph_for(conn), text, history)
            reply = (state.get("reply") or "").strip() or EMPTY_REPLY
            db.add_message(conn, "assistant", reply, channel="web")
        except Exception as exc:  # noqa: BLE001 - never leak internal details to the browser
            print(f"/chat failed: {type(exc).__name__}: {str(exc)[:200]}")
            raise HTTPException(status_code=502, detail="Friday couldn't answer right now.") from None
        finally:
            conn.close()
        return ChatOut(
            reply=reply,
            run_id=state["run_id"],
            via=state.get("via", ""),
            skill=state.get("skill_name", ""),
            provider=state.get("provider", ""),
        )

    @api.websocket("/trace")
    async def trace(ws: WebSocket, last: int = 0) -> None:
        conn = db.connect(db_path)
        try:
            newest = conn.execute("SELECT COALESCE(MAX(id), 0) FROM traces").fetchone()[0]
            last_id = max(0, newest - max(0, min(last, MAX_REPLAY)))
            await ws.accept()  # the start point is fixed before accepting, so no row is missed
            while True:
                rows = conn.execute(
                    "SELECT id, run_id, ts, step, input, output, ms "
                    "FROM traces WHERE id > ? ORDER BY id",
                    (last_id,),
                ).fetchall()
                for row in rows:
                    await ws.send_json(dict(row))
                    last_id = row["id"]
                try:
                    # Listening also lets us notice when the browser closes the page.
                    await asyncio.wait_for(ws.receive_text(), timeout=TRACE_POLL_SECONDS)
                except TimeoutError:
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            conn.close()

    return api


app = create_app()