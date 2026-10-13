# RAG mini eval results (2026-10-13)

Embeddings: all-MiniLM-L6-v2. LLM: Groq (Gemini fallback). Top-4 chunks.
Scoring is automatic text matching. The tables below show every answer so it can be read.

## Summary

| Setting | Chunk words | Retrieval hit (in-doc) | Answer correct (in-doc) | Refusal correct (not in doc) | All correct |
|---|---|---|---|---|---|
| production | 500 | 16/16 | 16/16 | 4/4 | 20/20 |
| stress | 40 | 14/16 | 14/16 | 4/4 | 18/20 |

## Every answer: production (chunks per document: {'cycling_club.txt': 1, 'friday_notes.pdf': 1, 'library_rules.txt': 1})

| Q | Question | Retrieval hit | Grounded | Correct (auto) | Reply |
|---|---|---|---|---|---|
| 1 | Which key is used for push-to-talk? | True | True | True | The push‑to‑talk key is the Right Ctrl key. |
| 2 | What does Friday fall back to if Groq fails? | True | True | True | Friday falls back to Gemini. |
| 3 | Which device does the music play on? | True | True | True | The music skill plays only on the device named ADI7. It never falls back to another device. |
| 4 | How many turns of conversation does the chat skill remember? | True | True | True | The chat skill remembers the last six turns of conversation. Each turn consists of a user message and Friday’s reply. |
| 5 | What is the table for lists and notes called? | True | True | True | The table for lists and notes is called list_items. It stores all list items and notes. |
| 6 | Which Piper voice does Friday use? | True | True | True | Friday uses Piper with the en_US-amy-medium voice. This voice is used for all text to speech replies. |
| 7 | Who founded the Kaveri Cycling Club? | True | True | True | The Kaveri Cycling Club was founded in 2014 by Meera Rao. |
| 8 | How much do students pay for club membership? | True | True | True | Students pay 900 rupees per year for club membership. |
| 9 | How fast does the Red group ride? | True | True | True | The Red group rides at 30 kilometres per hour. |
| 10 | Who drives the support van? | True | True | True | The support van is driven by Imran Sheikh. |
| 11 | Where is the annual club dinner held? | True | True | True | The annual club dinner is held at the Lalitha Mahal lawn. It takes place in December. |
| 12 | What is the maximum late fee for a book? | True | True | True | Late fees are 2 rupees per day per book, capped at 100 rupees. The maximum fee you can pay is 100 rupees. That is the limit. |
| 13 | How many books can a member borrow at a time? | True | True | True | Members can borrow up to four books at a time. |
| 14 | Who is the head librarian? | True | True | True | Mrs. Kavitha Reddy is the head librarian. She oversees the library's operations. |
| 15 | How many seats are in the reading room? | True | True | True | There are 40 seats in the reading room. Silence is required there. |
| 16 | When is the children's story hour? | True | True | True | The children’s story hour is held every Saturday at 11 AM. |
| 17 | What is the cycling club's Instagram handle? | n/a | False | True | That's not in the document. |
| 18 | Does the library have a cafe? | n/a | False | True | That's not in the document. |
| 19 | What is Friday's wake word? | n/a | False | True | That's not in the document. |
| 20 | Who is the treasurer of the cycling club? | n/a | False | True | That's not in the document. |

## Every answer: stress (chunks per document: {'cycling_club.txt': 7, 'friday_notes.pdf': 10, 'library_rules.txt': 5})

| Q | Question | Retrieval hit | Grounded | Correct (auto) | Reply |
|---|---|---|---|---|---|
| 1 | Which key is used for push-to-talk? | True | True | True | The push‑to‑talk key is the Right Ctrl key. Holding that key while speaking activates Friday. This is the method described in the project notes. |
| 2 | What does Friday fall back to if Groq fails? | True | True | True | Friday falls back to Gemini. That is the backup model used when Groq fails. |
| 3 | Which device does the music play on? | True | True | True | The music plays only on the device named ADI7. |
| 4 | How many turns of conversation does the chat skill remember? | True | True | True | The chat skill remembers the last six turns of conversation. |
| 5 | What is the table for lists and notes called? | True | True | True | The table for lists and notes is called list_items. It is used to store both lists and notes. This is mentioned in the document. |
| 6 | Which Piper voice does Friday use? | True | True | True | Friday uses the en_US‑amy‑medium voice. |
| 7 | Who founded the Kaveri Cycling Club? | True | True | True | The Kaveri Cycling Club was founded by Meera Rao. |
| 8 | How much do students pay for club membership? | False | True | False | Students pay 300 rupees per year for club membership. |
| 9 | How fast does the Red group ride? | True | True | True | The Red group rides at 30 kilometres per hour. They are the fast riders. |
| 10 | Who drives the support van? | True | True | True | The support van is driven by Imran Sheikh. |
| 11 | Where is the annual club dinner held? | True | True | True | The annual club dinner is held at the Lalitha Mahal lawn. It takes place in December. |
| 12 | What is the maximum late fee for a book? | True | True | True | Late fees are 2 rupees per day per book. The fee is capped at 100 rupees. |
| 13 | How many books can a member borrow at a time? | True | True | True | A member can borrow up to 4 books at a time. The library allows each member to take 4 books for a 21‑day period. That is the maximum number of books per borrowing period. |
| 14 | Who is the head librarian? | True | True | True | The head librarian is Mrs. Kavitha Reddy. |
| 15 | How many seats are in the reading room? | True | True | True | The reading room on the second floor has 40 seats. So the library has 40 seats in the reading room. |
| 16 | When is the children's story hour? | False | False | False | That's not in the document. |
| 17 | What is the cycling club's Instagram handle? | n/a | False | True | That's not in the document. |
| 18 | Does the library have a cafe? | n/a | False | True | That's not in the document. |
| 19 | What is Friday's wake word? | n/a | False | True | That's not in the document. |
| 20 | Who is the treasurer of the cycling club? | n/a | False | True | That's not in the document. |
