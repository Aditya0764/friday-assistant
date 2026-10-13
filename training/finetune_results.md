# T-04 fine-tune: DistilBERT (MASSIVE en-US, 5 mapped classes)

Measured 13 Oct 2026 on Kaggle (one Tesla T4, fp16 autocast), notebook friday-router-t01.
torch 2.11.0+cu128, transformers 5.16.1. Plain PyTorch loop (no Trainer).
Data: MASSIVE 1.1 en-US with training/intent_mapping.json (train 11514 / dev 2033 / test 2974).
Model: distilbert-base-uncased (67.0M params), input = utt only, max length 64 (no rows truncated).
Settings (starting guesses, NOT tuned): seed 42, 4 epochs, batch 32, lr 5e-5, AdamW wd 0.01,
10% warmup then linear decay, grad clip 1.0.
Checkpoint chosen by dev macro-F1 (best epoch 3). Test split scored once, with that checkpoint.

## Training curve (dev)
| epoch | train loss | dev acc | dev macro-F1 | seconds |
|---|---|---|---|---|
| 1 | 0.3949 | 0.9685 | 0.9346 | 25.5 |
| 2 | 0.0938 | 0.9710 | 0.9395 | 24.0 |
| 3 | 0.0459 | 0.9739 | 0.9458 | 24.4 |
| 4 | 0.0199 | 0.9734 | 0.9446 | 24.8 |
Total training time 99.3 s.

## Test results (best-dev checkpoint)
Accuracy 0.9657, macro-F1 0.9326

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| lists_notes | 0.925 | 0.873 | 0.899 | 142 |
| math_time | 0.936 | 0.903 | 0.919 | 113 |
| music | 0.931 | 0.849 | 0.888 | 238 |
| other | 0.972 | 0.985 | 0.979 | 2290 |
| timers_reminders | 0.974 | 0.984 | 0.979 | 191 |

## Versus the baseline (training/baseline_results.md)
| | TF-IDF + logreg | DistilBERT |
|---|---|---|
| Test accuracy | 0.9519 | 0.9657 |
| Test macro-F1 | 0.9066 | 0.9326 |

## Caveats
- One run, one seed. Hyperparameters were not tuned; the baseline got a 6-config search, this got one config.
- 5 classes only: doc_qa has no MASSIVE rows (own-phrasing set, T-06).
- The "remind" relabel rule means the model may partly learn that word.
- MASSIVE-only numbers. Own-phrasing accuracy is reported separately (T-06).
- Epoch 4 dev dipped slightly after epoch 3 (mild overfitting sign).
- The model checkpoint is not in git (models/ is ignored).