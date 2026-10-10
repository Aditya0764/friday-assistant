# Peak RAM check (P2-08)

Measured 11 Oct 2026 on the HP i3 laptop (8 GB RAM, 7.7 GB usable), read by eye from
Task Manager (Performance -> Memory). Single session, not a benchmark.

## Setup
- Closed Chrome, WhatsApp, Dropbox, Adobe Express Photos and Teams before the test.
- Kept VS Code and Spotify open (normal working setup).
- Ran `python -m friday.voice.loop` (faster-whisper base.en, Piper, Groq, chat memory)
  with Task Manager open beside it.
- Audio output: Stone 358 Pro (Bluetooth).

## Readings
| Moment | In use | Available | Committed |
|--------|--------|-----------|-----------|
| Before Friday starts (after closing apps) | 5.2 GB | 2.5 GB | 9.9 / 16.7 GB |
| Friday loaded, idle at "Ready" | 6.2 GB | 1.5 GB | 11.9 / 16.7 GB |
| During / after turns (short and long answers) | 6.3 GB | 1.4 GB | 12.2 / 16.7 GB |

- Peak In use seen: 6.3 GB of 7.7 GB (82%).
- Lowest Available seen: 1.3 GB.
- Loading the models added about 1.0 GB. The turns themselves added about 0.1 GB.
- Long answers did not push memory higher than short ones (graph stayed flat).

## Observations
- No audio stutter and no slowdown noticed during the turns (judged by ear and feel).
- Committed (12.2 GB) is above the 8 GB of RAM. That alone does not prove swapping,
  and Task Manager's Memory tab does not show pagefile activity directly.
  So the claim is: Available stayed above 1.3 GB and nothing slowed down.
  "No swapping" is NOT claimed.

## Caveats
- Peak read by eye, so a very short spike could have been missed.
- Test was without Chrome and the other apps closed above. With Chrome open, the
  baseline was 6.6 GB in use and only 1.1 GB available before Friday even started.
- Re-measured later in P7-03 with the full system (more skills, wake word).