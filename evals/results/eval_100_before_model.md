# Eval 100: before_model (2026-10-17)

Router model: ON (local, models/router_v2). LLM, embedder and music player are stubs; the clock is fixed at 2026-10-17T10:00:00+05:30. No network.
Chat rows (expected llm) are scored on routing only: the reply is a stub.
A row passes only if routing, reply and database effect are all right.

## Totals

- Checked rows: 93. Passed: 71. Failed: 22.
- Not checked offline (not counted as passes): 7.

## Per skill (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|
| echo | 5 | 2/5 | 2/5 | 5/5 | 2/5 |
| clock | 8 | 5/8 | 4/8 | 8/8 | 4/8 |
| lists | 15 | 11/15 | 11/15 | 13/15 | 11/15 |
| docs | 5 | 5/5 | 5/5 | 5/5 | 5/5 |
| calc | 10 | 9/10 | 9/10 | 10/10 | 9/10 |
| reminders | 15 | 13/15 | 13/15 | 13/15 | 13/15 |
| music | 15 | 10/15 | 10/15 | 15/15 | 10/15 |
| chat | 12 | 10/12 | 0/0 | 12/12 | 10/12 |
| safety | 8 | 7/8 | 7/7 | 8/8 | 7/8 |
| **all checked** | 93 | 72/93 | 61/80 | 89/93 | 71/93 |

## By phrasing note (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|
| exact | 61 | 61/61 | 51/51 | 61/61 | 61/61 |
| natural | 26 | 9/26 | 8/26 | 22/26 | 8/26 |
| known problem | 6 | 2/6 | 2/3 | 6/6 | 2/6 |

## Failed rows

| Id | Text | Wanted | Routed | Reply | Why |
|---|---|---|---|---|---|
| ECH-03 | Say after me I am ready | echo | llm (llm: llm [model other 0.99]) | (stub reply) | routing, reply |
| ECH-04 | Can you repeat after me, testing one two three | echo | llm (llm: llm [model other 1.00]) | (stub reply) | routing, reply |
| ECH-05 | Please echo hello Friday | echo | llm (llm: llm [model other 1.00]) | (stub reply) | routing, reply |
| CLK-05 | Got the time? | clock | catch (model: catch [model math_time 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| CLK-06 | What's the time and date? | clock | clock (rule: clock) | It is 10:00 AM. | reply |
| CLK-07 | Do you know what the time is right now | clock | catch (model: catch [model math_time 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| CLK-08 | Which day of the week is it today | clock | catch (model: catch [model math_time 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| LST-04 | Pop eggs onto the groceries list | lists | catch (model: catch [model lists_notes 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply, db: lists: wanted {'groceries': ['eggs']}, found {} |
| LST-09 | Tell me what I've got on the gym list | lists | catch (model: catch [model lists_notes 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| LST-12 | Scratch the towel from my gym list | lists | catch (model: catch [model lists_notes 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply, db: lists: wanted {}, found {'gym': ['towel']} |
| LST-15 | Is there anything on my chores list | lists | catch (model: catch [model lists_notes 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| CAL-10 | Divide 144 by 12 | calc | catch (model: catch [model math_time 0.99]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| REM-09 | Give me a heads up at 8 pm to take my vitamins | reminders | catch (model: catch [model timers_reminders 0.97]) | Sorry, I didn't catch that. Please say it again. | routing, reply, db: reminders: wanted 1 saved, found 0 |
| REM-10 | Wake me at 5 45 am | reminders | catch (model: catch [model timers_reminders 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply, db: reminders: wanted 1 saved, found 0 |
| MUS-03 | Put on Believer by Imagine Dragons | music | catch (model: catch [model music 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| MUS-05 | stop | music | catch (model: catch [model music 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| MUS-10 | Make it a little quieter please | music | catch (model: catch [model music 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| MUS-12 | Set the volume to fifty percent | music | catch (model: catch [model music 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| MUS-13 | It's too loud, turn it down | music | catch (model: catch [model music 1.00]) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| CHT-09 | Can you help me organise my shopping list? | llm | catch (model: catch [model lists_notes 1.00]) | Sorry, I didn't catch that. Please say it again. | routing |
| CHT-10 | I love this song | llm | catch (rule: catch [model other 1.00]) | Sorry, I didn't catch that. Please say it again. | routing |
| SAF-07 | What time is it in Tokyo? | llm | clock (rule: clock) | It is 10:00 AM. | routing |

## Not checked offline (document questions that need a real LLM)

These are never counted as passes. Routing is shown so a wrong route is still visible.

| Id | Text | Routed | Routing right | Reply (stub) |
|---|---|---|---|---|
| DOC-01 | What does the document say about late fees? | docs | True | (stub reply) |
| DOC-02 | According to the document, how long can I keep a book? | docs | True | (stub reply) |
| DOC-03 | What does the doc say about wifi? | docs | True | (stub reply) |
| DOC-04 | From the document, when does the library open? | docs | True | (stub reply) |
| DOC-05 | What does this paper say about Sundays? | docs | True | (stub reply) |
| DOC-10 | Can you tell me what's in the document about the reading room | docs | True | (stub reply) |
| DOC-11 | What does the document say about parking? | docs | True | (stub reply) |

## Every row

| Id | Status | Text | Routed | Reply |
|---|---|---|---|---|
| ECH-01 | pass | Repeat after me, good morning | echo | good morning |
| ECH-02 | pass | Echo the quick brown fox | echo | the quick brown fox |
| ECH-03 | fail | Say after me I am ready | llm | (stub reply) |
| ECH-04 | fail | Can you repeat after me, testing one two three | llm | (stub reply) |
| ECH-05 | fail | Please echo hello Friday | llm | (stub reply) |
| CLK-01 | pass | What time is it? | clock | It is 10:00 AM. |
| CLK-02 | pass | What's today's date? | clock | Today is Saturday, 17 October 2026. |
| CLK-03 | pass | What day is it? | clock | Today is Saturday, 17 October 2026. |
| CLK-04 | pass | Tell me the time | clock | It is 10:00 AM. |
| CLK-05 | fail | Got the time? | catch | Sorry, I didn't catch that. Please say it again. |
| CLK-06 | fail | What's the time and date? | clock | It is 10:00 AM. |
| CLK-07 | fail | Do you know what the time is right now | catch | Sorry, I didn't catch that. Please say it again. |
| CLK-08 | fail | Which day of the week is it today | catch | Sorry, I didn't catch that. Please say it again. |
| LST-01 | pass | Add bananas to my shopping list | lists | Okay, I added bananas to your shopping list. |
| LST-02 | pass | Add eggs and bread to my grocery list | lists | Okay, I added eggs and bread to your grocery list. |
| LST-03 | pass | Put socks on my packing list | lists | Okay, I added socks to your packing list. |
| LST-04 | fail | Pop eggs onto the groceries list | catch | Sorry, I didn't catch that. Please say it again. |
| LST-05 | pass | Could you add call the dentist to my to do list | lists | Okay, I added call the dentist to your todo list. |
| LST-06 | pass | What's on my list | lists | On your list: eggs. |
| LST-07 | pass | What's on my shopping list? | lists | On your shopping list: bananas and rice. |
| LST-08 | pass | Read me my packing list | lists | On your packing list: socks. |
| LST-09 | fail | Tell me what I've got on the gym list | catch | Sorry, I didn't catch that. Please say it again. |
| LST-10 | pass | Remove bananas from my shopping list | lists | Okay, I removed bananas from your shopping list. |
| LST-11 | pass | Take rice off the shopping list | lists | Okay, I removed rice from your shopping list. |
| LST-12 | fail | Scratch the towel from my gym list | catch | Sorry, I didn't catch that. Please say it again. |
| LST-13 | pass | Take a note that the demo is on Friday | lists | Okay, noted: the demo is on friday. |
| LST-14 | pass | Read my notes | lists | Your notes: buy a charger. |
| LST-15 | fail | Is there anything on my chores list | catch | Sorry, I didn't catch that. Please say it again. |
| DOC-01 | not_checked_offline | What does the document say about late fees? | docs | (stub reply) |
| DOC-02 | not_checked_offline | According to the document, how long can I keep a book? | docs | (stub reply) |
| DOC-03 | not_checked_offline | What does the doc say about wifi? | docs | (stub reply) |
| DOC-04 | not_checked_offline | From the document, when does the library open? | docs | (stub reply) |
| DOC-05 | not_checked_offline | What does this paper say about Sundays? | docs | (stub reply) |
| DOC-06 | pass | Read it to me | docs | Lakeview Public Library Rules Lakeview Public Library opened in 1998 and has about 24000 books. It is open Monday to Saturday from 9 AM to 7 PM and is closed on Sundays. The head librarian is Mrs. Kavitha Reddy. Members can borrow up to 4 books at a time for 21 days. A book can be renewed twice, unless another member has reserved it. Late fees are 2 rupees per day per book, capped at 100 rupees. A lost book must be paid for at its full price plus a 50 rupee handling fee. Membership costs 300 rupees per year. Say keep reading for more. |
| DOC-07 | pass | Read the document to me please | docs | Lakeview Public Library Rules Lakeview Public Library opened in 1998 and has about 24000 books. It is open Monday to Saturday from 9 AM to 7 PM and is closed on Sundays. The head librarian is Mrs. Kavitha Reddy. Members can borrow up to 4 books at a time for 21 days. A book can be renewed twice, unless another member has reserved it. Late fees are 2 rupees per day per book, capped at 100 rupees. A lost book must be paid for at its full price plus a 50 rupee handling fee. Membership costs 300 rupees per year. Say keep reading for more. |
| DOC-08 | pass | Keep reading | docs | Children under 12 join for free. The reading room on the second floor has 40 seats, and silence is required. Laptops are allowed only in the reading room. Photocopying costs 1 rupee per page. Wi-Fi is available on the ground floor only, and the password is given at the front desk. The library holds a story hour for children every Saturday at 11 AM. That's the end of the document. |
| DOC-09 | pass | Continue reading please | docs | Children under 12 join for free. The reading room on the second floor has 40 seats, and silence is required. Laptops are allowed only in the reading room. Photocopying costs 1 rupee per page. Wi-Fi is available on the ground floor only, and the password is given at the front desk. The library holds a story hour for children every Saturday at 11 AM. That's the end of the document. |
| DOC-10 | not_checked_offline | Can you tell me what's in the document about the reading room | docs | (stub reply) |
| DOC-11 | not_checked_offline | What does the document say about parking? | docs | (stub reply) |
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
| CAL-10 | fail | Divide 144 by 12 | catch | Sorry, I didn't catch that. Please say it again. |
| REM-01 | pass | Remind me at 5 pm to buy bread | reminders | Okay, I'll remind you to buy bread at 5 PM. |
| REM-02 | pass | Remind me to stretch in 10 minutes | reminders | Okay, I'll remind you to stretch in 10 minutes. |
| REM-03 | pass | Remind me tomorrow at 9 am to submit the report | reminders | Okay, I'll remind you to submit the report tomorrow at 9 AM. |
| REM-04 | pass | Set a timer for 5 minutes | reminders | Okay, timer set for 5 minutes. |
| REM-05 | pass | Start a 20 minute timer | reminders | Okay, timer set for 20 minutes. |
| REM-06 | pass | Set a timer for an hour | reminders | Okay, timer set for 1 hour. |
| REM-07 | pass | Set an alarm for 6 30 am | reminders | Okay, alarm set for tomorrow at 6:30 AM. |
| REM-08 | pass | Set an alarm for tomorrow at 7 am | reminders | Okay, alarm set for tomorrow at 7 AM. |
| REM-09 | fail | Give me a heads up at 8 pm to take my vitamins | catch | Sorry, I didn't catch that. Please say it again. |
| REM-10 | fail | Wake me at 5 45 am | catch | Sorry, I didn't catch that. Please say it again. |
| REM-11 | pass | Remind me to call the bank in an hour | reminders | Okay, I'll remind you to call the bank in 1 hour. |
| REM-12 | pass | Can you remind me at 3 pm that the parcel arrives | reminders | Okay, I'll remind you to the parcel arrives at 3 PM. |
| REM-13 | pass | Set a reminder to take out the trash at 8 pm | reminders | Okay, I'll remind you to take out the trash at 8 PM. |
| REM-14 | pass | Timer for two minutes | reminders | Okay, timer set for 2 minutes. |
| REM-15 | pass | Remind me to message Priya in 45 minutes | reminders | Okay, I'll remind you to message priya in 45 minutes. |
| MUS-01 | pass | Play Shape of You by Ed Sheeran | music | Playing shape of you by ed sheeran. |
| MUS-02 | pass | Play some jazz | music | Playing some jazz. |
| MUS-03 | fail | Put on Believer by Imagine Dragons | catch | Sorry, I didn't catch that. Please say it again. |
| MUS-04 | pass | decrease volume to 50 | music | Volume 50 percent. |
| MUS-05 | fail | stop | catch | Sorry, I didn't catch that. Please say it again. |
| MUS-06 | pass | Pause the music | music | Paused. |
| MUS-07 | pass | Resume the music | music | Resuming. |
| MUS-08 | pass | Skip this song | music | Skipping. |
| MUS-09 | pass | Go back a song | music | Going back. |
| MUS-10 | fail | Make it a little quieter please | catch | Sorry, I didn't catch that. Please say it again. |
| MUS-11 | pass | Turn the volume up | music | Volume 60 percent. |
| MUS-12 | fail | Set the volume to fifty percent | catch | Sorry, I didn't catch that. Please say it again. |
| MUS-13 | fail | It's too loud, turn it down | catch | Sorry, I didn't catch that. Please say it again. |
| MUS-14 | pass | Mute | music | Volume 0 percent. |
| MUS-15 | pass | Could you play the next track | music | Skipping. |
| CHT-01 | pass | Explain how a rainbow forms | llm | (stub reply) |
| CHT-02 | pass | Who wrote Pride and Prejudice? | llm | (stub reply) |
| CHT-03 | pass | What's a good name for a pet goldfish? | llm | (stub reply) |
| CHT-04 | pass | Give me three tips for a job interview | llm | (stub reply) |
| CHT-05 | pass | Why is the sky blue? | llm | (stub reply) |
| CHT-06 | pass | Thanks, that was helpful | llm | (stub reply) |
| CHT-07 | pass | How are you feeling today? | llm | (stub reply) |
| CHT-08 | pass | What is the capital of Australia? | llm | (stub reply) |
| CHT-09 | fail | Can you help me organise my shopping list? | catch | Sorry, I didn't catch that. Please say it again. |
| CHT-10 | fail | I love this song | catch | Sorry, I didn't catch that. Please say it again. |
| CHT-11 | pass | What's a good way to remember names? | llm | (stub reply) |
| CHT-12 | pass | Tell me a joke about cats | llm | (stub reply) |
| SAF-01 | pass | Echo | echo | You didn't say anything to repeat. |
| SAF-02 | pass | What's 5 divided by 0 | calc | I can't divide by zero. |
| SAF-03 | pass | What's 2 to the power of 500 | calc | That number is too big for me. |
| SAF-04 | pass | Remind me at 25 to call mom | catch | Sorry, I didn't catch that. Please say it again. |
| SAF-05 | pass | Set a timer for 0 minutes | catch | Sorry, I didn't catch that. Please say it again. |
| SAF-06 | pass | Add to my list | catch | Sorry, I didn't catch that. Please say it again. |
| SAF-07 | fail | What time is it in Tokyo? | clock | It is 10:00 AM. |
| SAF-08 | pass | Delete everything on my shopping list | catch | Sorry, I didn't catch that. Please say it again. |
