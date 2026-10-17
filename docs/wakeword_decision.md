# T-10: wake word decision (17 Oct 2026)

**Decision: GO.** Friday uses the custom "hey friday" model `ww_B.onnx` at threshold **0.9**. Push-to-talk stays as the fallback.

## What was tested
- Model: variant B of my openWakeWord training run (Kaggle, 30000 steps, max negative weight 100, 64 real positives per batch). Model file sha256 starts `c04d15b7ec12a3d9`. The hash was not recorded at training time; the wrapper in Friday reproduces the offline scores, which is indirect evidence it is the same file.
- Test method (`training/eval_wakeword.py`): audio fed in 1280-sample (80 ms) chunks, raw model score, no smoothing, no VAD, a trigger is a score of 0.9 or more, events closer than a 2 s quiet gap count once. Recall clips get 1 s of silence before and after.
- Pass rule written before the final test: at 0.9, at most 3 false accepts in 6 hours or more, and recall still 14 of 14 on the fresh clips.

## Results
| Test | Audio | At 0.9 | At 0.8 |
|---|---|---|---|
| Recall, `eval2` (14 fresh clips, recorded after the model was chosen) | 14 clips | 14/14 (lowest clip 0.99) | 14/14 |
| Confirmation test `away3` (fresh, overnight, room audio) | 7.00 h | **0 false accepts** | 1 (0.14/h) |
| Earlier `away2` (seen; this is where 0.9 was chosen) | 7.00 h | 3 (0.43/h) | 10 (1.43/h) |
| Earlier `away` + `media` (seen) | 5.33 h | 1 | 1 |

Result of the pre-registered test: **pass**. With 0 events in 7 h, the 95% upper bound on the true rate is about 0.43 per hour. Pooled over all four recordings it is 4 events in 19.3 h (about 0.2 per hour), but that figure is not unbiased because 0.9 was picked after seeing two of them.

## Honest limits
- One speaker (me), one laptop mic, one set of rooms. Other voices, TV speech and other mics are untested.
- The same hours of the night gave 3 false accepts one day and 0 the next (the 3 were road noise: honking and vehicles), so the real rate depends on the noise of the day and its range is wide.
- No VAD gate was used in these numbers.
- A retrain with extra road noise (ww_D) was worse and was dropped.
- False triggers with Friday running (its own voice, CPU load) are measured separately in P6-06.

## Next
P6-06 live dry run, then the README states these numbers with these limits.
