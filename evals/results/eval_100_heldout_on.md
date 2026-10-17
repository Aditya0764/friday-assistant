# Eval 100: heldout_on (2026-10-17)

**Passed 17 | Failed 13 | Runner errors 0**

Router model: ON (local, models/router_v2). LLM: LIVE (Groq, Gemini backup) with Friday's system prompt. Network allowed only to api.groq.com, generativelanguage.googleapis.com. Embedder local; music player fake; Spotify never touched; clock fixed at 2026-10-17T10:00:00+05:30. One sample per row.
Chat rows (expected llm) are scored on routing only: READ their real replies.
A row passes only if routing, reply and database effect are all right. A runner error (LLM, network or embedder problem) is not a Friday failure and is not in the totals.

## Totals

- Checked rows: 30. Passed: 17. Failed: 13. Runner errors: 0.
- Not checked offline (not counted as passes): 0.

## Per skill (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|
| lists | 6 | 6/6 | 5/6 | 2/6 | 1/6 |
| reminders | 6 | 3/6 | 3/6 | 3/6 | 0/6 |
| music | 7 | 6/7 | 6/7 | 7/7 | 6/7 |
| clock | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| calc | 4 | 3/4 | 3/4 | 4/4 | 3/4 |
| chat | 4 | 4/4 | 0/0 | 4/4 | 4/4 |
| **all checked** | 30 | 25/30 | 20/26 | 23/30 | 17/30 |

## By phrasing note (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|

## Failed rows

| Id | Text | Wanted | Routed | Reply | Why |
|---|---|---|---|---|---|
| HLD-01 | put toothpaste on my shopping list | lists | lists (rule: lists) | Okay, I added toothpaste to your shopping list. | db: lists: wanted {}, found {'shopping': ['toothpaste']} |
| HLD-02 | I need to add rice and lentils to the grocery list | lists | lists (model: catch [model lists_notes 1.00]) | Okay, I added rice and lentils to your grocery list. | db: lists: wanted {}, found {'grocery': ['rice', 'lentils']} |
| HLD-04 | take bread off my shopping list | lists | lists (rule: lists) | Okay, I removed bread from your shopping list. | db: lists: wanted {'shopping': ['bread', 'milk']}, found {'shopping': ['milk']} |
| HLD-05 | read out my to-do list | lists | lists (model: catch [model lists_notes 1.00]) | On your todo list: call the dentist. | reply |
| HLD-06 | note down that the rent is due on the first | lists | lists (rule: lists) | Okay, noted: the rent is due on the first. | db: lists: wanted {}, found {'notes': ['the rent is due on the first']} |
| HLD-07 | remind me to drink water in twenty minutes | reminders | reminders (rule: reminders) | Okay, I'll remind you to drink water in 20 minutes. | db: reminders: wanted none saved, found 1 |
| HLD-08 | set an alarm for six fifteen tomorrow morning | reminders | catch (model: catch [model timers_reminders 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| HLD-09 | remind me at four thirty to water the plants | reminders | catch (model: catch [model timers_reminders 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| HLD-10 | start a timer for ten minutes | reminders | reminders (rule: reminders) | Okay, timer set for 10 minutes. | db: reminders: wanted none saved, found 1 |
| HLD-11 | can you wake me up at seven | reminders | reminders (model: catch [model timers_reminders 1.00]) | Okay, alarm set for 7 PM. | db: reminders: wanted none saved, found 1 |
| HLD-12 | ping me in an hour to check the oven | reminders | llm (llm: llm [model other 0.95]) | I’m not able to set reminders. Could you please say that again? | routing, reply |
| HLD-17 | turn the volume down a bit | music | catch (model: catch [model music 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| HLD-24 | how many kilometers is 26 miles | calc | llm (llm: llm [model other 1.00]) | 26 miles is about 42 kilometers. | routing, reply |

## Runner errors (not Friday failures; not in the totals)

| Id | Text | Kind | Detail |
|---|---|---|---|

## LLM usage

- Calls made by Friday: 12. Answered by: {'groq': 12}.
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
| HLD-01 | fail | put toothpaste on my shopping list | lists | Okay, I added toothpaste to your shopping list. |
| HLD-02 | fail | I need to add rice and lentils to the grocery list | lists | Okay, I added rice and lentils to your grocery list. |
| HLD-03 | pass | what do I have on my packing list | lists | On your packing list: socks and toothbrush. |
| HLD-04 | fail | take bread off my shopping list | lists | Okay, I removed bread from your shopping list. |
| HLD-05 | fail | read out my to-do list | lists | On your todo list: call the dentist. |
| HLD-06 | fail | note down that the rent is due on the first | lists | Okay, noted: the rent is due on the first. |
| HLD-07 | fail | remind me to drink water in twenty minutes | reminders | Okay, I'll remind you to drink water in 20 minutes. |
| HLD-08 | fail | set an alarm for six fifteen tomorrow morning | catch | Sorry, I didn't catch that. Please say it again. |
| HLD-09 | fail | remind me at four thirty to water the plants | catch | Sorry, I didn't catch that. Please say it again. |
| HLD-10 | fail | start a timer for ten minutes | reminders | Okay, timer set for 10 minutes. |
| HLD-11 | fail | can you wake me up at seven | reminders | Okay, alarm set for 7 PM. |
| HLD-12 | fail | ping me in an hour to check the oven | llm | I’m not able to set reminders. Could you please say that again? |
| HLD-13 | pass | play Blinding Lights by The Weeknd | music | Playing blinding lights by the weeknd. |
| HLD-14 | pass | play something chill | music | Playing something chill. |
| HLD-15 | pass | pause | music | Paused. |
| HLD-16 | pass | next song please | music | Skipping. |
| HLD-17 | fail | turn the volume down a bit | catch | Sorry, I didn't catch that. Please say it again. |
| HLD-18 | pass | set volume to seventy | music | Volume 70 percent. |
| HLD-19 | pass | resume the song | music | Resuming. |
| HLD-20 | pass | what's the date today | clock | Today is Saturday, 17 October 2026. |
| HLD-21 | pass | tell me the time please | clock | It is 10:00 AM. |
| HLD-22 | pass | what is the time right now | clock | It is 10:00 AM. |
| HLD-23 | pass | what's twenty percent of 450 | calc | The answer is 90. |
| HLD-24 | fail | how many kilometers is 26 miles | llm | 26 miles is about 42 kilometers. |
| HLD-25 | pass | what is 15 times 18 | calc | The answer is 270. |
| HLD-26 | pass | what's the square root of 144 | calc | The answer is 12. |
| HLD-27 | pass | what's the difference between a virus and a bacteria | llm | Viruses are acellular particles that need a host cell to replicate, while bacteria are single‑cell organisms that can live and grow independently. Viruses have only genetic material wrapped in a protein coat, whereas bacteria possess a full cell structure with a cell wall, cytoplasm, and their own metabolism. Because of these differences, they respond to different treatments and behave in distinct ways. |
| HLD-28 | pass | suggest a good movie for tonight | llm | You might enjoy watching The Shawshank Redemption – it’s a timeless tale of hope and friendship. |
| HLD-29 | pass | how do I stay focused while studying | llm | Take a short walk to clear your mind before you sit down, then break your study time into 25‑minute focused blocks with five‑minute breaks. Use a simple to‑do list, write down what you need to cover, and keep your phone out of reach. Finally, give yourself a small reward when you finish each block—it keeps the momentum going. |
| HLD-30 | pass | tell me something interesting about space | llm | Did you know that a day on Venus is longer than its year? Venus rotates so slowly and in the opposite direction that its day lasts longer than it takes to orbit the Sun. |
