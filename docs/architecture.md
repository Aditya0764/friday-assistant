# Friday architecture (v0, end of Phase 1)

## What exists now

```
prompt
  |
  v
llm.ask() ------------------> Groq (openai/gpt-oss-20b)
  |    if Groq fails
  +--------------------------> Gemini (gemini-3.5-flash-lite, 30 s timeout)
  |
  v
LLMReply(text, provider, model, ms)
  |
  +--> db.py     saves messages to SQLite
  +--> trace.py  saves every step (step, input, output, ms) to SQLite

config.py reads the keys from .env for all of the above
```

## Files

| File | Job |
|---|---|
| `friday/config.py` | Loads settings from `.env`; clear error if a required key is missing |
| `friday/llm.py` | One `ask()` function. Groq first, Gemini as backup. Same reply shape from both |
| `friday/db.py` | SQLite tables (messages, reminders, list_items, traces, documents) and helpers |
| `friday/trace.py` | `Tracer` times each step and saves it as a trace row |

## Design rules

- One swappable LLM file: callers never know which provider answered.
- Trace everything: each step logs input, output and milliseconds.
- Secrets live only in `.env` and `.secrets/`, never in code or git.
- Limits and observations are in `docs/limits.md`.

## Planned (not built yet)

```
Voice (laptop) / Telegram / Web dashboard
  -> wake word (later) -> speech to text
  -> intent router (rules first, trained model later)
       confident -> skill directly
       unsure    -> LLM decides
  -> LangGraph: chat | music | timers | lists | math | RAG
  -> safety check (approval for risky actions)
  -> reply -> text to speech / message / screen
  -> every step logged to SQLite -> live trace page
```