"""T-04: fine-tune DistilBERT as Friday's intent router on MASSIVE en-US.

Runs in a Kaggle GPU notebook (paste the whole file into one cell) or on any
machine with a CUDA GPU. It downloads MASSIVE 1.1 en-US, maps the 60 intents
to Friday's classes (same mapping as training/intent_mapping.json), fine-tunes
distilbert-base-uncased with a plain PyTorch loop, picks the epoch by dev
macro-F1, scores the test split once, and writes its outputs to OUT_DIR.

Hyperparameters are starting guesses and were not tuned.
"""

import json
import os
import random
import shutil
import tarfile
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import transformers
from sklearn.metrics import accuracy_score, classification_report, f1_score
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_NAME = "distilbert-base-uncased"
SEED = 42
EPOCHS = 4
BATCH = 32
LR = 5e-5
MAXLEN = 64
URL = (
    "https://amazon-massive-nlu-dataset.s3.amazonaws.com/"
    "amazon-massive-dataset-1.1.tar.gz"
)
KAGGLE_DIR = Path("/kaggle/working")
OUT_DIR = KAGGLE_DIR if KAGGLE_DIR.exists() else Path(".")

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


def load_massive():
    tar_path = OUT_DIR / "massive.tar.gz"
    if not tar_path.exists():
        urllib.request.urlretrieve(URL, tar_path)
    extra = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
    with tarfile.open(tar_path) as tar:
        members = tar.getmembers()
        member = next(m for m in members if m.name.endswith("en-US.jsonl"))
        tar.extract(member, OUT_DIR / "massive_en", **extra)
    df = pd.read_json(OUT_DIR / "massive_en" / member.name, lines=True)
    df["label"] = [map_row(i, u) for i, u in zip(df["intent"], df["utt"])]
    return df


def encode(df, tok, part, label2id):
    d = df[df.partition == part]
    enc = tok(
        d["utt"].tolist(),
        padding="max_length",
        truncation=True,
        max_length=MAXLEN,
        return_tensors="pt",
    )
    y = torch.tensor([label2id[lab] for lab in d["label"]])
    return d, enc["input_ids"], enc["attention_mask"], y


@torch.no_grad()
def get_logits(model, ids, mask, device):
    model.eval()
    out = []
    for i in range(0, len(ids), 256):
        with torch.autocast("cuda", dtype=torch.float16):
            logits = model(
                input_ids=ids[i : i + 256].to(device),
                attention_mask=mask[i : i + 256].to(device),
            ).logits
        out.append(logits.float().cpu())
    return torch.cat(out).numpy()


def main():
    assert torch.cuda.is_available(), "needs a CUDA GPU"
    device = torch.device("cuda:0")
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)

    df = load_massive()
    classes = sorted(df["label"].unique())
    label2id = {c: i for i, c in enumerate(classes)}
    id2label = {i: c for c, i in label2id.items()}
    print(df.shape, len(classes), "classes")
    print(df.groupby("partition")["label"].value_counts().unstack())

    tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    lens = [len(x) for x in tok(df["utt"].tolist())["input_ids"]]
    print("token length: max", max(lens), "| longer than MAXLEN:",
          sum(n > MAXLEN for n in lens))

    _, tr_ids, tr_mask, tr_y = encode(df, tok, "train", label2id)
    _, dv_ids, dv_mask, dv_y = encode(df, tok, "dev", label2id)
    te_d, te_ids, te_mask, te_y = encode(df, tok, "test", label2id)

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=len(classes), id2label=id2label, label2id=label2id
    ).to(device)

    steps_per_epoch = (len(tr_y) + BATCH - 1) // BATCH
    total_steps = EPOCHS * steps_per_epoch
    warmup = int(0.1 * total_steps)

    def lr_lambda(step):
        if step < warmup:
            return (step + 1) / warmup
        return max(0.0, (total_steps - step) / (total_steps - warmup))

    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)
    scaler = torch.amp.GradScaler("cuda")
    gen = torch.Generator().manual_seed(SEED)

    history = []
    best = {"f1": -1.0, "epoch": 0, "state": None}
    t_start = time.time()
    for ep in range(1, EPOCHS + 1):
        model.train()
        t0 = time.time()
        total_loss = 0.0
        for idx in torch.randperm(len(tr_y), generator=gen).split(BATCH):
            ids = tr_ids[idx].to(device)
            mask = tr_mask[idx].to(device)
            y = tr_y[idx].to(device)
            opt.zero_grad()
            with torch.autocast("cuda", dtype=torch.float16):
                logits = model(input_ids=ids, attention_mask=mask).logits
            loss = torch.nn.functional.cross_entropy(logits.float(), y)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            total_loss += loss.item() * len(y)
        dv_pred = get_logits(model, dv_ids, dv_mask, device).argmax(-1)
        row = {
            "epoch": ep,
            "train_loss": total_loss / len(tr_y),
            "dev_acc": accuracy_score(dv_y.numpy(), dv_pred),
            "dev_macro_f1": f1_score(dv_y.numpy(), dv_pred, average="macro"),
            "epoch_seconds": round(time.time() - t0, 1),
        }
        history.append(row)
        print(row)
        if row["dev_macro_f1"] > best["f1"]:
            state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            best = {"f1": row["dev_macro_f1"], "epoch": ep, "state": state}
    train_seconds = round(time.time() - t_start, 1)
    print("total training seconds:", train_seconds,
          "| best epoch by dev macro-F1:", best["epoch"])

    # Test is scored once, with the best-dev checkpoint.
    model.load_state_dict(best["state"])
    dv_logits = get_logits(model, dv_ids, dv_mask, device)
    te_logits = get_logits(model, te_ids, te_mask, device)
    te_pred = te_logits.argmax(-1)
    te_acc = accuracy_score(te_y.numpy(), te_pred)
    te_f1 = f1_score(te_y.numpy(), te_pred, average="macro")
    print("\nTEST accuracy:", round(te_acc, 4), "| TEST macro-F1:", round(te_f1, 4))
    print("(TF-IDF baseline was 0.9519 / 0.9066)")
    print(classification_report(te_y.numpy(), te_pred, target_names=classes, digits=3))

    model_dir = OUT_DIR / "router_distilbert"
    model.save_pretrained(model_dir)
    tok.save_pretrained(model_dir)
    with open(OUT_DIR / "training_history.json", "w") as f:
        json.dump(history, f, indent=2)
    results = {
        "model": MODEL_NAME,
        "seed": SEED,
        "epochs": EPOCHS,
        "batch": BATCH,
        "lr": LR,
        "maxlen": MAXLEN,
        "best_epoch": best["epoch"],
        "train_seconds": train_seconds,
        "test_accuracy": float(te_acc),
        "test_macro_f1": float(te_f1),
        "classes": classes,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
    }
    with open(OUT_DIR / "finetune_results.json", "w") as f:
        json.dump(results, f, indent=2)
    np.save(OUT_DIR / "dev_logits.npy", dv_logits)
    np.save(OUT_DIR / "test_logits.npy", te_logits)
    pred_labels = [id2label[i] for i in te_pred]
    te_d.assign(pred=pred_labels).to_csv(OUT_DIR / "test_predictions.csv", index=False)
    shutil.make_archive(str(model_dir), "zip", model_dir)
    zip_mb = os.path.getsize(str(model_dir) + ".zip") / 1e6
    print("saved to", OUT_DIR.resolve(), "| zip size (MB):", round(zip_mb, 1))


if __name__ == "__main__":
    main()