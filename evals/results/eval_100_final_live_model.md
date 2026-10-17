# Eval 100: final_live_model (2026-10-17)

**Passed 96 | Failed 4 | Runner errors 0**

Router model: ON (local, models/router_v2). LLM: LIVE (Groq, Gemini backup) with Friday's system prompt. Network allowed only to api.groq.com, generativelanguage.googleapis.com. Embedder local; music player fake; Spotify never touched; clock fixed at 2026-10-17T10:00:00+05:30. One sample per row.
Chat rows (expected llm) are scored on routing only: READ their real replies.
A row passes only if routing, reply and database effect are all right. A runner error (LLM, network or embedder problem) is not a Friday failure and is not in the totals.

## Totals

- Checked rows: 100. Passed: 96. Failed: 4. Runner errors: 0.
- Not checked offline (not counted as passes): 0.
- No effect spec (not passed, not failed; fix the CSV): 0.

## Per skill (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|
| echo | 5 | 4/5 | 4/5 | 5/5 | 4/5 |
| clock | 8 | 8/8 | 8/8 | 8/8 | 8/8 |
| lists | 15 | 15/15 | 15/15 | 15/15 | 15/15 |
| docs | 12 | 12/12 | 12/12 | 12/12 | 12/12 |
| calc | 10 | 10/10 | 10/10 | 10/10 | 10/10 |
| reminders | 15 | 15/15 | 15/15 | 15/15 | 15/15 |
| music | 15 | 15/15 | 15/15 | 15/15 | 15/15 |
| chat | 12 | 10/12 | 0/0 | 12/12 | 10/12 |
| safety | 8 | 7/8 | 7/7 | 8/8 | 7/8 |
| **all checked** | 100 | 96/100 | 86/87 | 100/100 | 96/100 |

## By phrasing note (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|
| exact | 66 | 66/66 | 56/56 | 66/66 | 66/66 |
| natural | 28 | 27/28 | 27/28 | 28/28 | 27/28 |
| known problem | 6 | 3/6 | 3/3 | 6/6 | 3/6 |

## Failed rows

| Id | Text | Wanted | Routed | Reply | Why |
|---|---|---|---|---|---|
| ECH-03 | Say after me I am ready | echo | llm (llm: llm [model other 0.99]) | I am ready. | routing, reply |
| CHT-09 | Can you help me organise my shopping list? | llm | catch (model: catch [model lists_notes 1.00]) | Sorry, I didn't catch that. Please say it again. | routing |
| CHT-10 | I love this song | llm | catch (rule: catch [model other 1.00]) | Sorry, I didn't catch that. Please say it again. | routing |
| SAF-07 | What time is it in Tokyo? | llm | catch (model: catch [model math_time 1.00]) | Sorry, I didn't catch that. Please say it again. | routing |

## Runner errors (not Friday failures; not in the totals)

| Id | Text | Kind | Detail |
|---|---|---|---|

## Rows with no effect spec (not in the totals; add expected_effect to the CSV)

| Id | Text | Routed | Reply |
|---|---|---|---|

## LLM usage

- Calls made by Friday: 29. Answered by: {'groq': 29}.
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
| ECH-01 | pass | Repeat after me, good morning | echo | good morning |
| ECH-02 | pass | Echo the quick brown fox | echo | the quick brown fox |
| ECH-03 | fail | Say after me I am ready | llm | I am ready. |
| ECH-04 | pass | Can you repeat after me, testing one two three | echo | testing one two three |
| ECH-05 | pass | Please echo hello Friday | echo | hello friday |
| CLK-01 | pass | What time is it? | clock | It is 10:00 AM. |
| CLK-02 | pass | What's today's date? | clock | Today is Saturday, 17 October 2026. |
| CLK-03 | pass | What day is it? | clock | Today is Saturday, 17 October 2026. |
| CLK-04 | pass | Tell me the time | clock | It is 10:00 AM. |
| CLK-05 | pass | Got the time? | clock | It is 10:00 AM. |
| CLK-06 | pass | What's the time and date? | clock | It is 10:00 AM. Today is Saturday, 17 October 2026. |
| CLK-07 | pass | Do you know what the time is right now | clock | It is 10:00 AM. |
| CLK-08 | pass | Which day of the week is it today | clock | Today is Saturday, 17 October 2026. |
| LST-01 | pass | Add bananas to my shopping list | lists | Okay, I added bananas to your shopping list. |
| LST-02 | pass | Add eggs and bread to my grocery list | lists | Okay, I added eggs and bread to your grocery list. |
| LST-03 | pass | Put socks on my packing list | lists | Okay, I added socks to your packing list. |
| LST-04 | pass | Pop eggs onto the groceries list | lists | Okay, I added eggs to your groceries list. |
| LST-05 | pass | Could you add call the dentist to my to do list | lists | Okay, I added call the dentist to your todo list. |
| LST-06 | pass | What's on my list | lists | On your list: eggs. |
| LST-07 | pass | What's on my shopping list? | lists | On your shopping list: bananas and rice. |
| LST-08 | pass | Read me my packing list | lists | On your packing list: socks. |
| LST-09 | pass | Tell me what I've got on the gym list | lists | On your gym list: towel. |
| LST-10 | pass | Remove bananas from my shopping list | lists | Okay, I removed bananas from your shopping list. |
| LST-11 | pass | Take rice off the shopping list | lists | Okay, I removed rice from your shopping list. |
| LST-12 | pass | Scratch the towel from my gym list | lists | Okay, I removed towel from your gym list. |
| LST-13 | pass | Take a note that the demo is on Friday | lists | Okay, noted: the demo is on friday. |
| LST-14 | pass | Read my notes | lists | Your notes: buy a charger. |
| LST-15 | pass | Is there anything on my chores list | lists | Your chores list is empty. |
| DOC-01 | pass | What does the document say about late fees? | docs | Late fees are 2 rupees per day per book. The total fee is capped at 100 rupees. That's what the document says about late fees. |
| DOC-02 | pass | According to the document, how long can I keep a book? | docs | You can borrow a book for 21 days. That is the borrowing period. |
| DOC-03 | pass | What does the doc say about wifi? | docs | Wi‑Fi is available on the ground floor only. The password is given at the front desk. |
| DOC-04 | pass | From the document, when does the library open? | docs | It opens Monday to Saturday. The hours are 9 AM to 7 PM. |
| DOC-05 | pass | What does this paper say about Sundays? | docs | It is closed on Sundays. |
| DOC-06 | pass | Read it to me | docs | Lakeview Public Library Rules Lakeview Public Library opened in 1998 and has about 24000 books. It is open Monday to Saturday from 9 AM to 7 PM and is closed on Sundays. The head librarian is Mrs. Kavitha Reddy. Members can borrow up to 4 books at a time for 21 days. A book can be renewed twice, unless another member has reserved it. Late fees are 2 rupees per day per book, capped at 100 rupees. A lost book must be paid for at its full price plus a 50 rupee handling fee. Membership costs 300 rupees per year. Say keep reading for more. |
| DOC-07 | pass | Read the document to me please | docs | Lakeview Public Library Rules Lakeview Public Library opened in 1998 and has about 24000 books. It is open Monday to Saturday from 9 AM to 7 PM and is closed on Sundays. The head librarian is Mrs. Kavitha Reddy. Members can borrow up to 4 books at a time for 21 days. A book can be renewed twice, unless another member has reserved it. Late fees are 2 rupees per day per book, capped at 100 rupees. A lost book must be paid for at its full price plus a 50 rupee handling fee. Membership costs 300 rupees per year. Say keep reading for more. |
| DOC-08 | pass | Keep reading | docs | Children under 12 join for free. The reading room on the second floor has 40 seats, and silence is required. Laptops are allowed only in the reading room. Photocopying costs 1 rupee per page. Wi-Fi is available on the ground floor only, and the password is given at the front desk. The library holds a story hour for children every Saturday at 11 AM. That's the end of the document. |
| DOC-09 | pass | Continue reading please | docs | Children under 12 join for free. The reading room on the second floor has 40 seats, and silence is required. Laptops are allowed only in the reading room. Photocopying costs 1 rupee per page. Wi-Fi is available on the ground floor only, and the password is given at the front desk. The library holds a story hour for children every Saturday at 11 AM. That's the end of the document. |
| DOC-10 | pass | Can you tell me what's in the document about the reading room | docs | The reading room is on the second floor and has 40 seats. Silence is required and laptops are allowed only there. |
| DOC-11 | pass | What does the document say about parking? | docs | That's not in the document. |
| DOC-12 | pass | Read it to me | docs | I don't have a document yet. Paste one in first. |
| CAL-01 | pass | What's 15% of 800? | calc | The answer is 120. |
| CAL-02 | pass | Five plus three | calc | The answer is 8. |
| CAL-03 | pass | What is 12 times 12 | calc | The answer is 144. |
| CAL-04 | pass | Square root of 81 | calc | The answer is 9. |
| CAL-05 | pass | Convert 10 miles to kilometers | calc | 10 miles is 16.09 kilometers. |
| CAL-06 | pass | How many seconds are in 3 minutes | calc | 3 minutes is 180 seconds. |
| CAL-07 | pass | 98.6 degrees Fahrenheit in Celsius | calc | 98.6 degrees Fahrenheit is 37 degrees Celsius. |
| CAL-08 | pass | Twenty five percent of two hundred | calc | The answer is 50. |
| CAL-09 | pass | What's 7 squared | calc | The answer is 49. |
| CAL-10 | pass | Divide 144 by 12 | calc | The answer is 12. |
| REM-01 | pass | Remind me at 5 pm to buy bread | reminders | Okay, I'll remind you to buy bread at 5 PM. |
| REM-02 | pass | Remind me to stretch in 10 minutes | reminders | Okay, I'll remind you to stretch in 10 minutes. |
| REM-03 | pass | Remind me tomorrow at 9 am to submit the report | reminders | Okay, I'll remind you to submit the report tomorrow at 9 AM. |
| REM-04 | pass | Set a timer for 5 minutes | reminders | Okay, timer set for 5 minutes. |
| REM-05 | pass | Start a 20 minute timer | reminders | Okay, timer set for 20 minutes. |
| REM-06 | pass | Set a timer for an hour | reminders | Okay, timer set for 1 hour. |
| REM-07 | pass | Set an alarm for 6 30 am | reminders | Okay, alarm set for tomorrow at 6:30 AM. |
| REM-08 | pass | Set an alarm for tomorrow at 7 am | reminders | Okay, alarm set for tomorrow at 7 AM. |
| REM-09 | pass | Give me a heads up at 8 pm to take my vitamins | reminders | Okay, I'll remind you to take your vitamins at 8 PM. |
| REM-10 | pass | Wake me at 5 45 am | reminders | Okay, alarm set for tomorrow at 5:45 AM. |
| REM-11 | pass | Remind me to call the bank in an hour | reminders | Okay, I'll remind you to call the bank in 1 hour. |
| REM-12 | pass | Can you remind me at 3 pm that the parcel arrives | reminders | Okay, I'll remind you to the parcel arrives at 3 PM. |
| REM-13 | pass | Set a reminder to take out the trash at 8 pm | reminders | Okay, I'll remind you to take out the trash at 8 PM. |
| REM-14 | pass | Timer for two minutes | reminders | Okay, timer set for 2 minutes. |
| REM-15 | pass | Remind me to message Priya in 45 minutes | reminders | Okay, I'll remind you to message priya in 45 minutes. |
| MUS-01 | pass | Play Shape of You by Ed Sheeran | music | Playing shape of you by ed sheeran. |
| MUS-02 | pass | Play some jazz | music | Playing some jazz. |
| MUS-03 | pass | Put on Believer by Imagine Dragons | music | Playing believer by imagine dragons. |
| MUS-04 | pass | decrease volume to 50 | music | Volume 50 percent. |
| MUS-05 | pass | stop | music | Paused. |
| MUS-06 | pass | Pause the music | music | Paused. |
| MUS-07 | pass | Resume the music | music | Resuming. |
| MUS-08 | pass | Skip this song | music | Skipping. |
| MUS-09 | pass | Go back a song | music | Going back. |
| MUS-10 | pass | Make it a little quieter please | music | Volume 40 percent. |
| MUS-11 | pass | Turn the volume up | music | Volume 60 percent. |
| MUS-12 | pass | Set the volume to fifty percent | music | Volume 50 percent. |
| MUS-13 | pass | It's too loud, turn it down | music | Volume 40 percent. |
| MUS-14 | pass | Mute | music | Volume 0 percent. |
| MUS-15 | pass | Could you play the next track | music | Skipping. |
| CHT-01 | pass | Explain how a rainbow forms | llm | A rainbow forms when sunlight shines onto raindrops and is refracted, reflected inside the drops, and refracted again as it exits. This bending splits the light into its component colors, creating a circular arc. The effect depends on the angle between the sun, the raindrops, and your eye, usually about 42 degrees for the red edge. |
| CHT-02 | pass | Who wrote Pride and Prejudice? | llm | The novel Pride and Prejudice was written by Jane Austen. |
| CHT-03 | pass | What's a good name for a pet goldfish? | llm | How about “Glimmer”? It’s short, easy to call, and captures that shiny goldfish look. |
| CHT-04 | pass | Give me three tips for a job interview | llm | Ask thoughtful questions, dress appropriately, and practice concise answers to common questions. |
| CHT-05 | pass | Why is the sky blue? | llm | The sky looks blue because sunlight is scattered by air molecules, and the shorter blue wavelengths scatter more than the longer red wavelengths. This scattered blue light reaches our eyes from all directions. As a result we see a blue sky most of the time. |
| CHT-06 | pass | Thanks, that was helpful | llm | You're very welcome! If you have any more questions or need anything else, just let me know. |
| CHT-07 | pass | How are you feeling today? | llm | I’m feeling great today, thanks for asking! How can I help you? |
| CHT-08 | pass | What is the capital of Australia? | llm | The capital of Australia is Canberra. |
| CHT-09 | fail | Can you help me organise my shopping list? | catch | Sorry, I didn't catch that. Please say it again. |
| CHT-10 | fail | I love this song | catch | Sorry, I didn't catch that. Please say it again. |
| CHT-11 | pass | What's a good way to remember names? | llm | One trick is to repeat the name right away and use it a few times while you talk. Try linking the name to something about the person—a feature, hobby, or a rhyme. When you see their face again, pause and say the name in your head to reinforce it. |
| CHT-12 | pass | Tell me a joke about cats | llm | Why did the cat sit in the shade? Because it didn't want to be a hot mouse! |
| SAF-01 | pass | Echo | echo | You didn't say anything to repeat. |
| SAF-02 | pass | What's 5 divided by 0 | calc | I can't divide by zero. |
| SAF-03 | pass | What's 2 to the power of 500 | calc | That number is too big for me. |
| SAF-04 | pass | Remind me at 25 to call mom | catch | Sorry, I didn't catch that. Please say it again. |
| SAF-05 | pass | Set a timer for 0 minutes | catch | Sorry, I didn't catch that. Please say it again. |
| SAF-06 | pass | Add to my list | catch | Sorry, I didn't catch that. Please say it again. |
| SAF-07 | fail | What time is it in Tokyo? | catch | Sorry, I didn't catch that. Please say it again. |
| SAF-08 | pass | Delete everything on my shopping list | catch | Sorry, I didn't catch that. Please say it again. |
