# API limits (read from the dashboards)

Checked on 10 Oct 2026. Only numbers I read myself on the pages are listed.

## Groq (primary): openai/gpt-oss-20b

Source: Groq console, Settings > Limits (Organization Limits, free plan).

| Requests/min | Requests/day | Tokens/min | Tokens/day |
|---|---|---|---|
| 30 | 1,000 | 8,000 | 200,000 |

This resolves the earlier conflict between sources (about 1,000 vs 14,400 requests per day): the dashboard shows 1,000.

## Gemini (backup)

Source: Google AI Studio, project `friday-assistant`, Rate Limit page. Plan: Free tier, no billing set up.

| Model | Requests/min | Tokens/min | Requests/day |
|---|---|---|---|
| gemini-3.5-flash-lite (used as backup) | 15 | 250,000 | not read yet |
| gemini-3.8-flash | 5 | 250,000 | not read yet |

## Observations while testing (single samples, not benchmarks)

- gemini-3.8-flash hung: one call took about 285 s, another gave no result after 30 s and again after 40 s.
- gemini-3.5-flash-lite answered in about 5 s, so it is the backup model.
- Every Gemini call has a 30 s timeout in `llm.py`.

## Still to check

- Gemini requests per day (scroll the Rate Limit table sideways).
- Gemini free-tier terms: whether prompts can be used to improve Google products.