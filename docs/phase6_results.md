# Phase 6 results: router and wake word

Measured on Aditya's laptop (HP, i3, 8 GB). All figures are small samples from one person in one room, so quote the counts with them.

## Router in the graph (P6-01 to P6-03)

- Model: DistilBERT, 6 classes (models/router_v2, not committed). Switched on with env FRIDAY_ROUTER_MODEL=1; OFF by default. Threshold 0.9 is provisional. The default will be decided in Phase 7 by running the 100-command eval with and without it.
- CPU speed: mean 38.1 ms per line (P6-01).
- Share of commands that skip the LLM, split honestly:
  - Typed 90 own-phrasing lines: 63 of 90 did not reach the LLM, but only 26 were real actions (the rest were "say it again").
  - 63 unique real voice transcripts: the model routed 0 (rules: 34 to a skill, 11 to catch, 18 to the LLM).
  - 15 fresh real commands judged by eye: 8 correct actions (2 by rules, 6 by slot extraction), 7 router "other" misses (4 reminders, 3 music).
- Slot extraction: the LLM returns strict JSON, code builds the sentence the skill's own parser accepts; call time 864 to 1541 ms (7 calls).
- "Skips the LLM" does not mean "correct action".

## Wake word "hey friday" (T-09, T-10, P6-04 to P6-06)

Model: openWakeWord, ww_B.onnx, threshold 0.9. Push-to-talk stays as the fallback.

Offline (pre-registered rule: at 0.9, 3 or fewer false accepts in 6 h or more, recall 14/14 on eval2):

| Recording | Hours | False accepts at 0.9 | Notes |
|---|---|---|---|
| away3 (fresh test, overnight) | 7.00 | 0 | 1 at 0.8; recall 14/14 at 0.9. PASSED |
| away2 | 7.00 | 3 | 10 at 0.8 (failed the rule at 0.8); 0.9 picked after seeing it |
| away + media | 5.33 | 1 | road noise |

Live in Friday (listener running, laptop mic):
- First runs, 17 Oct: 6 of 6 "hey friday" commands woke and were answered correctly; with Spotify playing from the laptop speakers (50% and 100%) 6 of 6; later music test 3 of 3 (scores 0.90, 0.95, 0.98).
- P6-06 false-trigger run, 17 Oct 2026, 14:51 to 16:05 IST, dry run (wakes logged only):
  - Listening time 71.8 min (53,883 chunks). 5 wake events.
  - Rate: 4.18 per hour (95% exact Poisson interval 1.36 to 9.74). 25 chunks scored 0.5 to 0.9.
  - Conditions: normal use in one room. Tech house songs from a Bluetooth speaker (Stone 358 Pro) directly behind the laptop, Windows volume 80 (Spotify volume not recorded), then a podcast, then both, then quiet. Nobody said the wake phrase on purpose.
  - Event times and scores: 15:18:03 (0.98), 15:19:30 (0.92), 15:34:54 (0.97), 15:41:07 (0.92), 15:53:19 (0.96).
  - The audio at each trigger was not saved, so the cause is unknown.

Reading the two together: 0 in 7 h of a mostly quiet night, but about 4 per hour with music and speech playing from a speaker. Report both. One speaker, one mic, one room; no VAD gate in the offline numbers.

Decision (G6): wake word stays in v1 as an option with push-to-talk as the fallback. First Phase 7 fix item: false triggers with music or speech playing. Step one is saving the audio at each trigger in dry mode.