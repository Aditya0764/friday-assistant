# Eval 100: dev_hld_off (2026-10-17)

**Passed 29 | Failed 1 | Runner errors 0**

Router model: off (rules only). LLM: LIVE (Groq, Gemini backup) with Friday's system prompt. Network allowed only to api.groq.com, generativelanguage.googleapis.com. Embedder local; music player fake; Spotify never touched; clock fixed at 2026-10-17T10:00:00+05:30. One sample per row.
Chat rows (expected llm) are scored on routing only: READ their real replies.
A row passes only if routing, reply and database effect are all right. A runner error (LLM, network or embedder problem) is not a Friday failure and is not in the totals.

## Totals

- Checked rows: 30. Passed: 29. Failed: 1. Runner errors: 0.
- Not checked offline (not counted as passes): 0.
- No effect spec (not passed, not failed; fix the CSV): 0.

## Per skill (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|
| lists | 6 | 6/6 | 6/6 | 6/6 | 6/6 |
| reminders | 6 | 6/6 | 6/6 | 6/6 | 6/6 |
| music | 7 | 7/7 | 7/7 | 7/7 | 7/7 |
| clock | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| calc | 4 | 3/4 | 3/4 | 4/4 | 3/4 |
| chat | 4 | 4/4 | 0/0 | 4/4 | 4/4 |
| **all checked** | 30 | 29/30 | 25/26 | 30/30 | 29/30 |

## By phrasing note (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|

## Failed rows

| Id | Text | Wanted | Routed | Reply | Why |
|---|---|---|---|---|---|
| HLD-24 | how many kilometers is 26 miles | calc | llm (llm: llm) | About 41.8 kilometers. | routing, reply |

## Runner errors (not Friday failures; not in the totals)

| Id | Text | Kind | Detail |
|---|---|---|---|

## Rows with no effect spec (not in the totals; add expected_effect to the CSV)

| Id | Text | Routed | Reply |
|---|---|---|---|

## LLM usage

- Calls made by Friday: 5. Answered by: {'groq': 5}.
- Calls that failed on every provider: 0.
- Provider failures (including ones the backup covered): none.
- Hosts the guard blocked: none.

## Wording warnings (heuristic, NOT scored)

A reply from the plain LLM that sounds like it did a skill's job (matched by a simple wording pattern, so it can miss real cases and flag harmless ones). Read the replies yourself.

| Id | Text | Matched phrase | Reply |
|---|---|---|---|

## Every row

| Id | Status | Text | Routed | Reply |
|---|---|---|---|---|
| HLD-01 | pass | put toothpaste on my shopping list | lists | Okay, I added toothpaste to your shopping list. |
| HLD-02 | pass | I need to add rice and lentils to the grocery list | lists | Okay, I added rice and lentils to your grocery list. |
| HLD-03 | pass | what do I have on my packing list | lists | On your packing list: socks and toothbrush. |
| HLD-04 | pass | take bread off my shopping list | lists | Okay, I removed bread from your shopping list. |
| HLD-05 | pass | read out my to-do list | lists | On your todo list: call the dentist. |
| HLD-06 | pass | note down that the rent is due on the first | lists | Okay, noted: the rent is due on the first. |
| HLD-07 | pass | remind me to drink water in twenty minutes | reminders | Okay, I'll remind you to drink water in 20 minutes. |
| HLD-08 | pass | set an alarm for six fifteen tomorrow morning | reminders | Okay, alarm set for tomorrow at 6:15 AM. |
| HLD-09 | pass | remind me at four thirty to water the plants | reminders | Okay, I'll remind you to water the plants at 4:30 PM. |
| HLD-10 | pass | start a timer for ten minutes | reminders | Okay, timer set for 10 minutes. |
| HLD-11 | pass | can you wake me up at seven | reminders | Okay, alarm set for tomorrow at 7 AM. |
| HLD-12 | pass | ping me in an hour to check the oven | reminders | Okay, I'll remind you to check the oven in 1 hour. |
| HLD-13 | pass | play Blinding Lights by The Weeknd | music | Playing blinding lights by the weeknd. |
| HLD-14 | pass | play something chill | music | Playing something chill. |
| HLD-15 | pass | pause | music | Paused. |
| HLD-16 | pass | next song please | music | Skipping. |
| HLD-17 | pass | turn the volume down a bit | music | Volume 40 percent. |
| HLD-18 | pass | set volume to seventy | music | Volume 70 percent. |
| HLD-19 | pass | resume the song | music | Resuming. |
| HLD-20 | pass | what's the date today | clock | Today is Saturday, 17 October 2026. |
| HLD-21 | pass | tell me the time please | clock | It is 10:00 AM. |
| HLD-22 | pass | what is the time right now | clock | It is 10:00 AM. |
| HLD-23 | pass | what's twenty percent of 450 | calc | The answer is 90. |
| HLD-24 | fail | how many kilometers is 26 miles | llm | About 41.8 kilometers. |
| HLD-25 | pass | what is 15 times 18 | calc | The answer is 270. |
| HLD-26 | pass | what's the square root of 144 | calc | The answer is 12. |
| HLD-27 | pass | what's the difference between a virus and a bacteria | llm | A virus is a tiny particle that can only replicate inside a host cell, while a bacteria is a single‑cell organism that can live on its own. Viruses need a host to multiply, bacteria can grow independently. This is why antibiotics work on bacteria but not viruses. |
| HLD-28 | pass | suggest a good movie for tonight | llm | How about watching “Guardians of the Galaxy”—it’s a fun, action‑packed adventure with a great soundtrack and plenty of laughs. |
| HLD-29 | pass | how do I stay focused while studying | llm | Use a quiet space, turn off distractions, and break your study time into short blocks with short breaks. Keep a clear goal for each block so you know what you need to finish. And remember to stretch or breathe a few minutes between sessions to refresh your focus. |
| HLD-30 | pass | tell me something interesting about space | llm | The largest known star, UY Scuti, is so huge that if it were placed at the center of our solar system its outer layers would reach beyond the orbit of Neptune. |
