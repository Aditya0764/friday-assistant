# Router CPU speed and RAM (P6-01)

Measured 2026-10-16 on the HP i3 laptop (Windows 11, 8 GB RAM). Script: data/p601_cpu_speed.py (git-ignored, not committed). Model: models/router_v2 (DistilBERT, 6 classes), PyTorch fp32 on CPU, no ONNX. torch 2.14.1+cpu, transformers 5.19.0, 2 torch threads (default).

One process with only the router loaded. Not measured: Whisper, Piper and the embedder loaded together; other thread counts; whether the laptop was plugged in and which other programs were running (not recorded).

## Speed
270 timed runs (90 own-phrasing test lines x 3, after 10 warm-up runs), one command at a time, on Friday's clean text:
- mean 38.1 ms, median 36.0 ms, p95 61.9 ms (nearest rank), min 22.6 ms, max 157.6 ms
- tokenising: 0.3 ms mean; model forward: 37.8 ms mean
- For comparison only (different day and conditions): docs/latency.md has a mean LLM step of 998 ms.

## Start-up and RAM (this process only)
- Importing torch and transformers took 41.5 s on this run (cold start; a second run was not measured).
- Tokenizer and model load took 1.3 s. The weights file is 267,844,872 bytes on disk.
- RAM in MiB, working set / private: bare Python 16 / 10; after importing torch 336 / 530; after loading the router 611 / 835; end of run 623 / 876. Peak working set 626.
- Working set is the RAM Windows keeps for the process. Private is memory only this process uses.

## Sanity check
- The laptop reproduces Kaggle run B: 77 of 90 correct (0.8556) on the 90 own-phrasing test lines. Friday clean text, training-style cleaning and raw text all give the same 77 and the same per-class counts. 0 of 90 predictions change between padded (training) and unpadded (Friday) input.
- Per class: doc_qa 9 of 14, lists_notes 12 of 13, math_time 14 of 18, music 8 of 9, other 17 of 17, timers_reminders 17 of 19.
- 13 wrong, 10 with confidence 0.95 or higher (the Kaggle report said 9 of 13; the reason for the one-line difference was not checked).
- These are typed lowercase lines, so this says nothing yet about real Whisper text. The 90 lines are already used: do not tune on them.