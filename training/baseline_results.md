# T-03 baseline: TF-IDF + logistic regression (MASSIVE en-US, mapped classes)

Measured 13 Oct 2026 on Kaggle (CPU) in notebook friday-router-t01.
Data: MASSIVE 1.1 en-US with training/intent_mapping.json (train 11514 / dev 2033 / test 2974).
Model: TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True) + LogisticRegression(max_iter=2000).
Grid: class_weight in {None, balanced} x C in {1, 10, 100}; chosen by dev macro-F1.
Chosen: class_weight=None, C=100. Test split scored once, for the chosen model only.

Reference: always predicting "other" gives 0.77 test accuracy.

## Dev results
| class_weight | C | dev acc | dev macro-F1 |
|---|---|---|---|
| None | 1 | 0.9503 | 0.8917 |
| None | 10 | 0.9621 | 0.9231 |
| None | 100 | 0.9626 | 0.9244 |
| balanced | 1 | 0.9257 | 0.8660 |
| balanced | 10 | 0.9488 | 0.9005 |
| balanced | 100 | 0.9547 | 0.9101 |

## Test results (chosen model)
Accuracy 0.9519, macro-F1 0.9066

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| lists_notes | 0.915 | 0.838 | 0.875 | 142 |
| math_time | 0.940 | 0.832 | 0.883 | 113 |
| music | 0.851 | 0.866 | 0.858 | 238 |
| other | 0.965 | 0.975 | 0.970 | 2290 |
| timers_reminders | 0.957 | 0.937 | 0.947 | 191 |

## Caveats
- doc_qa has no MASSIVE rows, so it is not in this report (own-phrasing set, T-06).
- Most MASSIVE reminder phrasing is labeled calendar_set; the "remind" rule relabels it, so the model may partly learn that word.
- MASSIVE-only numbers. Own-phrasing accuracy is reported separately (T-06).
- C=100 was the largest value tried.