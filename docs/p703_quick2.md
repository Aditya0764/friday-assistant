# P7-03 results: quick2 (2026-10-18)

**QUICK RUN: 1 pass, no repeats. Fewer samples; read the n column.**

## Decision rules (fixed before the run)

- **(a) Router latency cost:** the router model goes ON unless the mean added time (router ON minus router OFF, same row, same pass) over the paired turns whose ON turn ended via=model is MORE than 0.5 s. Needs n >= 5 pairs. The all-turn mean is shown next to it and is NOT used. Rows whose routed skill differs between the modes are listed separately.
- **(b) RAM:** a peak working set of this Python process, with everything loaded (Whisper, Piper, MiniLM, router model, wake word), above 6144 MiB (6 GB) means not ON. System used RAM is context only.

### Result of (a)

- via=model pairs: n=3 pairs over 3 rows; mean ON-minus-OFF = **785 ms** (median 1009, min 203, max 1144).
- All pairs (not used for the decision): n=30; mean 139 ms, median 0.1 ms.

Rule (a): n too small to apply rule (a) (n = 3, need 5)

### Result of (b)

- Peak working set = 1563 MiB (source: OS peak working set (psutil peak_wset)).

Rule (b): peak = 1563 MiB, threshold 6144 MiB: NOT ABOVE

## Conditions

- Machine: Windows-11-10.0.26200-SP0, Python 3.13.3; 2 cores / 4 threads; CPU 1190 MHz now (max 1190); CPU busy 27.6% over 1 s before the run.
- Power: battery 0%, plugged in: True.
- System RAM at the start: total 7881 MiB, available 1782 MiB (used 6098 MiB).
- System RAM available at the end: 950 MiB.
- Biggest process groups at the start (working set summed per name; shared pages can be counted twice; names only):

| Name | Processes | Working set MiB |
|---|---|---|
| Code.exe | 21 | 1293 |
| svchost.exe | 92 | 586 |
| msedgewebview2.exe | 20 | 452 |
| PSExpressCore.exe | 1 | 209 |
| MsMpEng.exe | 1 | 207 |
| MemCompression | 1 | 182 |
| claude.exe | 1 | 174 |
| explorer.exe | 1 | 159 |

- Rows: 30 from evals/heldout2_30.csv. Passes: 1. Repeats for local parts: 1. Pause between turns: 1.0 s (outside the timers).
- LLM: live Groq, Gemini as backup, through friday.llm.ask with Friday's system prompt. Network allowed only to api.groq.com, generativelanguage.googleapis.com. Embedder local. Music player fake; Spotify never touched; clock fixed. A throwaway database per turn.
- Setup commands of a row run first (untimed, rules only, no router model).
- **The router model was loaded for the whole run, so the router-OFF turns ran with it in memory (interleaved with the ON turns).** The RAM stages below are in load order: the stage before the router load is the row 'MiniLM embedder'.
- The wake-word detector was loaded and fed one silent chunk, then left idle: no audio was streamed through it during the timings.
- Modules already imported before the first load: langgraph.
- Warm-up: 2 rows x 2 modes discarded before the text turns; 1 discarded run before STT and TTS.

## 1. Graph time per turn (text in, reply text out)

Timer around run_turn only: includes the real LLM network time. Rows: 30, passes: 1.

### Router OFF

Turns run: 30; errors excluded from the stats: 0.

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| all turns | 30 | 204 | 30.3 | 1165 | 1208 |
| ended: rules skill | 25 | 30.1 | 29.1 | 37.0 | 41.4 |
| ended: plain chat LLM | 5 | 1071 | 1140 | 1208 | 1208 |

p95 is nearest-rank: with n=30 it is the 29th smallest value.
First timed turn in this mode: 32.5 ms (rules skill).

By the provider that answered (turns that called the LLM):

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| groq | 5 | 1071 | 1140 | 1208 | 1208 |

### Router ON

Turns run: 30; errors excluded from the stats: 0.

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| all turns | 30 | 342 | 31.3 | 1167 | 4175 |
| ended: rules skill | 23 | 29.9 | 29.7 | 36.7 | 38.4 |
| ended: model + slot extraction | 3 | 1074 | 1030 | 1167 | 1167 |
| ended: plain chat LLM | 4 | 1589 | 796 | 4175 | 4175 |

p95 is nearest-rank: with n=30 it is the 29th smallest value.
First timed turn in this mode: 35.6 ms (rules skill).

By the provider that answered (turns that called the LLM):

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| groq | 7 | 1368 | 1025 | 4175 | 4175 |

LLM calls in the timed turns: 12; answered by {'groq': 12}; calls that failed on every provider: 0; provider failures (including ones the backup covered): none.

## 2. Router cost

Paired by row and pass (both turns must have succeeded). The ON turn and the OFF turn of a via=model row do different work (slot extraction vs a chat answer), so the difference is the cost of the route taken, not of the model alone.

| Pairs | n | mean ms | median ms | min ms | max ms |
|---|---|---|---|---|---|
| via=model (decision) | 3 | 785 | 1009 | 203 | 1144 |
| all pairs | 30 | 139 | 0.1 | -565 | 3036 |

Rows whose routed skill differs between OFF and ON (not averaged together):

| Row | OFF routed | ON routed | ON via | pairs | mean ON-OFF ms |
|---|---|---|---|---|---|
| HLD2-02 | catch | lists | model | 1 | 1009 |
| HLD2-15 | llm | music | model | 1 | 203 |
| HLD2-19 | catch | music | model | 1 | 1144 |

### Cold start of the router model

- Fresh Python process, time from ModelClassifier() to ready (includes importing torch and transformers and loading the weights). Runs: 1; ready times in s: 13.26; failures: 0. The disk cache was not cleared, so the first run may be slower than the rest. Interpreter start and the friday import are not counted.

### Model forward time (tokenize + forward + softmax, in-process, warm)

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| classify() on 30 texts x 1 repeats | 30 | 46.7 | 46.0 | 70.8 | 77.1 |

p95 is nearest-rank: with n=30 it is the 29th smallest value.

## 3. STT (faster-whisper base.en, int8, CPU, vad=True)

- Clips: 31 (saved wake/follow-up clips in data\clips*, read only; 31 decoded, 0 failed to decode). Repeats per clip: 1, so 31 timings from 31 distinct decoded clips. Each clip is decoded once with friday.voice.decode before timing and the float32 array is passed to transcribe(), as Friday does; only transcribe() is timed here.
- Clip length: min 1.0 s, max 5.4 s, mean 3.3 s.
- Empty transcripts: 4 of 31 timings; errors: 0. No file name or transcript is kept.

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| transcribe() | 31 | 1171 | 976 | 1436 | 9545 |

p95 is nearest-rank: with n=31 it is the 30th smallest value.
Transcribe time / clip length: mean 0.37, median 0.23 (n=31).
Model load: 1866 ms (one run).

## 4. TTS (Piper en_US-amy-medium, synthesize_wav, no playback)

- Texts: 30 (replies from the router-OFF turns of pass 1). Repeats each: 1. Errors: 0.

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| synthesize_wav() | 30 | 359 | 283 | 1321 | 1365 |

p95 is nearest-rank: with n=30 it is the 29th smallest value.

| Row | text chars | mean synth ms | audio s |
|---|---|---|---|
| HLD2-16 | 9 | 80.2 | 1.0 |
| HLD2-21 | 15 | 185 | 2.4 |
| HLD2-14 | 17 | 135 | 1.5 |
| HLD2-24 | 17 | 149 | 2.0 |
| HLD2-25 | 17 | 163 | 1.9 |
| HLD2-26 | 17 | 143 | 1.9 |
| HLD2-17 | 18 | 161 | 1.8 |
| HLD2-18 | 18 | 190 | 1.8 |
| HLD2-23 | 18 | 205 | 2.6 |
| HLD2-11 | 25 | 209 | 2.9 |
| HLD2-13 | 26 | 175 | 1.9 |
| HLD2-08 | 31 | 288 | 3.0 |
| HLD2-20 | 35 | 364 | 4.4 |
| HLD2-22 | 35 | 389 | 4.5 |
| HLD2-09 | 37 | 265 | 3.3 |
| HLD2-01 | 40 | 300 | 3.3 |
| HLD2-04 | 41 | 297 | 3.3 |
| HLD2-06 | 41 | 253 | 3.3 |
| HLD2-03 | 44 | 285 | 3.4 |
| HLD2-15 | 45 | 267 | 3.1 |
| HLD2-29 | 47 | 366 | 3.6 |
| HLD2-02 | 48 | 281 | 3.8 |
| HLD2-19 | 48 | 292 | 3.9 |
| HLD2-07 | 50 | 352 | 4.2 |
| HLD2-10 | 55 | 329 | 4.1 |
| HLD2-05 | 57 | 305 | 4.0 |
| HLD2-12 | 58 | 434 | 4.5 |
| HLD2-28 | 230 | 1365 | 15.5 |
| HLD2-30 | 254 | 1321 | 15.7 |
| HLD2-27 | 255 | 1237 | 16.0 |

## 5. Full turn: clip -> STT -> graph -> synthesize_wav

**No playback, no Bluetooth, WAV ready, not audio start.** One timer around the whole chain INCLUDING the decoding of the saved clip (a live turn already has the audio array from the microphone, so decoding is extra here), one pass per router mode, real LLM. The parts below are measured inside the same turns and are shown separately: they are not added together here.

### Router OFF

Turns: 31; ok: 26; empty transcript: 5; errors: 0 (not in the stats).

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| whole turn (one timer) | 26 | 1445 | 1264 | 2405 | 2600 |
| part: decode clip | 26 | 9.8 | 9.7 | 13.5 | 22.4 |
| part: STT (transcribe only) | 26 | 978 | 963 | 1141 | 1167 |
| part: graph | 26 | 212 | 24.5 | 942 | 1235 |
| part: TTS | 26 | 245 | 224 | 375 | 401 |

p95 is nearest-rank: with n=26 it is the 25th smallest value.

### Router ON

Turns: 31; ok: 26; empty transcript: 5; errors: 0 (not in the stats).

| Group | n | mean ms | median ms | p95 ms | max ms |
|---|---|---|---|---|---|
| whole turn (one timer) | 26 | 1498 | 1317 | 2303 | 2329 |
| part: decode clip | 26 | 9.6 | 9.3 | 14.3 | 14.6 |
| part: STT (transcribe only) | 26 | 980 | 962 | 1118 | 1213 |
| part: graph | 26 | 263 | 28.6 | 1009 | 1026 |
| part: TTS | 26 | 246 | 228 | 362 | 395 |

p95 is nearest-rank: with n=26 it is the 25th smallest value.

## 6. RAM of this process (psutil)

Working set (RSS) after each load, in load order. USS (memory only this process owns) where Windows allowed it.

| After loading | load ms | working set MiB | USS MiB | error |
|---|---|---|---|---|
| Python + Friday imports | 0.0 | 106 | 81 |  |
| Whisper base.en | 1866 | 255 | 218 |  |
| Piper amy-medium | 4104 | 364 | 318 |  |
| MiniLM embedder | 11115 | 790 | 704 |  |
| Router model (DistilBERT) | 423 | 1054 | 970 |  |
| Wake-word detector | 275 | 1086 | 1002 |  |

- Peak during the work (sampled every 50 ms, 4755 samples, a short spike can be missed): 1559 MiB.
- OS peak working set since the process started (includes load spikes): 1563 MiB.
- Sampled peak per phase:

| Phase | peak working set MiB |
|---|---|
| text turns | 1093 |
| router forward | 1095 |
| STT | 1380 |
| TTS | 1336 |
| full turns | 1559 |

## 7. Per row (all passes)

| Row | OFF median ms | ON median ms | OFF routed | ON routed (via) |
|---|---|---|---|---|
| HLD2-01 | 32.5 | 35.6 | lists (rule) | lists (rule) |
| HLD2-02 | 21.4 | 1030 | catch (rule) | lists (model) |
| HLD2-03 | 27.5 | 29.7 | lists (rule) | lists (rule) |
| HLD2-04 | 34.4 | 38.4 | lists (rule) | lists (rule) |
| HLD2-05 | 41.4 | 33.8 | lists (rule) | lists (rule) |
| HLD2-06 | 28.6 | 27.4 | lists (rule) | lists (rule) |
| HLD2-07 | 33.5 | 33.4 | reminders (rule) | reminders (rule) |
| HLD2-08 | 35.4 | 36.3 | reminders (rule) | reminders (rule) |
| HLD2-09 | 35.7 | 31.2 | reminders (rule) | reminders (rule) |
| HLD2-10 | 35.9 | 36.7 | reminders (rule) | reminders (rule) |
| HLD2-11 | 37.0 | 31.8 | reminders (rule) | reminders (rule) |
| HLD2-12 | 35.5 | 31.3 | reminders (rule) | reminders (rule) |
| HLD2-13 | 27.7 | 23.8 | music (rule) | music (rule) |
| HLD2-14 | 29.4 | 30.1 | music (rule) | music (rule) |
| HLD2-15 | 823 | 1025 | llm (llm) | music (model) |
| HLD2-16 | 30.6 | 29.0 | music (rule) | music (rule) |
| HLD2-17 | 29.1 | 29.5 | music (rule) | music (rule) |
| HLD2-18 | 26.3 | 29.6 | music (rule) | music (rule) |
| HLD2-19 | 23.5 | 1167 | catch (rule) | music (model) |
| HLD2-20 | 28.2 | 27.3 | clock (rule) | clock (rule) |
| HLD2-21 | 29.9 | 29.7 | clock (rule) | clock (rule) |
| HLD2-22 | 28.9 | 23.5 | clock (rule) | clock (rule) |
| HLD2-23 | 28.1 | 28.6 | calc (rule) | calc (rule) |
| HLD2-24 | 22.2 | 24.9 | calc (rule) | calc (rule) |
| HLD2-25 | 21.4 | 25.5 | calc (rule) | calc (rule) |
| HLD2-26 | 29.1 | 21.5 | calc (rule) | calc (rule) |
| HLD2-27 | 1165 | 948 | llm (llm) | llm (llm) |
| HLD2-28 | 1208 | 643 | llm (llm) | llm (llm) |
| HLD2-29 | 1140 | 4175 | llm (llm) | llm (llm) |
| HLD2-30 | 1022 | 589 | llm (llm) | llm (llm) |

## What this does not show

- Every LLM-bound number depends on the network and the provider at that minute.
- Parts (STT, graph, TTS) are separate measurements; only section 5 is a full turn, and it ends at a WAV in memory, not at sound from the speaker.
- RAM here is this process only. It is not comparable with docs/ram.md, which was read by eye from Task Manager for the whole system.
- The clips are the owner's voice on this laptop; other voices and noise may differ.
