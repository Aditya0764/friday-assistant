"""T-06: how does the router do on Aditya's own phrasing?

Runs three fine-tunes of distilbert-base-uncased with a 6-class head
(timers_reminders, lists_notes, math_time, music, doc_qa, other) and scores
each one on the held-out own-phrasing test lines:

  A  MASSIVE only (the model has never seen own phrasing; doc_qa is unseen)
  B  MASSIVE + own train lines repeated OWN_REPEAT times  <- primary run
  C  MASSIVE + own train lines once (sensitivity check)

B is the primary run because it was chosen before any result was seen
(doc_qa has only a handful of train lines, so repeating them is a guess,
not a tuned value). The best epoch is picked on MASSIVE dev only. The own
test lines are never used for training or for choosing anything.

Each run is scored on the own test lines twice: raw text (as typed) and
normalised text (lowercase, no punctuation), plus on the MASSIVE test split.

Needs training/own_phrasing_train.txt and own_phrasing_test.txt (made by
training/own_phrasing_split.py) in the working folder, in /kaggle/working or
in training/. Runs on a CUDA GPU (Kaggle) or, slowly, on CPU.
Hyperparameters are starting guesses and were not tuned.
"""

import json
import os
import random
import re
import shutil
import tarfile
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import transformers
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_NAME = os.environ.get("ROUTER_BASE_MODEL", "distilbert-base-uncased")
SEED = 42
EPOCHS = int(os.environ.get("ROUTER_EPOCHS", "4"))
BATCH = 32
LR = 5e-5
MAXLEN = 64
OWN_REPEAT = 10
URL = (
    "https://amazon-massive-nlu-dataset.s3.amazonaws.com/"
    "amazon-massive-dataset-1.1.tar.gz"
)
KAGGLE_DIR = Path("/kaggle/working")
OUT_DIR = KAGGLE_DIR if KAGGLE_DIR.exists() else Path(".")

CLASSES = sorted(
    ["timers_reminders", "lists_notes", "math_time", "music", "doc_qa", "other"]
)
LABEL2ID = {c: i for i, c in enumerate(CLASSES)}
ID2LABEL = dict(enumerate(CLASSES))
ALL_IDS = list(range(len(CLASSES)))
MASSIVE_IDS = [LABEL2ID[c] for c in CLASSES if c != "doc_qa"]

# Mirrors training/intent_mapping.json (keep the two in sync).
INTENT_TO_CLASS = {
    "alarm_set": "timers_reminders",
    "alarm_query": "timers_reminders",
    "alarm_remove": "timers_reminders",
    "lists_createoradd": "lists_notes",
    "lists_query": "lists_notes",
    "lists_remove": "lists_notes",
    "datetime_query": "math_time",
    "qa_maths": "math_time",
    "play_music": "music",
    "audio_volume_up": "music",
    "audio_volume_down": "music",
    "audio_volume_mute": "music",
    "audio_volume_other": "music",
}


def map_row(intent, utt):
    if intent == "calendar_set" and "remind" in utt.lower():
        return "timers_reminders"
    return INTENT_TO_CLASS.get(intent, "other")


def normalise(text):
    """Same function as in training/own_phrasing_split.py (keep in sync)."""
    text = text.lower().replace("\u2019", "'")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_massive():
    found = sorted(OUT_DIR.glob("massive_en/**/en-US.jsonl"))
    if not found:
        tar_path = OUT_DIR / "massive.tar.gz"
        if not tar_path.exists():
            urllib.request.urlretrieve(URL, tar_path)
        extra = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        with tarfile.open(tar_path) as tar:
            member = next(
                m for m in tar.getmembers() if m.name.endswith("en-US.jsonl")
            )
            tar.extract(member, OUT_DIR / "massive_en", **extra)
        found = sorted(OUT_DIR.glob("massive_en/**/en-US.jsonl"))
    df = pd.read_json(found[0], lines=True)
    labels = [
        map_row(i, u) for i, u in zip(df["intent"], df["utt"], strict=True)
    ]
    df["label"] = labels
    return df


def find_file(name):
    for folder in (OUT_DIR, Path("training"), Path(".")):
        if (folder / name).exists():
            return folder / name
    raise SystemExit(f"cannot find {name} (looked in {OUT_DIR}, training/, .)")


def read_own(path):
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        label, sep, text = line.partition("|")
        label, text = label.strip(), text.strip()
        if not sep or label not in LABEL2ID or not text:
            raise SystemExit(f"{path.name} line {n}: bad line: {line!r}")
        rows.append((label, text))
    return rows


def set_seed():
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)


def encode(tok, texts):
    enc = tok(
        texts,
        padding="max_length",
        truncation=True,
        max_length=MAXLEN,
        return_tensors="pt",
    )
    return enc["input_ids"], enc["attention_mask"]


@torch.no_grad()
def get_logits(model, ids, mask, device, use_amp):
    model.eval()
    out = []
    for i in range(0, len(ids), 256):
        with torch.autocast(device.type, dtype=torch.float16, enabled=use_amp):
            logits = model(
                input_ids=ids[i : i + 256].to(device),
                attention_mask=mask[i : i + 256].to(device),
            ).logits
        out.append(logits.float().cpu())
    return torch.cat(out).numpy()


def score(true_ids, pred_ids, labels):
    true_ids, pred_ids = np.asarray(true_ids), np.asarray(pred_ids)
    prec, rec, f1, sup = precision_recall_fscore_support(
        true_ids, pred_ids, labels=labels, zero_division=0
    )
    per_class = {}
    for k, label_id in enumerate(labels):
        correct = int(((true_ids == label_id) & (pred_ids == label_id)).sum())
        per_class[ID2LABEL[label_id]] = {
            "precision": float(prec[k]),
            "recall": float(rec[k]),
            "f1": float(f1[k]),
            "support": int(sup[k]),
            "correct": correct,
        }
    return {
        "accuracy": float(accuracy_score(true_ids, pred_ids)),
        "macro_f1": float(
            f1_score(
                true_ids, pred_ids, labels=labels, average="macro", zero_division=0
            )
        ),
        "n": len(true_ids),
        "n_correct": int((true_ids == pred_ids).sum()),
        "per_class": per_class,
        "confusion": confusion_matrix(true_ids, pred_ids, labels=labels).tolist(),
    }


def train_one(tag, train_texts, train_y, tok, dev_enc, dev_y, device, use_amp):
    set_seed()
    ids, mask = encode(tok, train_texts)
    y = torch.tensor(train_y)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=len(CLASSES), id2label=ID2LABEL, label2id=LABEL2ID
    ).to(device)
    steps_per_epoch = (len(y) + BATCH - 1) // BATCH
    total_steps = EPOCHS * steps_per_epoch
    warmup = max(1, int(0.1 * total_steps))

    def lr_lambda(step):
        if step < warmup:
            return (step + 1) / warmup
        return max(0.0, (total_steps - step) / max(1, total_steps - warmup))

    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)
    scaler = torch.amp.GradScaler(device.type, enabled=use_amp)
    gen = torch.Generator().manual_seed(SEED)
    history = []
    best = {"f1": -1.0, "epoch": 0, "state": None}
    t_start = time.time()
    for ep in range(1, EPOCHS + 1):
        model.train()
        t0 = time.time()
        total_loss = 0.0
        for idx in torch.randperm(len(y), generator=gen).split(BATCH):
            b_ids, b_mask = ids[idx].to(device), mask[idx].to(device)
            b_y = y[idx].to(device)
            opt.zero_grad()
            with torch.autocast(device.type, dtype=torch.float16, enabled=use_amp):
                logits = model(input_ids=b_ids, attention_mask=b_mask).logits
            loss = torch.nn.functional.cross_entropy(logits.float(), b_y)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            total_loss += loss.item() * len(b_y)
        dev_pred = get_logits(model, *dev_enc, device, use_amp).argmax(-1)
        dev = score(dev_y, dev_pred, MASSIVE_IDS)
        row = {
            "epoch": ep,
            "train_loss": total_loss / len(y),
            "dev_acc": dev["accuracy"],
            "dev_macro_f1": dev["macro_f1"],
            "epoch_seconds": round(time.time() - t0, 1),
        }
        history.append(row)
        print(tag, row)
        if row["dev_macro_f1"] > best["f1"]:
            state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            best = {"f1": row["dev_macro_f1"], "epoch": ep, "state": state}
    seconds = round(time.time() - t_start, 1)
    model.load_state_dict(best["state"])
    print(tag, "trained in", seconds, "s | best epoch by MASSIVE dev macro-F1:",
          best["epoch"])
    return model, history, best["epoch"], seconds


def print_own(tag, variant, res):
    head = f"{res['n_correct']} of {res['n']}"
    print(f"\n[{tag}] own test, {variant} text: accuracy {res['accuracy']:.4f}"
          f" ({head}), macro-F1 {res['macro_f1']:.4f}")
    print(f"  {'class':18}{'correct':>9}{'prec':>7}{'recall':>8}{'F1':>7}")
    for name, m in res["per_class"].items():
        print(f"  {name:18}{m['correct']:>4} of {m['support']:<3}"
              f"{m['precision']:>7.3f}{m['recall']:>8.3f}{m['f1']:>7.3f}")
    print("  confusion (rows = true, cols = predicted), order:", CLASSES)
    for name, row in zip(CLASSES, res["confusion"], strict=True):
        print(f"  {name:18}{row}")


def main():
    use_amp = torch.cuda.is_available()
    device = torch.device("cuda:0" if use_amp else "cpu")
    print("device:", device, "| torch", torch.__version__,
          "| transformers", transformers.__version__)

    massive = load_massive()
    own_train = read_own(find_file("own_phrasing_train.txt"))
    own_test = read_own(find_file("own_phrasing_test.txt"))
    print("MASSIVE rows:", len(massive), "| own train:", len(own_train),
          "| own test:", len(own_test))
    print("own train per class:", dict(sorted(pd.Series([c for c, _ in own_train])
                                              .value_counts().items())))
    print("own test per class: ", dict(sorted(pd.Series([c for c, _ in own_test])
                                              .value_counts().items())))
    train_keys = {normalise(t) for _, t in own_train}
    overlap = [t for _, t in own_test if normalise(t) in train_keys]
    print("own test lines that also appear in own train (normalised):", len(overlap))

    tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    all_text = massive["utt"].tolist() + [t for _, t in own_train + own_test]
    longest = max(len(x) for x in tok(all_text)["input_ids"])
    print("longest input in tokens:", longest, "| MAXLEN:", MAXLEN)

    m_train = massive[massive.partition == "train"]
    m_dev = massive[massive.partition == "dev"]
    m_test = massive[massive.partition == "test"]
    m_train_texts = m_train["utt"].tolist()
    m_train_y = [LABEL2ID[x] for x in m_train["label"]]
    dev_enc = encode(tok, m_dev["utt"].tolist())
    dev_y = [LABEL2ID[x] for x in m_dev["label"]]
    test_enc = encode(tok, m_test["utt"].tolist())
    test_y = [LABEL2ID[x] for x in m_test["label"]]

    own_tr_texts = [normalise(t) for _, t in own_train]
    own_tr_y = [LABEL2ID[c] for c, _ in own_train]
    own_true = [LABEL2ID[c] for c, _ in own_test]
    own_variants = {
        "raw": [t for _, t in own_test],
        "normalised": [normalise(t) for _, t in own_test],
    }

    plan = [
        ("A_massive_only", 0),
        (f"B_massive_plus_own_x{OWN_REPEAT}", OWN_REPEAT),
        ("C_massive_plus_own_x1", 1),
    ]
    results = {
        "config": {
            "model": MODEL_NAME, "seed": SEED, "epochs": EPOCHS, "batch": BATCH,
            "lr": LR, "maxlen": MAXLEN, "own_repeat_primary": OWN_REPEAT,
            "classes": CLASSES, "torch": torch.__version__,
            "transformers": transformers.__version__,
        },
        "runs": {},
    }
    pred_rows = []
    for tag, repeat in plan:
        texts = m_train_texts + own_tr_texts * repeat
        ys = m_train_y + own_tr_y * repeat
        print(f"\n=== {tag}: {len(texts)} training rows ===")
        model, history, best_epoch, seconds = train_one(
            tag, texts, ys, tok, dev_enc, dev_y, device, use_amp
        )
        massive_logits = get_logits(model, *test_enc, device, use_amp)
        massive_pred = massive_logits.argmax(-1)
        massive_res = score(test_y, massive_pred, MASSIVE_IDS)
        n_doc = int((massive_pred == LABEL2ID["doc_qa"]).sum())
        print(f"[{tag}] MASSIVE test: accuracy {massive_res['accuracy']:.4f},"
              f" macro-F1 (5 classes) {massive_res['macro_f1']:.4f},"
              f" rows predicted doc_qa: {n_doc}")
        run = {
            "train_rows": len(texts), "best_epoch": best_epoch,
            "train_seconds": seconds, "history": history,
            "massive_test": massive_res, "massive_test_pred_doc_qa": n_doc,
            "own_test": {},
        }
        for variant, texts_v in own_variants.items():
            logits = get_logits(model, *encode(tok, texts_v), device, use_amp)
            pred = logits.argmax(-1)
            conf = torch.softmax(torch.tensor(logits), dim=1).max(1).values.numpy()
            res = score(own_true, pred, ALL_IDS)
            run["own_test"][variant] = res
            print_own(tag, variant, res)
            for text, t_id, p_id, c in zip(texts_v, own_true, pred, conf, strict=True):
                pred_rows.append({
                    "run": tag, "text_variant": variant, "text": text,
                    "true": ID2LABEL[t_id], "pred": ID2LABEL[int(p_id)],
                    "confidence": round(float(c), 3),
                })
        results["runs"][tag] = run
        if repeat == OWN_REPEAT:
            model_dir = OUT_DIR / "router_v2_primary"
            model.save_pretrained(model_dir)
            tok.save_pretrained(model_dir)
            shutil.make_archive(str(model_dir), "zip", model_dir)
            zip_mb = os.path.getsize(str(model_dir) + ".zip") / 1e6
            print("saved primary model zip (MB):", round(zip_mb, 1))
        del model
        if use_amp:
            torch.cuda.empty_cache()

    with open(OUT_DIR / "finetune_v2_results.json", "w") as f:
        json.dump(results, f, indent=2)
    pd.DataFrame(pred_rows).to_csv(
        OUT_DIR / "finetune_v2_own_test_predictions.csv", index=False
    )

    print(f"\n=== SUMMARY (own test = {len(own_test)} held-out lines) ===")
    print(f"{'run':28}{'text':12}{'own acc':>16}{'own macroF1':>13}"
          f"{'doc_qa':>9}{'MASSIVE acc':>13}")
    for tag, run in results["runs"].items():
        for variant in own_variants:
            o = run["own_test"][variant]
            d = o["per_class"]["doc_qa"]
            print(f"{tag:28}{variant:12}"
                  f"{o['accuracy']:>9.4f} ({o['n_correct']:>2}/{o['n']})"
                  f"{o['macro_f1']:>13.4f}{d['correct']:>4}/{d['support']:<4}"
                  f"{run['massive_test']['accuracy']:>9.4f}")
    print("saved: finetune_v2_results.json, finetune_v2_own_test_predictions.csv")


if __name__ == "__main__":
    main()