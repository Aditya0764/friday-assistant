# Eval 100: heldout2_off (2026-10-17)

**Passed 22 | Failed 3 | Runner errors 4**

**PARTIAL RUN: stopped after 3 runner errors in a row; 29 of 30 rows ran.**

Router model: off (rules only). LLM: LIVE (Groq, Gemini backup) with Friday's system prompt. Network allowed only to api.groq.com, generativelanguage.googleapis.com. Embedder local; music player fake; Spotify never touched; clock fixed at 2026-10-17T10:00:00+05:30. One sample per row.
Chat rows (expected llm) are scored on routing only: READ their real replies.
A row passes only if routing, reply and database effect are all right. A runner error (LLM, network or embedder problem) is not a Friday failure and is not in the totals.

## Totals

- Checked rows: 25. Passed: 22. Failed: 3. Runner errors: 4.
- Not checked offline (not counted as passes): 0.
- No effect spec (not passed, not failed; fix the CSV): 0.

## Per skill (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|
| lists | 6 | 5/6 | 5/6 | 5/6 | 4/6 |
| reminders | 6 | 6/6 | 6/6 | 6/6 | 6/6 |
| music | 6 | 5/6 | 5/6 | 6/6 | 5/6 |
| clock | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| calc | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| chat | 0 | 0/0 | 0/0 | 0/0 | 0/0 |
| **all checked** | 25 | 23/25 | 23/25 | 24/25 | 22/25 |

## By phrasing note (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|

## Failed rows

| Id | Text | Wanted | Routed | Reply | Why |
|---|---|---|---|---|---|
| HLD2-02 | what all is on my shopping list | lists | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| HLD2-05 | add sunscreen and a towel to my packing list | lists | lists (rule: lists) | Okay, I added sunscreen and a towel to your packing list. | db: lists: wanted {'packing': ['sunscreen', 'towel']}, found {'packing': ['sunscreen', 'a towel']} |
| HLD2-19 | stop playing the song | music | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing, reply |

## Runner errors (not Friday failures; not in the totals)

| Id | Text | Kind | Detail |
|---|---|---|---|
| HLD2-15 | pause this for a bit | network | APIConnectionError, status None |
| HLD2-27 | explain what an API is in simple words | network | APIConnectionError, status None |
| HLD2-28 | give me a tip for a job interview | network | APIConnectionError, status None |
| HLD2-29 | what's a good name for a pet dog | network | APIConnectionError, status None |

## Rows with no effect spec (not in the totals; add expected_effect to the CSV)

| Id | Text | Routed | Reply |
|---|---|---|---|

## LLM usage

- Calls made by Friday: 4. Answered by: none.
- Calls that failed on every provider: 4.
- Provider failures (including ones the backup covered): {'gemini/network': 4, 'groq/network': 4}.
- Hosts the guard blocked: none.

## Wording warnings (heuristic, NOT scored)

A reply from the plain LLM that sounds like it did a skill's job (matched by a simple wording pattern, so it can miss real cases and flag harmless ones). Read the replies yourself.

| Id | Text | Matched phrase | Reply |
|---|---|---|---|

## Every row

| Id | Status | Text | Routed | Reply |
|---|---|---|---|---|
| HLD2-01 | pass | add eggs to my grocery list | lists | Okay, I added eggs to your grocery list. |
| HLD2-02 | fail | what all is on my shopping list | catch | Sorry, I didn't catch that. Please say it again. |
| HLD2-03 | pass | remove milk from the grocery list | lists | Okay, I removed milk from your grocery list. |
| HLD2-04 | pass | put call mom on my to-do list | lists | Okay, I added call mom to your todo list. |
| HLD2-05 | fail | add sunscreen and a towel to my packing list | lists | Okay, I added sunscreen and a towel to your packing list. |
| HLD2-06 | pass | make a note that the meeting moved to friday | lists | Okay, noted: the meeting moved to friday. |
| HLD2-07 | pass | remind me to call the bank at three thirty | reminders | Okay, I'll remind you to call the bank at 3:30 PM. |
| HLD2-08 | pass | set a timer for fifteen minutes | reminders | Okay, timer set for 15 minutes. |
| HLD2-09 | pass | wake me up at six tomorrow | reminders | Okay, alarm set for tomorrow at 6 AM. |
| HLD2-10 | pass | remind me in two hours to take out the trash | reminders | Okay, I'll remind you to take out the trash in 2 hours. |
| HLD2-11 | pass | set an alarm for nine pm | reminders | Okay, alarm set for 9 PM. |
| HLD2-12 | pass | remind me to submit the form tomorrow at nine am | reminders | Okay, I'll remind you to submit the form tomorrow at 9 AM. |
| HLD2-13 | pass | play some Arijit Singh | music | Playing some arijit singh. |
| HLD2-14 | pass | play the song Kesariya | music | Playing kesariya. |
| HLD2-15 | runner_error | pause this for a bit | llm | ERROR: APIConnectionError: [Errno 11001] getaddrinfo failed |
| HLD2-16 | pass | play the next track | music | Skipping. |
| HLD2-17 | pass | make it louder | music | Volume 60 percent. |
| HLD2-18 | pass | put the volume at forty percent | music | Volume 40 percent. |
| HLD2-19 | fail | stop playing the song | catch | Sorry, I didn't catch that. Please say it again. |
| HLD2-20 | pass | which day of the week is it | clock | Today is Saturday, 17 October 2026. |
| HLD2-21 | pass | what's the time now | clock | It is 10:00 AM. |
| HLD2-22 | pass | tell me today's date | clock | Today is Saturday, 17 October 2026. |
| HLD2-23 | pass | what is 45 plus 67 | calc | The answer is 112. |
| HLD2-24 | pass | what's fifteen percent of 80 | calc | The answer is 12. |
| HLD2-25 | pass | what is 144 divided by 12 | calc | The answer is 12. |
| HLD2-26 | pass | what's nine squared | calc | The answer is 81. |
| HLD2-27 | runner_error | explain what an API is in simple words | llm | ERROR: APIConnectionError: [Errno 11001] getaddrinfo failed |
| HLD2-28 | runner_error | give me a tip for a job interview | llm | ERROR: APIConnectionError: [Errno 11001] getaddrinfo failed |
| HLD2-29 | runner_error | what's a good name for a pet dog | llm | ERROR: APIConnectionError: [Errno 11001] getaddrinfo failed |
