# T-05 evaluation: DistilBERT router (MASSIVE en-US, 5 mapped classes)

Measured 13 Oct 2026 from the T-04 checkpoint (best dev epoch 3) in the same Kaggle session.
Test accuracy 0.9657, macro-F1 0.9326 (per-class precision/recall/F1: training/finetune_results.md).
Per-class F1 only; per-original-MASSIVE-intent F1 was not computed (error counts by intent below).

## Confusion matrix (test, rows = true, cols = predicted)
| true \ pred | lists_notes | math_time | music | other | timers_reminders |
|---|---|---|---|---|---|
| lists_notes | 124 | 0 | 0 | 18 | 0 |
| math_time | 0 | 102 | 0 | 11 | 0 |
| music | 1 | 1 | 202 | 33 | 1 |
| other | 9 | 6 | 15 | 2256 | 4 |
| timers_reminders | 0 | 0 | 0 | 3 | 188 |

## Confidence-threshold analysis
Rule: a command skips the LLM when the model predicts a skill class (not "other") with confidence >= threshold.
- skips_LLM_% = share of ALL commands that skip the LLM.
- direct_precision = share of those that were routed to the right skill.
- wrong_direct = commands sent straight to a skill that were wrong (includes true "other" sent to a skill).
- skill_cmds_routed_ok_% = share of true skill commands routed directly and correctly.
Skill commands are 684 of 2974 test rows (23.0%), so skips_LLM_% cannot exceed 23.0% on MASSIVE.

Dev:
| threshold | skips_LLM_% | direct_precision | wrong_direct | skill_cmds_routed_ok_% |
|---|---|---|---|---|
| 0.50 | 22.0 | 0.9531 | 21 | 92.4 |
| 0.70 | 21.5 | 0.9634 | 16 | 91.1 |
| 0.80 | 21.3 | 0.9630 | 16 | 90.3 |
| 0.90 | 20.6 | 0.9690 | 13 | 87.9 |
| 0.95 | 20.3 | 0.9709 | 12 | 86.6 |
| 0.99 | 14.1 | 0.9895 | 3 | 61.3 |

Test:
| threshold | skips_LLM_% | direct_precision | wrong_direct | skill_cmds_routed_ok_% |
|---|---|---|---|---|
| 0.50 | 21.9 | 0.9448 | 36 | 90.1 |
| 0.70 | 21.5 | 0.9499 | 32 | 88.7 |
| 0.80 | 21.0 | 0.9536 | 29 | 87.1 |
| 0.90 | 20.5 | 0.9607 | 24 | 85.8 |
| 0.95 | 19.9 | 0.9645 | 21 | 83.5 |
| 0.99 | 14.1 | 0.9833 | 7 | 60.2 |

No threshold is chosen here. Choose it in P6-02 on own-phrasing dev data (MASSIVE's skill share is not Friday's).
Confidence is not a reliable safety filter: 7 wrong direct routes remain at >= 0.99 on test.

## Error analysis (test: 102 errors of 2974)
- skill -> other: 65 (music 33, lists_notes 18, math_time 11, timers_reminders 3). In current Friday, "other" falls to the chat LLM, which cannot act, so these are failed commands, not just slow ones.
- other -> skill: 34 (music 15, lists_notes 9, math_time 6, timers_reminders 4).
- skill -> different skill: 3.
- Top original MASSIVE intent -> predicted: play_music -> other 28, datetime_query -> other 9, lists_remove -> other 8, lists_query -> other 7, play_radio -> music 5, datetime_convert -> math_time 3.
- Reading of 25 random errors (qualitative, not a measured rate): many are label noise or ambiguity (garbled text, calendar items labeled lists, no-context phrases) or mapping artifacts (radio/audiobook/settings are mapped to other but look like music). Some are real misses: song or artist names without a clear cue ("pandora", "play the weekend", "olly play i can't feel my face").
- One example ("remind me that i like that song" predicted as a reminder at 0.922) is consistent with the model leaning on the word "remind" (see the caveat in training/baseline_results.md).
- Do not tune fixes on these test errors; use dev errors and the own-phrasing set (T-06).

## Not covered
- doc_qa has no MASSIVE rows (own-phrasing set, T-06).
- CPU inference speed and ONNX export are measured later (not done yet).
- MASSIVE-only numbers; own-phrasing accuracy is reported separately.