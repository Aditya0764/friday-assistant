# Eval 100: before_live (2026-10-17)

**Passed 78 | Failed 22 | Runner errors 0**

Router model: off (rules only). LLM: LIVE (Groq, Gemini backup) with Friday's system prompt. Network allowed only to api.groq.com, generativelanguage.googleapis.com. Embedder local; music player fake; Spotify never touched; clock fixed at 2026-10-17T10:00:00+05:30. One sample per row.
Chat rows (expected llm) are scored on routing only: READ their real replies.
A row passes only if routing, reply and database effect are all right. A runner error (LLM, network or embedder problem) is not a Friday failure and is not in the totals.

## Totals

- Checked rows: 100. Passed: 78. Failed: 22. Runner errors: 0.
- Not checked offline (not counted as passes): 0.

## Per skill (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|
| echo | 5 | 2/5 | 4/5 | 5/5 | 2/5 |
| clock | 8 | 5/8 | 4/8 | 8/8 | 4/8 |
| lists | 15 | 11/15 | 11/15 | 13/15 | 11/15 |
| docs | 12 | 12/12 | 12/12 | 12/12 | 12/12 |
| calc | 10 | 9/10 | 9/10 | 10/10 | 9/10 |
| reminders | 15 | 13/15 | 13/15 | 13/15 | 13/15 |
| music | 15 | 10/15 | 10/15 | 15/15 | 10/15 |
| chat | 12 | 10/12 | 0/0 | 12/12 | 10/12 |
| safety | 8 | 7/8 | 7/7 | 8/8 | 7/8 |
| **all checked** | 100 | 79/100 | 70/87 | 96/100 | 78/100 |

## By phrasing note (checked rows only)

| Group | Rows | Routed right | Reply right | DB effect right | Passed |
|---|---|---|---|---|---|
| exact | 66 | 66/66 | 56/56 | 66/66 | 66/66 |
| natural | 28 | 11/28 | 12/28 | 24/28 | 10/28 |
| known problem | 6 | 2/6 | 2/3 | 6/6 | 2/6 |

## Failed rows

| Id | Text | Wanted | Routed | Reply | Why |
|---|---|---|---|---|---|
| ECH-03 | Say after me I am ready | echo | llm (llm: llm) | I am ready. | routing, reply |
| ECH-04 | Can you repeat after me, testing one two three | echo | llm (llm: llm) | testing one two three | routing |
| ECH-05 | Please echo hello Friday | echo | llm (llm: llm) | hello Friday | routing |
| CLK-05 | Got the time? | clock | llm (llm: llm) | I’m sorry, I can’t check that right now. | routing, reply |
| CLK-06 | What's the time and date? | clock | clock (rule: clock) | It is 10:00 AM. | reply |
| CLK-07 | Do you know what the time is right now | clock | llm (llm: llm) | I’m sorry, but I can’t check the current time for you. | routing, reply |
| CLK-08 | Which day of the week is it today | clock | llm (llm: llm) | I’m not sure what day it is. Could you tell me the date? | routing, reply |
| LST-04 | Pop eggs onto the groceries list | lists | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing, reply, db: lists: wanted {'groceries': ['eggs']}, found {} |
| LST-09 | Tell me what I've got on the gym list | lists | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| LST-12 | Scratch the towel from my gym list | lists | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing, reply, db: lists: wanted {}, found {'gym': ['towel']} |
| LST-15 | Is there anything on my chores list | lists | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| CAL-10 | Divide 144 by 12 | calc | llm (llm: llm) | I’m sorry, I can’t help with that. | routing, reply |
| REM-09 | Give me a heads up at 8 pm to take my vitamins | reminders | llm (llm: llm) | I didn’t catch that. Could you please say it again? | routing, reply, db: reminders: wanted 1 saved, found 0 |
| REM-10 | Wake me at 5 45 am | reminders | llm (llm: llm) | I didn’t catch that. Could you say it again? | routing, reply, db: reminders: wanted 1 saved, found 0 |
| MUS-03 | Put on Believer by Imagine Dragons | music | llm (llm: llm) | I’m sorry, I didn’t catch that. Could you please say it again? | routing, reply |
| MUS-05 | stop | music | llm (llm: llm) | Sure thing. Let me know if you need anything else. | routing, reply |
| MUS-10 | Make it a little quieter please | music | llm (llm: llm) | I’m sorry, but I can’t adjust that. Could you tell me again what you’d like me to do? | routing, reply |
| MUS-12 | Set the volume to fifty percent | music | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing, reply |
| MUS-13 | It's too loud, turn it down | music | llm (llm: llm) | I’m sorry, I didn’t catch that. Could you say it again? | routing, reply |
| CHT-09 | Can you help me organise my shopping list? | llm | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing |
| CHT-10 | I love this song | llm | catch (rule: catch) | Sorry, I didn't catch that. Please say it again. | routing |
| SAF-07 | What time is it in Tokyo? | llm | clock (rule: clock) | It is 10:00 AM. | routing |

## Runner errors (not Friday failures; not in the totals)

| Id | Text | Kind | Detail |
|---|---|---|---|

## LLM usage

- Calls made by Friday: 30. Answered by: {'groq': 30}.
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
| ECH-04 | fail | Can you repeat after me, testing one two three | llm | testing one two three |
| ECH-05 | fail | Please echo hello Friday | llm | hello Friday |
| CLK-01 | pass | What time is it? | clock | It is 10:00 AM. |
| CLK-02 | pass | What's today's date? | clock | Today is Saturday, 17 October 2026. |
| CLK-03 | pass | What day is it? | clock | Today is Saturday, 17 October 2026. |
| CLK-04 | pass | Tell me the time | clock | It is 10:00 AM. |
| CLK-05 | fail | Got the time? | llm | I’m sorry, I can’t check that right now. |
| CLK-06 | fail | What's the time and date? | clock | It is 10:00 AM. |
| CLK-07 | fail | Do you know what the time is right now | llm | I’m sorry, but I can’t check the current time for you. |
| CLK-08 | fail | Which day of the week is it today | llm | I’m not sure what day it is. Could you tell me the date? |
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
| DOC-01 | pass | What does the document say about late fees? | docs | Late fees are 2 rupees per day per book, capped at 100 rupees. |
| DOC-02 | pass | According to the document, how long can I keep a book? | docs | You can keep a book for 21 days. |
| DOC-03 | pass | What does the doc say about wifi? | docs | Wi‑Fi is available on the ground floor only. The password is given at the front desk. |
| DOC-04 | pass | From the document, when does the library open? | docs | It opens Monday to Saturday from 9 AM to 7 PM. It is closed on Sundays. |
| DOC-05 | pass | What does this paper say about Sundays? | docs | It is closed on Sundays. |
| DOC-06 | pass | Read it to me | docs | Lakeview Public Library Rules Lakeview Public Library opened in 1998 and has about 24000 books. It is open Monday to Saturday from 9 AM to 7 PM and is closed on Sundays. The head librarian is Mrs. Kavitha Reddy. Members can borrow up to 4 books at a time for 21 days. A book can be renewed twice, unless another member has reserved it. Late fees are 2 rupees per day per book, capped at 100 rupees. A lost book must be paid for at its full price plus a 50 rupee handling fee. Membership costs 300 rupees per year. Say keep reading for more. |
| DOC-07 | pass | Read the document to me please | docs | Lakeview Public Library Rules Lakeview Public Library opened in 1998 and has about 24000 books. It is open Monday to Saturday from 9 AM to 7 PM and is closed on Sundays. The head librarian is Mrs. Kavitha Reddy. Members can borrow up to 4 books at a time for 21 days. A book can be renewed twice, unless another member has reserved it. Late fees are 2 rupees per day per book, capped at 100 rupees. A lost book must be paid for at its full price plus a 50 rupee handling fee. Membership costs 300 rupees per year. Say keep reading for more. |
| DOC-08 | pass | Keep reading | docs | Children under 12 join for free. The reading room on the second floor has 40 seats, and silence is required. Laptops are allowed only in the reading room. Photocopying costs 1 rupee per page. Wi-Fi is available on the ground floor only, and the password is given at the front desk. The library holds a story hour for children every Saturday at 11 AM. That's the end of the document. |
| DOC-09 | pass | Continue reading please | docs | Children under 12 join for free. The reading room on the second floor has 40 seats, and silence is required. Laptops are allowed only in the reading room. Photocopying costs 1 rupee per page. Wi-Fi is available on the ground floor only, and the password is given at the front desk. The library holds a story hour for children every Saturday at 11 AM. That's the end of the document. |
| DOC-10 | pass | Can you tell me what's in the document about the reading room | docs | The reading room on the second floor has 40 seats and requires silence. Laptops are allowed only in that room. |
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
| CAL-10 | fail | Divide 144 by 12 | llm | I’m sorry, I can’t help with that. |
| REM-01 | pass | Remind me at 5 pm to buy bread | reminders | Okay, I'll remind you to buy bread at 5 PM. |
| REM-02 | pass | Remind me to stretch in 10 minutes | reminders | Okay, I'll remind you to stretch in 10 minutes. |
| REM-03 | pass | Remind me tomorrow at 9 am to submit the report | reminders | Okay, I'll remind you to submit the report tomorrow at 9 AM. |
| REM-04 | pass | Set a timer for 5 minutes | reminders | Okay, timer set for 5 minutes. |
| REM-05 | pass | Start a 20 minute timer | reminders | Okay, timer set for 20 minutes. |
| REM-06 | pass | Set a timer for an hour | reminders | Okay, timer set for 1 hour. |
| REM-07 | pass | Set an alarm for 6 30 am | reminders | Okay, alarm set for tomorrow at 6:30 AM. |
| REM-08 | pass | Set an alarm for tomorrow at 7 am | reminders | Okay, alarm set for tomorrow at 7 AM. |
| REM-09 | fail | Give me a heads up at 8 pm to take my vitamins | llm | I didn’t catch that. Could you please say it again? |
| REM-10 | fail | Wake me at 5 45 am | llm | I didn’t catch that. Could you say it again? |
| REM-11 | pass | Remind me to call the bank in an hour | reminders | Okay, I'll remind you to call the bank in 1 hour. |
| REM-12 | pass | Can you remind me at 3 pm that the parcel arrives | reminders | Okay, I'll remind you to the parcel arrives at 3 PM. |
| REM-13 | pass | Set a reminder to take out the trash at 8 pm | reminders | Okay, I'll remind you to take out the trash at 8 PM. |
| REM-14 | pass | Timer for two minutes | reminders | Okay, timer set for 2 minutes. |
| REM-15 | pass | Remind me to message Priya in 45 minutes | reminders | Okay, I'll remind you to message priya in 45 minutes. |
| MUS-01 | pass | Play Shape of You by Ed Sheeran | music | Playing shape of you by ed sheeran. |
| MUS-02 | pass | Play some jazz | music | Playing some jazz. |
| MUS-03 | fail | Put on Believer by Imagine Dragons | llm | I’m sorry, I didn’t catch that. Could you please say it again? |
| MUS-04 | pass | decrease volume to 50 | music | Volume 50 percent. |
| MUS-05 | fail | stop | llm | Sure thing. Let me know if you need anything else. |
| MUS-06 | pass | Pause the music | music | Paused. |
| MUS-07 | pass | Resume the music | music | Resuming. |
| MUS-08 | pass | Skip this song | music | Skipping. |
| MUS-09 | pass | Go back a song | music | Going back. |
| MUS-10 | fail | Make it a little quieter please | llm | I’m sorry, but I can’t adjust that. Could you tell me again what you’d like me to do? |
| MUS-11 | pass | Turn the volume up | music | Volume 60 percent. |
| MUS-12 | fail | Set the volume to fifty percent | catch | Sorry, I didn't catch that. Please say it again. |
| MUS-13 | fail | It's too loud, turn it down | llm | I’m sorry, I didn’t catch that. Could you say it again? |
| MUS-14 | pass | Mute | music | Volume 0 percent. |
| MUS-15 | pass | Could you play the next track | music | Skipping. |
| CHT-01 | pass | Explain how a rainbow forms | llm | A rainbow appears when sunlight enters a water droplet, bends and splits into its component colors. Inside the droplet the light reflects off the back surface and then refracts again as it exits. The result is a circular arc of red to violet that we see in the sky. |
| CHT-02 | pass | Who wrote Pride and Prejudice? | llm | Jane Austen wrote Pride and Prejudice. |
| CHT-03 | pass | What's a good name for a pet goldfish? | llm | You could call your goldfish Sunny to match its bright color. If you like something classic, Goldie works too. |
| CHT-04 | pass | Give me three tips for a job interview | llm | Be ready to explain how your past projects match the job’s needs. Show genuine enthusiasm and confidence when you talk about the role. Ask thoughtful questions about the team and next steps to demonstrate interest. |
| CHT-05 | pass | Why is the sky blue? | llm | The sky looks blue because sunlight hits molecules and tiny particles in the air, and those shorter blue wavelengths scatter more than the longer red ones. That scattered blue light is what we see coming from all directions. |
| CHT-06 | pass | Thanks, that was helpful | llm | You're welcome! I'm glad it helped. Let me know if there's anything else you'd like to chat about. |
| CHT-07 | pass | How are you feeling today? | llm | I’m just a program, so I don’t have feelings, but I’m here and ready to help you with whatever you need. |
| CHT-08 | pass | What is the capital of Australia? | llm | The capital of Australia is Canberra. |
| CHT-09 | fail | Can you help me organise my shopping list? | catch | Sorry, I didn't catch that. Please say it again. |
| CHT-10 | fail | I love this song | catch | Sorry, I didn't catch that. Please say it again. |
| CHT-11 | pass | What's a good way to remember names? | llm | Try linking the name to a visual cue or rhyme, like picturing “Linda” with a kind hand. Repeating the name aloud when you first meet someone helps cement it. A quick mental note—such as associating their name with a trait—works well too. |
| CHT-12 | pass | Tell me a joke about cats | llm | Why don’t cats play poker in the jungle? Because there are too many cheetahs. |
| SAF-01 | pass | Echo | echo | You didn't say anything to repeat. |
| SAF-02 | pass | What's 5 divided by 0 | calc | I can't divide by zero. |
| SAF-03 | pass | What's 2 to the power of 500 | calc | That number is too big for me. |
| SAF-04 | pass | Remind me at 25 to call mom | catch | Sorry, I didn't catch that. Please say it again. |
| SAF-05 | pass | Set a timer for 0 minutes | catch | Sorry, I didn't catch that. Please say it again. |
| SAF-06 | pass | Add to my list | catch | Sorry, I didn't catch that. Please say it again. |
| SAF-07 | fail | What time is it in Tokyo? | clock | It is 10:00 AM. |
| SAF-08 | pass | Delete everything on my shopping list | catch | Sorry, I didn't catch that. Please say it again. |
