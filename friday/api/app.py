"""Friday's HTTP API for the dashboard.

Run:  python -m uvicorn friday.api.app:app --host 127.0.0.1 --port 8000
Keep it on 127.0.0.1: there is no login, so only this laptop should reach it.

  GET  /health     -> {"status": "ok"}
  POST /chat       -> {"text": "..."} returns reply, run_id, via, skill, provider
  POST /voice      -> an audio file (field "file"): returns what Whisper heard (heard)
                      plus the same fields as /chat
  POST /documents  -> a .pdf, .txt or .md file (field "file"): ingested so Friday can answer
                      questions about it. The first upload loads the embedding model.
  WS   /trace      -> streams trace rows as Friday works; /trace?last=20 replays the last 20

Each request opens its own SQLite connection (a connection can't be shared between threads).
Skills here are the ones that need no running service (no reminders or music, like Telegram).
/voice decodes audio with friday.voice.decode (faster-whisper's own file reader breaks on
PyAV 19) and answers in text; spoken replies in the browser come with the dashboard mic panel.
FastAPI already uses /docs for its own help page, which is why uploads go to /documents.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from friday import db
from friday.graph import build_graph, run_turn
from friday.history import load_history
from friday.prompt import FRIDAY_PROMPT
from friday.rag import store
from friday.rag.ingest import ingest_file
from friday.skills.registry import build_registry
from friday.voice.decode import SAMPLE_RATE, decode_audio_file
from friday.voice.stt import get_stt

MAX_TEXT_CHARS = 2000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_VOICE_SECONDS = 60
TRACE_POLL_SECONDS = 0.3
MAX_REPLAY = 500
EMPTY_REPLY = "Sorry, I have nothing to say to that."

Embed = Callable[[list[str]], np.ndarray]
TranscribeArray = Callable[[np.ndarray], str]


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class ChatOut(BaseModel):
    reply: str
    run_id: str
    via: str  # "rule" or "llm"
    skill: str  # the skill that answered, empty when the LLM did
    provider: str  # the LLM provider, empty when a skill answered


class VoiceOut(ChatOut):
    heard: str  # what speech to text made of the recording


class DocOut(BaseModel):
    id: int
    name: str
    chunks: int


def transcribe_array(audio: np.ndarray) -> str:
    """Speech to text with the shared Whisper model (it loads on the first call)."""
    return get_stt().transcribe(audio).text


def create_app(
    db_path: Path | None = None,
    llm=None,
    embed_fn: Embed | None = None,
    transcribe: TranscribeArray | None = None,
) -> FastAPI:
    """Build the API. The arguments are for tests; the defaults are the real ones."""
    api = FastAPI(title="Friday API")
    hear_audio = transcribe or transcribe_array

    def graph_for(conn):
        registry = build_registry(db_path=db_path)
        extra = {"llm": llm} if llm else {}
        return build_graph(conn, registry, system_prompt=FRIDAY_PROMPT, **extra)

    def run_chat(text: str, channel: str) -> ChatOut:
        """One turn through the graph, saved to the database under `channel`."""
        conn = db.connect(db_path)
        try:
            history = load_history(conn)  # before saving, so the new message is not sent twice
            db.add_message(conn, "user", text, channel=channel)
            state = run_turn(graph_for(conn), text, history)
            reply = (state.get("reply") or "").strip() or EMPTY_REPLY
            db.add_message(conn, "assistant", reply, channel=channel)
        except Exception as exc:  # noqa: BLE001 - never leak internal details to the browser
            print(f"{channel} turn failed: {type(exc).__name__}: {str(exc)[:200]}")
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

    def read_upload(file: UploadFile) -> bytes:
        data = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="That file is too big.")
        if not data:
            raise HTTPException(status_code=400, detail="The file is empty.")
        return data

    def hear(data: bytes) -> str:
        """Audio bytes -> text. Raises HTTPException with a safe message on any problem."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            path = Path(folder) / "audio.bin"
            path.write_bytes(data)
            try:
                audio = decode_audio_file(path)
            except Exception as exc:  # noqa: BLE001 - any decoder error means "not usable audio"
                print(f"/voice decode failed: {type(exc).__name__}")
                raise HTTPException(status_code=400, detail="Couldn't read that audio.") from None
        if len(audio) / SAMPLE_RATE > MAX_VOICE_SECONDS:
            raise HTTPException(status_code=413, detail="That recording is too long.")
        try:
            text = hear_audio(audio).strip()
        except Exception as exc:  # noqa: BLE001 - never leak internal details to the browser
            print(f"/voice transcription failed: {type(exc).__name__}: {str(exc)[:200]}")
            raise HTTPException(status_code=502, detail="Couldn't transcribe that.") from None
        if not text:
            raise HTTPException(status_code=422, detail="I couldn't hear anything in that.")
        return text

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @api.post("/chat", response_model=ChatOut)
    def chat(body: ChatIn) -> ChatOut:
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="Empty message.")
        return run_chat(text, "web")

    @api.post("/voice", response_model=VoiceOut)
    def voice(file: UploadFile) -> VoiceOut:
        heard = hear(read_upload(file))
        out = run_chat(heard, "web_voice")
        return VoiceOut(**out.model_dump(), heard=heard)

    @api.post("/documents", response_model=DocOut)
    def upload_document(file: UploadFile) -> DocOut:
        name = Path(file.filename or "").name  # drop any folders from the name
        if not name:
            raise HTTPException(status_code=400, detail="The file needs a name.")
        data = read_upload(file)
        extra = {"embed_fn": embed_fn} if embed_fn else {}
        conn = db.connect(db_path)
        try:
            store.ensure_tables(conn)
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
                path = Path(folder) / name
                path.write_bytes(data)
                doc_id = ingest_file(conn, path, **extra)
            doc = next(d for d in store.list_documents(conn) if d["id"] == doc_id)
        except ValueError as exc:  # our own messages: unsupported type, no text, already added
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except OSError:
            raise HTTPException(status_code=400, detail="That file name isn't usable.") from None
        except Exception as exc:  # noqa: BLE001 - never leak internal details to the browser
            print(f"/documents failed: {type(exc).__name__}: {str(exc)[:200]}")
            raise HTTPException(status_code=502, detail="Couldn't add that document.") from None
        finally:
            conn.close()
        return DocOut(id=doc["id"], name=doc["name"], chunks=doc["chunk_count"])

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