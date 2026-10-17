# Eval 100: spoken2_off (2026-10-18)

**Passed 20 | Failed 10 | Runner errors 0**

Router model: off (rules only). LLM: LIVE (Groq, Gemini backup) with Friday's system prompt. Network allowed only to api.groq.com, generativelanguage.googleapis.com. Embedder local; music player fake; Spotify never touched; clock fixed at 2026-10-17T10:00:00+05:30. One sample per row.
Chat rows (expected llm) are scored on routing only: READ their real replies.
Spoken test: each row ran on what Friday HEARD (30 transcribed, 0 empty transcripts counted as failures, 0 with no audio left out of the totals). STT base.en, vad=True. Transcripts: eval_100_heard_heldout2.json (sha256 ee45eaacc1f4). Setup commands stay typed.
A row passes only if routing, reply and database effect are all right. A runner error (LLM, network or embedder problem) is not a Friday failure and is not in the totals.

## Totals

- Checked rows: 30. Passed: 20. Failed: 10. Runner errors: 0.
- Not checked offline (not counted as passes): 0.
- No effect spec (not passed, not failed; fix the CSV): 0.

## Per skill (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|
| lists | 6 | 4/6 | 2/6 | 3/6 | 2/6 |
| reminders | 6 | 4/6 | 4/6 | 4/6 | 4/6 |
| music | 7 | 5/7 | 5/7 | 7/7 | 5/7 |
| clock | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| calc | 4 | 2/4 | 2/4 | 4/4 | 2/4 |
| chat | 4 | 4/4 | 0/0 | 4/4 | 4/4 |
| **all checked** | 30 | 22/30 | 16/26 | 25/30 | 20/30 |

## By phrasing note (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|

## Failed rows

| Id | Text | Heard | Wanted | Routed | Reply | Why |
|---|---|---|---|---|---|---|
| HLD2-01 | add eggs to my grocery list | Add x to my grocery list | lists | lists (rule: lists) | Okay, I added x to your grocery list. | reply, db: lists: wanted {'grocery': ['eggs']}, found {'grocery': ['x']} |
| HLD2-02 | what all is on my shopping list | What all is on my shopping list? | lists | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| HLD2-03 | remove milk from the grocery list | Remove milk from a glossary list. | lists | lists (rule: lists) | I couldn't find milk on your glossary list. | reply, db: lists: wanted {'grocery': ['eggs']}, found {'grocery': ['milk', 'eggs']} |
| HLD2-05 | add sunscreen and a towel to my packing list | I had sunscreen and it doubled to my packing list. | lists | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing, reply, db: lists: wanted {'packing': ['sunscreen', 'towel']}, found {} |
| HLD2-07 | remind me to call the bank at three thirty | Remind me to call the bank at 330. | reminders | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing, reply, db: reminders: wanted 1 saved, found 0 |
| HLD2-08 | set a timer for fifteen minutes | Set it MF for 15 minutes. | reminders | llm (llm: llm) | I didn't catch that. Could you say it again? | routing, reply, db: reminders: wanted 1 saved, found 0 |
| HLD2-15 | pause this for a bit | Pause this for a bit. | music | llm (llm: llm) | I didn't catch that—could you please say it again? | routing, reply |
| HLD2-19 | stop playing the song | Stop playing the song. | music | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| HLD2-23 | what is 45 plus 67 | What is 45 to 67? | calc | llm (llm: llm) | If you’re looking for the difference, 67 minus 45 is 22. If you mean the numbers in between, it’s 45, 46, 47, …, 67. Let me know which one you wanted! | routing, reply |
| HLD2-24 | what's fifteen percent of 80 | worth 15% of 80% | calc | llm (llm: llm) | 15 percent of 80 percent is 12 percent. | routing, reply |

## Runner errors (not Friday failures; not in the totals)

| Id | Text | Kind | Detail |
|---|---|---|---|

## No audio (not in the totals; record or fix these WAVs)

| Id | Text | Why |
|---|---|---|

## Rows with no effect spec (not in the totals; add expected_effect to the CSV)

| Id | Text | Routed | Reply |
|---|---|---|---|

## LLM usage

- Calls made by Friday: 8. Answered by: {'groq': 8}.
- Calls that failed on every provider: 0.
- Provider failures (including ones the backup covered): none.
- Hosts the guard blocked: none.

## Wording warnings (heuristic, NOT scored)

A reply from the plain LLM that sounds like it did a skill's job (matched by a simple wording pattern, so it can miss real cases and flag harmless ones). Read the replies yourself.

| Id | Text | Matched phrase | Reply |
|---|---|---|---|

## Every row

| Id | Status | Text | Heard | Routed | Reply |
|---|---|---|---|---|---|
| HLD2-01 | fail | add eggs to my grocery list | Add x to my grocery list | lists | Okay, I added x to your grocery list. |
| HLD2-02 | fail | what all is on my shopping list | What all is on my shopping list? | catch | Sorry, I didn't catch that. Please say it again. |
| HLD2-03 | fail | remove milk from the grocery list | Remove milk from a glossary list. | lists | I couldn't find milk on your glossary list. |
| HLD2-04 | pass | put call mom on my to-do list | Put call mom on my to-do list | lists | Okay, I added call mom to your todo list. |
| HLD2-05 | fail | add sunscreen and a towel to my packing list | I had sunscreen and it doubled to my packing list. | catch | Sorry, I didn't catch that. Please say it again. |
| HLD2-06 | pass | make a note that the meeting moved to friday | Make a note that the meeting moved to Friday. | lists | Okay, noted: the meeting moved to friday. |
| HLD2-07 | fail | remind me to call the bank at three thirty | Remind me to call the bank at 330. | catch | Sorry, I didn't catch that. Please say it again. |
| HLD2-08 | fail | set a timer for fifteen minutes | Set it MF for 15 minutes. | llm | I didn't catch that. Could you say it again? |
| HLD2-09 | pass | wake me up at six tomorrow | Wake me up at 6 tomorrow | reminders | Okay, alarm set for tomorrow at 6 AM. |
| HLD2-10 | pass | remind me in two hours to take out the trash | Remind me in two hours to take out the trash. | reminders | Okay, I'll remind you to take out the trash in 2 hours. |
| HLD2-11 | pass | set an alarm for nine pm | Set an alarm for 9pm. | reminders | Okay, alarm set for 9 PM. |
| HLD2-12 | pass | remind me to submit the form tomorrow at nine am | Remind me to submit the form tomorrow at 9am. | reminders | Okay, I'll remind you to submit the form tomorrow at 9 AM. |
| HLD2-13 | pass | play some Arijit Singh | Play some original notes in the description. | music | Playing some original notes in the description. |
| HLD2-14 | pass | play the song Kesariya | Play the song in case area. | music | Playing in case area. |
| HLD2-15 | fail | pause this for a bit | Pause this for a bit. | llm | I didn't catch that—could you please say it again? |
| HLD2-16 | pass | play the next track | Play the next track | music | Skipping. |
| HLD2-17 | pass | make it louder | Make it louder | music | Volume 60 percent. |
| HLD2-18 | pass | put the volume at forty percent | Put the volume at 40 percent | music | Volume 40 percent. |
| HLD2-19 | fail | stop playing the song | Stop playing the song. | catch | Sorry, I didn't catch that. Please say it again. |
| HLD2-20 | pass | which day of the week is it | Which day of the week is it? | clock | Today is Saturday, 17 October 2026. |
| HLD2-21 | pass | what's the time now | What's the time now? | clock | It is 10:00 AM. |
| HLD2-22 | pass | tell me today's date | Tell me today's date | clock | Today is Saturday, 17 October 2026. |
| HLD2-23 | fail | what is 45 plus 67 | What is 45 to 67? | llm | If you’re looking for the difference, 67 minus 45 is 22. If you mean the numbers in between, it’s 45, 46, 47, …, 67. Let me know which one you wanted! |
| HLD2-24 | fail | what's fifteen percent of 80 | worth 15% of 80% | llm | 15 percent of 80 percent is 12 percent. |
| HLD2-25 | pass | what is 144 divided by 12 | What is 144 divided by 12? | calc | The answer is 12. |
| HLD2-26 | pass | what's nine squared | What's 9 squared? | calc | The answer is 81. |
| HLD2-27 | pass | explain what an API is in simple words | Explain what an API is in simple words. | llm | An API is a set of rules that lets software talk to each other. Think of it like a menu in a restaurant: you pick what you want, and the kitchen—another program—prepares it for you. |
| HLD2-28 | pass | give me a tip for a job interview | Give me a tip for a job interview | llm | A great tip is to think of a few stories that show how you solved problems or worked well in teams, and keep them ready to share. This helps you illustrate your skills with clear, real examples. Make sure you practice the stories so they feel natural when you talk about them. |
| HLD2-29 | pass | what's a good name for a pet dog | What's a good name for a pet dog? | llm | How about Milo, Luna or Bear? Those names are easy to call out and they suit many dog personalities. If none feels right, try thinking of something that reminds you of a favorite hobby or place. |
| HLD2-30 | pass | why is the ocean salty | Why is the ocean salty? | llm | The ocean is salty because water from rivers carries tiny bits of minerals and salts that dissolve as the water travels to the sea. When the water evaporates, it leaves those minerals behind, concentrating the salt. This process has been happening for billions of years. |
