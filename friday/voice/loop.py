"""Voice loop: hold key -> mic -> STT -> LLM -> TTS, every step traced.

Run `python -m friday.voice.loop`. Hold the key, speak, release, listen.
Ctrl+C to quit. No chat memory yet (that is P2-07).
"""

from __future__ import annotations

import time

from friday import db
from friday.llm import ask
from friday.trace import Tracer
from friday.voice.audio import DEFAULT_KEY, record_while_held
from friday.voice.stt import get_stt
from friday.voice.tts import get_tts

MIN_SECONDS = 0.3  # shorter than this is treated as an accidental tap

# Temporary: keeps spoken replies short until Phase 3 adds proper prompting.
VOICE_HINT = "\n\n(Reply in 1 to 3 short sentences, plain text, no markdown.)"


def handle_turn(conn, stt, tts) -> bool:
    """Run one turn. Returns False if the clip was ignored."""
    cap = record_while_held()
    released = time.perf_counter()  # key release: start of voice-to-voice time

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

    with tracer.step("save_user_message", heard.text) as out:
        db.add_message(conn, "user", heard.text)
        out["output"] = "saved"

    with tracer.step("llm", heard.text + VOICE_HINT) as out:
        reply = ask([{"role": "user", "content": heard.text + VOICE_HINT}])
        out["output"] = f"{reply.provider}/{reply.model}: {reply.text}"
    print(f"Friday: {reply.text!r}  ({reply.provider}, LLM {reply.ms} ms)")

    with tracer.step("save_reply", reply.text) as out:
        db.add_message(conn, "assistant", reply.text)
        out["output"] = "saved"

    # The tts step time includes playback, so first_audio_ms is logged in the output.
    with tracer.step("tts", reply.text) as out:
        spoken = tts.speak(reply.text)
        out["output"] = (
            f"{spoken.sentences} sentences, first audio ready {spoken.first_audio_ms} ms"
        )

    to_first_audio = int((time.perf_counter() - released) * 1000)
    print(f"[release -> end of speech {to_first_audio} ms | run {tracer.run_id}]")
    return True


def main() -> None:
    conn = db.connect()
    print("Loading models (once)...")
    stt = get_stt()
    tts = get_tts()
    print(f"Ready. Hold [{DEFAULT_KEY}], speak, release. Ctrl+C to quit.")

    try:
        while True:
            try:
                handle_turn(conn, stt, tts)
            except Exception as exc:  # noqa: BLE001 - keep the loop alive after one bad turn
                print(f"Turn failed: {exc}")
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()