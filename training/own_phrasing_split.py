"""T-06: split the own-phrasing commands into a train half and a test half.

Reads training/own_phrasing.txt (one `label|text` per line, `#` = comment).
Each line goes to train or test from a hash of its normalised text, so adding
new lines later never moves an existing line to the other half. The salt is
fixed: do not change it after looking at results.

Writes training/own_phrasing_train.txt and training/own_phrasing_test.txt.
Run from the repo root: python training/own_phrasing_split.py
"""

import hashlib
import re
from collections import Counter
from pathlib import Path

SRC = Path("training/own_phrasing.txt")
TRAIN = Path("training/own_phrasing_train.txt")
TEST = Path("training/own_phrasing_test.txt")
SALT = "friday-t06"
TEST_PERCENT = 50
CLASSES = [
    "timers_reminders",
    "lists_notes",
    "math_time",
    "music",
    "doc_qa",
    "other",
]


def normalise(text):
    """Lowercase and drop punctuation (keep apostrophes and digits).

    MASSIVE has no sentence punctuation; Whisper adds it. Use this one
    function on MASSIVE, on this set and on real input.
    """
    text = text.lower().replace("\u2019", "'")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def bucket(text):
    digest = hashlib.sha256((SALT + normalise(text)).encode()).hexdigest()
    return int(digest, 16) % 100


def load():
    rows, seen = [], set()
    for n, line in enumerate(SRC.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        label, sep, text = line.partition("|")
        label, text = label.strip(), text.strip()
        if not sep or label not in CLASSES or not text:
            raise SystemExit(f"line {n}: bad format or label: {line!r}")
        key = normalise(text)
        if key in seen:
            raise SystemExit(f"line {n}: duplicate command: {text!r}")
        seen.add(key)
        rows.append((label, text))
    return rows


def main():
    rows = load()
    train = [r for r in rows if bucket(r[1]) >= TEST_PERCENT]
    test = [r for r in rows if bucket(r[1]) < TEST_PERCENT]
    for path, part in ((TRAIN, train), (TEST, test)):
        body = "\n".join(f"{label}|{text}" for label, text in part)
        path.write_text(body + "\n", encoding="utf-8")
    print("total commands:", len(rows))
    tr, te = Counter(r[0] for r in train), Counter(r[0] for r in test)
    print(f"{'class':18}{'train':>6}{'test':>6}")
    for c in CLASSES:
        print(f"{c:18}{tr[c]:>6}{te[c]:>6}")
    print(f"{'ALL':18}{len(train):>6}{len(test):>6}")
    thin = [c for c in CLASSES if min(tr[c], te[c]) < 6]
    if thin:
        print("WARNING: fewer than 6 lines in one half for:", ", ".join(thin))


if __name__ == "__main__":
    main()