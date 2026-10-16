"""Voice loop: hold key (or say the wake word) -> mic -> STT -> graph -> TTS, all traced.

Run `python -m friday.voice.loop`. Hold the key, speak, release, listen.
Ctrl+C to quit. Memory = last MEMORY_TURNS turns from SQLite (sent only to the LLM).
One spoken command = one run_id: record, stt, router, safety/skill or llm, reply, tts.

Wake word (P6-04), OFF by default: set FRIDAY_WAKEWORD=1 before starting. Then one shared
mic stream feeds the wake-word detector AND the push-to-talk key, and wake scores are
logged to data\\wake_log.csv. A leading "hey friday" in what was heard is removed.
Debug: also set FRIDAY_SAVE_CLIPS=1 to save each command's audio to data\\clips\\.
Counting false triggers (P6-06): also set FRIDAY_WAKE_DRY=1. Wakes are heard and logged, but
nothing is transcribed, answered or spoken.

Reminders: a background scheduler speaks them when they are due. A lock makes sure a
reminder never talks over a reply (it waits until the reply is finished).

Music: if Spotify is set up in .env, the music skill is switched on. It plays only on
the device named in SPOTIFY_DEVICE_NAME.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

import numpy as np

from friday import db
from friday.graph import build_graph
from friday.prompt import FRIDAY_PROMPT
from friday.scheduler import ReminderScheduler
from friday.skills.registry import build_registry
from friday.spotify_client import SpotifyPlayer
from friday.trace import Tracer
from friday.voice.audio import DEFAULT_KEY, record_while_held
from friday.voice.phrase import strip_wake_phrase
from friday.voice.stt import get_stt
from friday.voice.tts import get_tts

MIN_SECONDS = 0.3  # shorter than this is treated as an accidental tap
MEMORY_TURNS = 6  # one turn = your message + Friday's reply
WAKE_FLAG = "FRIDAY_WAKEWORD"
WAKE_LOG = Path("data") / "wake_log.csv"


def wake_enabled() -> bool:
    return os.environ.get(WAKE_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def load_history(conn) -> list[dict]:
    """Last N turns from SQLite, starting on a user message."""
    history = db.recent_messages(conn, MEMORY_TURNS * 2)
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


def process_capture(
    conn,
    app,
    stt,
    tts,
    audio,
    seconds: float,
    peak: float,
    speak_lock: AbstractContextManager | None = None,
    source: str = "key",
    started: float | None = None,
) -> bool:
    """Everything after recording: STT, graph, save, TTS. Returns False if the clip was ignored."""
    speak_lock = speak_lock or nullcontext()
    started = time.perf_counter() if started is None else started  # start of the timing below

    tracer = Tracer(conn)
    tracer.log("record", "", f"{seconds:.1f} s, peak {peak:.2f}, via {source}", 0)

    if seconds < MIN_SECONDS:
        print("Too short, ignored.")
        return False

    with tracer.step("stt", f"{seconds:.1f} s of audio") as out:
        heard = stt.transcribe(audio, vad=source != "key")
        out["output"] = heard.text
    print(f"You: {heard.text!r}  (STT {heard.ms} ms)")

    if not heard.text:
        print("Heard nothing, ignored.")
        return False

    text = heard.text
    if source != "key":  # spoken after the wake word: drop a leading "hey friday"
        text = strip_wake_phrase(text)
        if text != heard.text:
            print(f"    (wake phrase removed: {text!r})")

    # Load memory BEFORE saving the new message, so it is not sent twice.
    history = load_history(conn)

    with tracer.step("save_user_message", text) as out:
        db.add_message(conn, "user", text, channel="voice")
        out["output"] = "saved"

    # The graph writes its own trace rows (router, safety, skill, llm, reply) under this run_id.
    state = app.invoke({"run_id": tracer.run_id, "text": text, "history": history})
    reply = state["reply"]
    via = state["via"]
    who = state["skill_name"] if via in ("rule", "model") else state.get("provider", "llm")
    print(f"Friday: {reply!r}  (via {via}: {who}, memory {len(history)} msgs)")

    with tracer.step("save_reply", reply) as out:
        db.add_message(conn, "assistant", reply, channel="voice")
        out["output"] = "saved"

    # The tts step time includes playback, so first_audio_ms is logged in the output.
    with tracer.step("tts", reply) as out, speak_lock:
        spoken = tts.speak(reply)
        out["output"] = (
            f"{spoken.sentences} sentences, first audio ready {spoken.first_audio_ms} ms"
        )

    to_end = int((time.perf_counter() - started) * 1000)
    print(f"[{source} -> end of speech {to_end} ms | run {tracer.run_id}]")
    return True


def handle_turn(conn, app, stt, tts, speak_lock: AbstractContextManager | None = None) -> bool:
    """Push-to-talk turn: record while the key is held, then process it."""
    cap = record_while_held()
    released = time.perf_counter()  # key release: start of the timing
    return process_capture(
        conn, app, stt, tts, cap.audio, cap.seconds, cap.peak, speak_lock, "key", released
    )


def run_wake(conn, app, stt, tts, speak_lock) -> None:
    """Always-on mode: wake word or push-to-talk from one shared mic stream."""
    import keyboard  # the same library the push-to-talk recorder uses

    from friday.voice.clips import clips_enabled, save_clip
    from friday.voice.listener import Listener
    from friday.voice.mic import SAMPLE_RATE, MicHub
    from friday.voice.wakeword import THRESHOLD, WakeWordDetector

    print("Loading the wake-word model...")
    detector = WakeWordDetector()
    save_clips = clips_enabled()
    dry_run = os.environ.get("FRIDAY_WAKE_DRY", "").strip().lower() in ("1", "true", "yes", "on")

    def on_audio(audio, source: str) -> bool:
        if dry_run:  # false-trigger counting: hear and log, do nothing else
            print(f"    (dry run: {source} heard, nothing processed)")
            return False
        if save_clips:
            try:
                print(f"    (clip saved: {save_clip(audio, source).name})")
            except Exception as exc:  # noqa: BLE001 - a debug aid must never break a turn
                print(f"    (clip not saved: {exc})")
        samples = audio.astype(np.float32) / 32768.0
        seconds = len(samples) / SAMPLE_RATE
        peak = float(np.abs(samples).max()) if len(samples) else 0.0
        return process_capture(conn, app, stt, tts, samples, seconds, peak, speak_lock, source)

    WAKE_LOG.parent.mkdir(exist_ok=True)
    is_new = not WAKE_LOG.exists()
    with WAKE_LOG.open("a", encoding="utf-8") as log, MicHub() as mic:
        if is_new:
            log.write("time,kind,score,chunks\n")

        def write(line: str) -> None:
            log.write(line + "\n")
            log.flush()

        listener = Listener(
            mic,
            detector,
            on_audio,
            is_speaking=speak_lock.locked,
            key_down=lambda: keyboard.is_pressed(DEFAULT_KEY),
            wake_log=write,
        )
        print(f'Ready. Say "hey friday" (threshold {THRESHOLD}) or hold [{DEFAULT_KEY}].')
        print(f"Wake scores are logged to {WAKE_LOG}. Ctrl+C to quit.")
        if dry_run:
            print("DRY RUN: wakes are logged only. Nothing is transcribed, answered or spoken.")
        if save_clips:
            print("Saving each command's audio to data\\clips\\ (debug).")
        listener.run()


def main() -> None:
    conn = db.connect()
    print("Loading models (once)...")
    stt = get_stt()
    tts = get_tts()

    speak_lock = threading.Lock()  # one voice at a time: replies and reminders take turns

    def say(text: str) -> None:
        print(f"Friday (reminder): {text!r}")
        with speak_lock:
            tts.speak(text)

    scheduler = ReminderScheduler(say)
    restored = scheduler.start()
    player = SpotifyPlayer.from_env()  # None when Spotify is not set up in .env
    registry = build_registry(scheduler, player=player)
    app = build_graph(conn, registry, system_prompt=FRIDAY_PROMPT)
    print(f"Skills: {', '.join(registry.names())}")
    print(f"Reminders waiting: {restored}")
    print("Music: on" if player else "Music: off (Spotify not set up in .env)")

    try:
        if wake_enabled():
            run_wake(conn, app, stt, tts, speak_lock)
        else:
            print(f"Ready. Hold [{DEFAULT_KEY}], speak, release. Ctrl+C to quit.")
            while True:
                try:
                    handle_turn(conn, app, stt, tts, speak_lock)
                except Exception as exc:  # noqa: BLE001 - keep the loop alive after one bad turn
                    print(f"Turn failed: {exc}")
    except KeyboardInterrupt:
        print("\nBye.")
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    main()