"""Voice loop: hold key -> mic -> STT -> graph (router, skill or LLM) -> TTS, all traced.

Run `python -m friday.voice.loop`. Hold the key, speak, release, listen.
Ctrl+C to quit. Memory = last MEMORY_TURNS turns from SQLite (sent only to the LLM).
One spoken command = one run_id: record, stt, router, safety/skill or llm, reply, tts.
"""

from __future__ import annotations

import time

from friday import db
from friday.graph import build_graph
from friday.skills.registry import build_registry
from friday.trace import Tracer
from friday.voice.audio import DEFAULT_KEY, record_while_held
from friday.voice.stt import get_stt
from friday.voice.tts import get_tts

MIN_SECONDS = 0.3  # shorter than this is treated as an accidental tap
MEMORY_TURNS = 6  # one turn = your message + Friday's reply

# Temporary: keeps spoken LLM replies short until Phase 3+ adds proper prompting.
VOICE_HINT = "\n\n(Reply in 1 to 3 short sentences, plain text, no markdown.)"


def load_history(conn) -> list[dict]:
    """Last N turns from SQLite, starting on a user message."""
    history = db.recent_messages(conn, MEMORY_TURNS * 2)
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


def handle_turn(conn, app, stt, tts) -> bool:
    """Run one turn. Returns False if the clip was ignored."""
    cap = record_while_held()
    released = time.perf_counter()  # key release: start of the timing below

    tracer = Tracer(conn)
    tracer.log("record", "", f"{cap.seconds:.1f} s, peak {cap.peak:.2f}", 0)

    if cap.seconds < MIN_SECONDS:
        print("Too short, ignored.")
        return False

    with tracer.step("stt", f"{cap.seconds:.1f} s of audio") as out:
        heard = stt.transcribe(cap.audio)
        out["output"] = heard.text
    print(f"You: {heard.text!r}  (STT {heard.ms} ms)")

    if not heard.text:
        print("Heard nothing, ignored.")
        return False

    # Load memory BEFORE saving the new message, so it is not sent twice.
    history = load_history(conn)

    with tracer.step("save_user_message", heard.text) as out:
        db.add_message(conn, "user", heard.text, channel="voice")
        out["output"] = "saved"

    # The graph writes its own trace rows (router, safety, skill, llm, reply) under this run_id.
    state = app.invoke({"run_id": tracer.run_id, "text": heard.text, "history": history})
    reply = state["reply"]
    who = state["skill_name"] if state["via"] == "rule" else state.get("provider", "llm")
    print(f"Friday: {reply!r}  (via {state['via']}: {who}, memory {len(history)} msgs)")

    with tracer.step("save_reply", reply) as out:
        db.add_message(conn, "assistant", reply, channel="voice")
        out["output"] = "saved"

    # The tts step time includes playback, so first_audio_ms is logged in the output.
    with tracer.step("tts", reply) as out:
        spoken = tts.speak(reply)
        out["output"] = (
            f"{spoken.sentences} sentences, first audio ready {spoken.first_audio_ms} ms"
        )

    to_end = int((time.perf_counter() - released) * 1000)
    print(f"[release -> end of speech {to_end} ms | run {tracer.run_id}]")
    return True


def main() -> None:
    conn = db.connect()
    print("Loading models (once)...")
    stt = get_stt()
    tts = get_tts()
    registry = build_registry()
    app = build_graph(conn, registry, llm_suffix=VOICE_HINT)
    print(f"Skills: {', '.join(registry.names())}")
    print(f"Ready. Hold [{DEFAULT_KEY}], speak, release. Ctrl+C to quit.")

    try:
        while True:
            try:
                handle_turn(conn, app, stt, tts)
            except Exception as exc:  # noqa: BLE001 - keep the loop alive after one bad turn
                print(f"Turn failed: {exc}")
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()