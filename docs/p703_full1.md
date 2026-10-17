# P7-03 results: full1 (2026-10-18)

## Decision rules (fixed before the run)

- **(a) Router latency cost:** the router model goes ON unless the mean added time (router ON minus router OFF, same row, same pass) over the paired turns whose ON turn ended via=model is MORE than 0.5 s. Needs n >= 5 pairs. The all-turn mean is shown next to it and is NOT used. Rows whose routed skill differs between the modes are listed separately.
- **(b) RAM:** a peak working set of this Python process, with everything loaded (Whisper, Piper, MiniLM, router model, wake word), above 6144 MiB (6 GB) means not ON. System used RAM is context only.

### Result of (a)

- via=model pairs: n=9 pairs over 3 rows; mean ON-minus-OFF = **840 ms** (median 989, min 288, max 1221).
- All pairs (not used for the decision): n=90; mean 89.2 ms, median 0.4 ms.

Rule (a): mean added = 0.840 s, n = 9, threshold 0.5 s: ABOVE

### Result of (b)

- Peak working set = 1456 MiB (source: OS peak working set (psutil peak_wset)).

Rule (b): peak = 1456 MiB, threshold 6144 MiB: NOT ABOVE

## Conditions

- Machine: Windows-11-10.0.26200-SP0, Python 3.13.3; 2 cores / 4 threads; CPU 1190 MHz now (max 1190); CPU busy 23.0% over 1 s before the run.
- Power: battery 0%, plugged in: True.
- System RAM at the start: total 7881 MiB, available 2117 MiB (used 5764 MiB).
- System RAM available at the end: 1219 MiB.
- Biggest process groups at the start (working set summed per name; shared pages can be counted twice; names only):

| Name | Processes | Working set MiB |
|---|---|---|
| Code.exe | 21 | 1074 |
| svchost.exe | 90 | 592 |
| msedgewebview2.exe | 20 | 484 |
| MsMpEng.exe | 1 | 204 |
| cpptools.exe | 2 | 177 |
| explorer.exe | 1 | 158 |
| PSExpressCore.exe | 1 | 151 |
| claude.exe | 1 | 129 |

- Rows: 30 from evals/heldout2_30.csv. Passes: 3. Repeats for local parts: 3. Pause between turns: 1.0 s (outside the timers).
- LLM: live Groq, Gemini as backup, through friday.llm.ask with Friday's system prompt. Network allowed only to api.groq.com, generativelanguage.googleapis.com. Embedder local. Music player fake; Spotify never touched; clock fixed. A throwaway database per turn.
- Setup commands of a row run first (untimed, rules only, no router model).
- **The router model was loaded for the whole run, so the router-OFF turns ran with it in memory (interleaved with the ON turns).** The RAM stages below are in load order: the stage before the router load is the row 'MiniLM embedder'.
- The wake-word detector was loaded and fed one silent chunk, then left idle: no audio was streamed through it during the timings.
- Modules already imported before the first load: langgraph.
- Warm-up: 2 rows x 2 modes discarded before the text turns; 1 discarded run before STT and TTS.

## 1. Graph time per turn (text in, reply text out)

Timer around run_turn only: includes the real LLM network time. Rows: 30, passes: 3.

### Router OFF

Turns run: 90; errors excluded from the stats: 0.

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| all turns | 90 | 173 | 29.8 | 968 | 1060 |
| ended: rules skill | 75 | 31.2 | 28.7 | 43.0 | 216 |
| ended: plain chat LLM | 15 | 880 | 879 | 1060 | 1060 |

p95 is nearest-rank: with n=90 it is the 86th smallest value.
First timed turn in this mode: 40.7 ms (rules skill).

By the provider that answered (turns that called the LLM):

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| groq | 15 | 880 | 879 | 1060 | 1060 |

### Router ON

Turns run: 90; errors excluded from the stats: 0.

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| all turns | 90 | 262 | 30.4 | 1186 | 1704 |
| ended: rules skill | 69 | 29.4 | 29.1 | 38.3 | 44.8 |
| ended: model + slot extraction | 9 | 1171 | 1176 | 1376 | 1376 |
| ended: plain chat LLM | 12 | 917 | 854 | 1704 | 1704 |

p95 is nearest-rank: with n=90 it is the 86th smallest value.
First timed turn in this mode: 38.3 ms (rules skill).

By the provider that answered (turns that called the LLM):

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| groq | 21 | 1026 | 1014 | 1376 | 1704 |

LLM calls in the timed turns: 36; answered by {'groq': 36}; calls that failed on every provider: 0; provider failures (including ones the backup covered): none.

## 2. Router cost

Paired by row and pass (both turns must have succeeded). The ON turn and the OFF turn of a via=model row do different work (slot extraction vs a chat answer), so the difference is the cost of the route taken, not of the model alone.

| Pairs | n | mean ms | median ms | min ms | max ms |
|---|---|---|---|---|---|
| via=model (decision) | 9 | 840 | 989 | 288 | 1221 |
| all pairs | 90 | 89.2 | 0.4 | -438 | 1221 |

Rows whose routed skill differs between OFF and ON (not averaged together):

| Row | OFF routed | ON routed | ON via | pairs | mean ON-OFF ms |
|---|---|---|---|---|---|
| HLD2-02 | catch | lists | model | 3 | 1103 |
| HLD2-15 | llm | music | model | 3 | 349 |
| HLD2-19 | catch | music | model | 3 | 1068 |

### Cold start of the router model

- Fresh Python process, time from ModelClassifier() to ready (includes importing torch and transformers and loading the weights). Runs: 3; ready times in s: 13.55, 10.88, 10.66; failures: 0. The disk cache was not cleared, so the first run may be slower than the rest. Interpreter start and the friday import are not counted.

### Model forward time (tokenize + forward + softmax, in-process, warm)

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| classify() on 30 texts x 3 repeats | 90 | 57.5 | 49.6 | 114 | 167 |

p95 is nearest-rank: with n=90 it is the 86th smallest value.

## 3. STT (faster-whisper base.en, int8, CPU, vad=True)

- Clips: 31 (saved wake/follow-up clips in data\clips*, read only; 31 decoded, 0 failed to decode). Repeats per clip: 3, so 93 timings from 31 distinct decoded clips. Each clip is decoded once with friday.voice.decode before timing and the float32 array is passed to transcribe(), as Friday does; only transcribe() is timed here.
- Clip length: min 1.0 s, max 5.4 s, mean 3.3 s.
- Empty transcripts: 15 of 93 timings; errors: 0. No file name or transcript is kept.

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| transcribe() | 93 | 1408 | 1236 | 1446 | 12420 |

p95 is nearest-rank: with n=93 it is the 89th smallest value.
Transcribe time / clip length: mean 0.44, median 0.29 (n=93).
Model load: 1782 ms (one run).

## 4. TTS (Piper en_US-amy-medium, synthesize_wav, no playback)

- Texts: 30 (replies from the router-OFF turns of pass 1). Repeats each: 3. Errors: 0.

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| synthesize_wav() | 90 | 431 | 336 | 1423 | 1813 |

p95 is nearest-rank: with n=90 it is the 86th smallest value.

| Row | text chars | mean synth ms | audio s |
|---|---|---|---|
| HLD2-16 | 9 | 110 | 1.0 |
| HLD2-21 | 15 | 242 | 2.4 |
| HLD2-14 | 17 | 165 | 1.5 |
| HLD2-24 | 17 | 186 | 2.0 |
| HLD2-25 | 17 | 296 | 1.9 |
| HLD2-26 | 17 | 183 | 2.0 |
| HLD2-17 | 18 | 298 | 1.8 |
| HLD2-18 | 18 | 180 | 1.7 |
| HLD2-23 | 18 | 247 | 2.6 |
| HLD2-11 | 25 | 320 | 2.9 |
| HLD2-13 | 26 | 181 | 1.9 |
| HLD2-08 | 31 | 296 | 3.0 |
| HLD2-20 | 35 | 450 | 4.6 |
| HLD2-22 | 35 | 437 | 4.5 |
| HLD2-09 | 37 | 344 | 3.3 |
| HLD2-01 | 40 | 325 | 3.4 |
| HLD2-04 | 41 | 322 | 3.3 |
| HLD2-06 | 41 | 327 | 3.3 |
| HLD2-03 | 44 | 331 | 3.3 |
| HLD2-15 | 44 | 310 | 3.1 |
| HLD2-02 | 48 | 487 | 3.9 |
| HLD2-19 | 48 | 370 | 3.8 |
| HLD2-07 | 50 | 439 | 4.1 |
| HLD2-10 | 55 | 400 | 4.1 |
| HLD2-05 | 57 | 404 | 4.1 |
| HLD2-12 | 58 | 441 | 4.5 |
| HLD2-29 | 74 | 519 | 5.2 |
| HLD2-27 | 175 | 1136 | 11.6 |
| HLD2-30 | 236 | 1426 | 14.5 |
| HLD2-28 | 275 | 1756 | 17.5 |

## 5. Full turn: clip -> STT -> graph -> synthesize_wav

**No playback, no Bluetooth, WAV ready, not audio start.** One timer around the whole chain INCLUDING the decoding of the saved clip (a live turn already has the audio array from the microphone, so decoding is extra here), one pass per router mode, real LLM. The parts below are measured inside the same turns and are shown separately: they are not added together here.

### Router OFF

Turns: 31; ok: 26; empty transcript: 5; errors: 0 (not in the stats).

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| whole turn (one timer) | 26 | 1496 | 1300 | 2514 | 2582 |
| part: decode clip | 26 | 9.6 | 9.4 | 12.8 | 16.5 |
| part: STT (transcribe only) | 26 | 996 | 981 | 1090 | 1235 |
| part: graph | 26 | 227 | 25.0 | 1028 | 1082 |
| part: TTS | 26 | 263 | 220 | 425 | 462 |

p95 is nearest-rank: with n=26 it is the 25th smallest value.

### Router ON

Turns: 31; ok: 26; empty transcript: 5; errors: 0 (not in the stats).

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| whole turn (one timer) | 26 | 1551 | 1292 | 2498 | 2686 |
| part: decode clip | 26 | 9.3 | 9.5 | 12.7 | 13.4 |
| part: STT (transcribe only) | 26 | 987 | 984 | 1113 | 1125 |
| part: graph | 26 | 312 | 26.4 | 1188 | 1328 |
| part: TTS | 26 | 242 | 212 | 429 | 430 |

p95 is nearest-rank: with n=26 it is the 25th smallest value.

## 6. RAM of this process (psutil)

Working set (RSS) after each load, in load order. USS (memory only this process owns) where Windows allowed it.

| After loading | load ms | working set MiB | USS MiB | error |
|---|---|---|---|---|
| Python + Friday imports | 0.0 | 105 | 81 |  |
| Whisper base.en | 1782 | 253 | 217 |  |
| Piper amy-medium | 4277 | 364 | 317 |  |
| MiniLM embedder | 11139 | 788 | 702 |  |
| Router model (DistilBERT) | 478 | 1051 | 967 |  |
| Wake-word detector | 257 | 1084 | 1000 |  |

- Peak during the work (sampled every 50 ms, 9135 samples, a short spike can be missed): 1452 MiB.
- OS peak working set since the process started (includes load spikes): 1456 MiB.
- Sampled peak per phase:

| Phase | peak working set MiB |
|---|---|
| text turns | 1093 |
| router forward | 1084 |
| STT | 1373 |
| TTS | 1313 |
| full turns | 1452 |

## 7. Per row (all passes)

| Row | OFF median ms | ON median ms | OFF routed | ON routed (via) |
|---|---|---|---|---|
| HLD2-01 | 32.7 | 37.2 | lists (rule) | lists (rule) |
| HLD2-02 | 21.7 | 1167 | catch (rule) | lists (model) |
| HLD2-03 | 33.0 | 29.4 | lists (rule) | lists (rule) |
| HLD2-04 | 32.7 | 32.6 | lists (rule) | lists (rule) |
| HLD2-05 | 45.0 | 41.6 | lists (rule) | lists (rule) |
| HLD2-06 | 29.1 | 31.6 | lists (rule) | lists (rule) |
| HLD2-07 | 31.1 | 33.0 | reminders (rule) | reminders (rule) |
| HLD2-08 | 31.9 | 30.0 | reminders (rule) | reminders (rule) |
| HLD2-09 | 32.0 | 33.1 | reminders (rule) | reminders (rule) |
| HLD2-10 | 31.3 | 31.0 | reminders (rule) | reminders (rule) |
| HLD2-11 | 32.6 | 30.2 | reminders (rule) | reminders (rule) |
| HLD2-12 | 30.5 | 30.4 | reminders (rule) | reminders (rule) |
| HLD2-13 | 23.9 | 25.1 | music (rule) | music (rule) |
| HLD2-14 | 27.5 | 25.9 | music (rule) | music (rule) |
| HLD2-15 | 1030 | 1331 | llm (llm) | music (model) |
| HLD2-16 | 24.2 | 23.5 | music (rule) | music (rule) |
| HLD2-17 | 28.6 | 25.0 | music (rule) | music (rule) |
| HLD2-18 | 22.6 | 23.9 | music (rule) | music (rule) |
| HLD2-19 | 24.5 | 1089 | catch (rule) | music (model) |
| HLD2-20 | 25.8 | 24.1 | clock (rule) | clock (rule) |
| HLD2-21 | 25.3 | 25.4 | clock (rule) | clock (rule) |
| HLD2-22 | 25.3 | 25.0 | clock (rule) | clock (rule) |
| HLD2-23 | 23.8 | 25.2 | calc (rule) | calc (rule) |
| HLD2-24 | 23.3 | 22.8 | calc (rule) | calc (rule) |
| HLD2-25 | 23.6 | 25.8 | calc (rule) | calc (rule) |
| HLD2-26 | 25.1 | 26.3 | calc (rule) | calc (rule) |
| HLD2-27 | 952 | 964 | llm (llm) | llm (llm) |
| HLD2-28 | 879 | 922 | llm (llm) | llm (llm) |
| HLD2-29 | 755 | 711 | llm (llm) | llm (llm) |
| HLD2-30 | 843 | 786 | llm (llm) | llm (llm) |

## What this does not show

- Every LLM-bound number depends on the network and the provider at that minute.
- Parts (STT, graph, TTS) are separate measurements; only section 5 is a full turn, and it ends at a WAV in memory, not at sound from the speaker.
- RAM here is this process only. It is not comparable with docs/ram.md, which was read by eye from Task Manager for the whole system.
- The clips are the owner's voice on this laptop; other voices and noise may differ.
