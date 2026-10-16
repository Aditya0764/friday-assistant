"""Live wake-word test (P6-04): the shared mic, the detector and the end-of-command logic.

Run:  python -m friday.voice.wake_test       (Ctrl+C to stop and see the summary)
No Whisper, no LLM, no speakers. Say "hey friday", then a command, then stay quiet.
It prints the loudest score and the room noise about every 3 s, and when the wake word fires it
shows how the command window would end. Close the voice loop first: two programs on the mic
can fight over it.
"""

from __future__ import annotations

import time

from friday.voice.endpoint import (
    CHUNK_SECONDS,
    Endpointer,
    NoiseFloor,
    rms,
    speech_threshold,
)
from friday.voice.mic import MicHub
from friday.voice.wakeword import THRESHOLD, WakeWordDetector

REPORT_SECONDS = 3.0


def main() -> None:
    print("Loading the wake-word model...")
    detector = WakeWordDetector()
    floor = NoiseFloor()
    events = 0
    step_ms: list[float] = []
    started = time.monotonic()
    last_report = started
    peak = 0.0
    with MicHub() as mic:
        print(f'Listening (threshold {THRESHOLD}). Say "hey friday", then a command. Ctrl+C to stop.')
        try:
            while True:
                chunk = mic.read(timeout=1.0)
                if chunk is None:
                    print("No audio for 1 s. Is the microphone OK or in use by another program?")
                    continue
                floor.add(rms(chunk))
                t0 = time.perf_counter()
                score, fired = detector.feed(chunk)
                step_ms.append((time.perf_counter() - t0) * 1000)
                peak = max(peak, score)
                if fired:
                    events += 1
                    threshold = speech_threshold(floor.level)
                    print(f">>> WAKE (score {score:.2f}). Say your command now...")
                    endpoint = Endpointer(threshold)
                    reason = None
                    while reason is None:
                        nxt = mic.read(timeout=1.0)
                        if nxt is None:
                            reason = "mic_stalled"
                            break
                        reason = endpoint.update(nxt)
                    print(
                        f"    command window ended: {reason} after {endpoint.chunks * CHUNK_SECONDS:.1f} s "
                        f"(speech threshold {threshold:.4f}, noise floor {floor.level:.4f})"
                    )
                    detector.reset()
                now = time.monotonic()
                if now - last_report >= REPORT_SECONDS:
                    print(f"  loudest score {peak:.2f} | noise floor {floor.level:.4f}")
                    peak, last_report = 0.0, now
        except KeyboardInterrupt:
            pass
    minutes = (time.monotonic() - started) / 60
    print(f"\nRan {minutes:.1f} min, {events} wake events, {len(step_ms)} chunks scored.")
    if step_ms:
        mean = sum(step_ms) / len(step_ms)
        print(f"Detector per chunk, live: mean {mean:.1f} ms, max {max(step_ms):.1f} ms")
    print(f"Chunks dropped because nobody read them: {mic.dropped}. Sound-card overflows: {mic.overflows}.")


if __name__ == "__main__":
    main()