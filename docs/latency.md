# Voice-to-voice latency

Measured 2026-10-11 on the HP i3 laptop, 8 GB RAM. 20 valid runs, same spoken sentence each time.

Voice-to-voice = key release until the first reply sentence is ready to play (STT + LLM + first TTS sentence + small overhead).
Not included: audio-device and Bluetooth delay (not visible to the code).

## Summary

- Mean: 2318 ms
- Median: 2210 ms
- p95 (nearest rank, 19th of 20 sorted): 2877 ms
- Min / max: 1925 / 3061 ms
- Mean STT: 1041 ms
- Mean LLM: 998 ms
- Mean TTS first sentence: 232 ms
- LLM providers used: {'groq': 20}
- The earlier estimate was about 2.5 s. This file holds the measured numbers.

## Runs

| # | STT ms | LLM ms | TTS first ms | Total ms | Provider |
|---|--------|--------|--------------|----------|----------|
| 1 | 1089 | 1679 | 278 | 3061 | groq |
| 2 | 1074 | 901 | 237 | 2227 | groq |
| 3 | 1375 | 1110 | 380 | 2877 | groq |
| 4 | 1165 | 1453 | 180 | 2810 | groq |
| 5 | 1154 | 717 | 217 | 2105 | groq |
| 6 | 985 | 773 | 245 | 2014 | groq |
| 7 | 992 | 1393 | 266 | 2664 | groq |
| 8 | 950 | 843 | 254 | 2058 | groq |
| 9 | 936 | 916 | 218 | 2088 | groq |
| 10 | 952 | 898 | 215 | 2079 | groq |
| 11 | 1007 | 836 | 222 | 2077 | groq |
| 12 | 903 | 818 | 190 | 1925 | groq |
| 13 | 1380 | 851 | 231 | 2474 | groq |
| 14 | 976 | 935 | 179 | 2105 | groq |
| 15 | 1038 | 970 | 185 | 2208 | groq |
| 16 | 938 | 1031 | 228 | 2211 | groq |
| 17 | 979 | 896 | 324 | 2219 | groq |
| 18 | 938 | 862 | 198 | 2016 | groq |
| 19 | 996 | 837 | 191 | 2643 | groq |
| 20 | 998 | 1249 | 201 | 2499 | groq |
