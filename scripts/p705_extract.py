"""P7-05: copy the router training tables from training/*.md into dashboard/public/results/.

Parses markdown tables only; invents and recomputes nothing. Fails loudly (exit 1, nothing written)
if a table is missing or changed shape. Run: python scripts/p705_extract.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRAINING = ROOT / "training"
OUT = ROOT / "dashboard" / "public" / "results" / "router_results.json"

CURVE_HEAD = ["epoch", "train loss", "dev acc", "dev macro-F1", "seconds"]
RUNS_HEAD = ["Run", "Own accuracy", "Own macro-F1", "doc_qa", "MASSIVE test acc (5 classes)"]
CLASS_HEAD = ["Class", "Correct", "Precision", "Recall", "F1"]


class ExtractError(Exception):
    pass


def table_after(text, heading, header, name):
    """Rows (lists of cells) of the first markdown table under the heading line starting with `heading`."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith(heading)), None)
    if start is None:
        raise ExtractError(f"{name}: heading not found: {heading!r}")
    block = []
    for ln in lines[start + 1:]:
        if ln.startswith("|"):
            block.append(ln)
        elif block:
            break
    if len(block) < 3:
        raise ExtractError(f"{name}: no table under {heading!r}")
    rows = [[c.strip().replace("**", "") for c in ln.strip().strip("|").split("|")] for ln in block]
    if header is not None and rows[0] != header:
        raise ExtractError(f"{name}: header changed under {heading!r}: {rows[0]} != {header}")
    width = len(rows[0])
    if any(len(r) != width for r in rows):
        raise ExtractError(f"{name}: ragged table under {heading!r}")
    return rows[0], rows[2:]  # rows[1] is the |---| separator


def number(cell, kind, name):
    try:
        return kind(cell)
    except ValueError as exc:
        raise ExtractError(f"{name}: not a number: {cell!r}") from exc


def search(pattern, text, name):
    m = re.search(pattern, text)
    if not m:
        raise ExtractError(f"{name}: pattern not found: {pattern}")
    return m


def router5(finetune, report):
    name = "finetune_results.md"
    _, rows = table_after(finetune, "## Training curve (dev)", CURVE_HEAD, name)
    if len(rows) != 4:
        raise ExtractError(f"{name}: expected 4 epochs, found {len(rows)}")
    curve = [
        {
            "epoch": number(r[0], int, name),
            "train_loss": number(r[1], float, name),
            "dev_acc": number(r[2], float, name),
            "dev_macro_f1": number(r[3], float, name),
            "seconds": number(r[4], float, name),
        }
        for r in rows
    ]
    best = search(r"best epoch (\d+)", finetune, name)
    acc = search(r"Accuracy ([\d.]+), macro-F1 ([\d.]+)", finetune, name)

    name = "eval_report.md"
    head, rows = table_after(report, "## Confusion matrix (test", None, name)
    classes = head[1:]
    if len(classes) != 5 or len(rows) != 5 or [r[0] for r in rows] != classes:
        raise ExtractError(f"{name}: confusion matrix is not 5x5 with matching row/column labels")
    confusion = [[number(c, int, name) for c in r[1:]] for r in rows]
    test_rows = search(r"of (\d+) test rows", report, name)
    return {
        "model": "models/router_distilbert",
        "classes": classes,
        "curve": curve,
        "best_epoch": int(best.group(1)),
        "test_accuracy": float(acc.group(1)),
        "test_macro_f1": float(acc.group(2)),
        "confusion": confusion,
        "confusion_total": sum(sum(r) for r in confusion),
        "test_rows_stated": int(test_rows.group(1)),
    }


def count(cell, pattern, name):
    m = re.search(pattern, cell)
    if not m:
        raise ExtractError(f"{name}: no count in {cell!r}")
    return int(m.group(1)), int(m.group(2))


def router6(own):
    name = "own_phrasing_results.md"
    _, rows = table_after(own, "## Results (90 held-out", RUNS_HEAD, name)
    if len(rows) != 3:
        raise ExtractError(f"{name}: expected runs A, B, C, found {len(rows)}")
    runs = []
    for r in rows:
        correct, total = count(r[1], r"\((\d+)/(\d+)\)", name)
        doc_ok, doc_n = count(r[3], r"(\d+)/(\d+)", name)
        runs.append(
            {
                "run": r[0],
                "own_accuracy": number(r[1].split()[0], float, name),
                "correct": correct,
                "total": total,
                "own_macro_f1": number(r[2], float, name),
                "doc_qa_correct": doc_ok,
                "doc_qa_total": doc_n,
                "massive_test_acc": number(r[4], float, name),
            }
        )
    if [r["run"][0] for r in runs] != ["A", "B", "C"]:
        raise ExtractError(f"{name}: runs are not A, B, C")
    _, rows = table_after(own, "## Run B per class", CLASS_HEAD, name)
    if len(rows) != 6:
        raise ExtractError(f"{name}: expected 6 classes in run B, found {len(rows)}")
    per_class = []
    for r in rows:
        ok, n = count(r[1], r"(\d+) of (\d+)", name)
        per_class.append(
            {
                "class": r[0],
                "correct": ok,
                "support": n,
                "precision": number(r[2], float, name),
                "recall": number(r[3], float, name),
                "f1": number(r[4], float, name),
            }
        )
    if sum(c["support"] for c in per_class) != runs[1]["total"]:
        raise ExtractError(f"{name}: run B per-class support does not add up to {runs[1]['total']}")
    return {"model": "models/router_v2", "deployed_run": "B", "runs": runs, "run_b_per_class": per_class}


def extract(finetune, report, own):
    return {
        "generated_by": "scripts/p705_extract.py",
        "sources": [
            "training/finetune_results.md",
            "training/eval_report.md",
            "training/own_phrasing_results.md",
        ],
        "router5": router5(finetune, report),
        "router6": router6(own),
    }


def main():
    try:
        texts = [
            (TRAINING / f).read_text(encoding="utf-8")
            for f in ("finetune_results.md", "eval_report.md", "own_phrasing_results.md")
        ]
        data = extract(*texts)
    except (OSError, ExtractError) as exc:
        print(f"error: {exc}; nothing written", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
