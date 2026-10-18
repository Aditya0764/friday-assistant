# P7-04 spoken held-out set #2: scored vs by eye

Sources (committed): `evals/results/eval_100_spoken2_off.json`, `evals/results/eval_100_spoken2_on.json`, `evals/results/eval_100_heard_heldout2.json` (transcripts, sha256 ee45eaacc1f4), `evals/heldout2_30.csv` (what was said and what the scorer expects).

## Numbers

| Router model | Scored | By eye |
|---|---|---|
| OFF | 20/30 | 18/30 |
| ON | 24/30 | 22/30 |

- Passed in both runs: 20 rows (HLD2-04, 06, 09, 10, 11, 12, 13, 14, 16, 17, 18, 20, 21, 22, 25, 26, 27, 28, 29, 30).
- ON passed 4 more: HLD2-02, 08, 15, 19. That makes 24.

## Why by eye is 2 lower

Two scored passes play the wrong song, because Whisper misheard. The scorer only expects a reply that matches `^Playing .+\.$`, so any "Playing ..." reply passes. Both rows were routed to music by rule in both runs.

| Row | Said | Whisper heard | Reply |
|---|---|---|---|
| HLD2-13 | play some Arijit Singh | Play some original notes in the description. | Playing some original notes in the description. |
| HLD2-14 | play the song Kesariya | Play the song in case area. | Playing in case area. |

By-eye counts = scored counts minus these two rows (HLD2-13 and HLD2-14 pass in both runs).

## Caveats

- The by-eye counts were judged by reading the saved transcripts, not by a second scorer. The scorer was not edited after the results.
- HLD2-08 (ON only) is counted as correct: the timer is really 15 minutes, although Whisper heard "Set it MF for 15 minutes".
- HLD2-27 to HLD2-30 are chat rows scored on routing only. Answer quality was not judged.
- 30 rows, one speaker, one mic, one room, read from a screen, no wake phrase.
