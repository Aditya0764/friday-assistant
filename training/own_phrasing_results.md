# T-06: own-phrasing evaluation

Script: `training/finetune_router_v2.py`. Data: `own_phrasing_train.txt` (106 lines) and `own_phrasing_test.txt` (90 lines), split by hash from `own_phrasing.txt` (196 lines, 6 classes). No test line appears in train after normalising.

Setup: distilbert-base-uncased, 4 epochs, batch 32, lr 5e-5, seed 42, Kaggle T4. Checkpoint chosen by MASSIVE dev macro-F1, never by own test. Own test scored once per run. Run B was fixed as the primary run before training; C is a sensitivity check; A is a control with no own data.

## Results (90 held-out own lines, one seed each)

| Run | Own accuracy | Own macro-F1 | doc_qa | MASSIVE test acc (5 classes) |
|---|---|---|---|---|
| A: MASSIVE only | 0.6889 (62/90) | 0.6652 | 0/14 | 0.9637 |
| **B: MASSIVE + own x10 (primary)** | **0.8556 (77/90)** | **0.8676** | 9/14 | 0.9654 |
| C: MASSIVE + own x1 | 0.8111 (73/90) | 0.8156 | 8/14 | 0.9644 |

Raw and normalised text gave identical scores, because the own lines are already lowercase typed text.

## Run B per class

| Class | Correct | Precision | Recall | F1 |
|---|---|---|---|---|
| doc_qa | 9 of 14 | 1.000 | 0.643 | 0.783 |
| lists_notes | 12 of 13 | 0.923 | 0.923 | 0.923 |
| math_time | 14 of 18 | 1.000 | 0.778 | 0.875 |
| music | 8 of 9 | 1.000 | 0.889 | 0.941 |
| other | 17 of 17 | 0.586 | 1.000 | 0.739 |
| timers_reminders | 17 of 19 | 1.000 | 0.895 | 0.944 |

## Run B errors (13 of 90)

12 of 13 went to `other`; 1 doc_qa line went to lists_notes. 9 of 13 wrong predictions had confidence 0.95 or higher, so a confidence threshold would not catch most of them.

- All 4 unit-conversion lines in the test half (e.g. "convert 5kg to pounds", "10km in miles").
- All 5 missed doc_qa lines avoid the word "document" (e.g. "what does it say about cricket", "check the file for any information about trees").
- Unseen phrasings: "notify me at 5pm for a meeting with my boss", "mark done for eggs", "go to the next one", "dont let me forget something tomorrow".

## Caveats

- One seed and one run per setting. B vs C is a 4-line difference and is not evidence that x10 is better than x1.
- 90 test lines in total, 9 to 19 per class. An approximate 95% interval for B's accuracy is 77% to 91%. Quote counts next to percentages.
- Some train and test lines are close paraphrases, so these numbers are probably somewhat optimistic.
- Own lines are typed lowercase text, not Whisper output. Capitalisation, punctuation and mishearing are not tested here.
- Lines with the word "remind" were relabelled in the MASSIVE mapping, so the model may partly learn that word.
- Hyperparameters were not tuned.
- MASSIVE has no doc_qa, so doc_qa is learned only from the 15 own train lines (x10).

## Backlog from this run

- More unit-conversion and "file/it" doc phrasings for a later retrain, scored on a fresh test set.
- Hand-label the 109 real Whisper transcripts as an extra check.