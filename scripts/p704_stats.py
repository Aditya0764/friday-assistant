"""P7-04 router stats: read existing eval result JSON files, write docs/p704_stats.md.

Read-only on the inputs. No network, no models, no LLM. Refuses to overwrite the output.
Run: python scripts/p704_stats.py
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INPUTS = [
    ("eval_100_final_live.json", "development set"),
    ("eval_100_final_live_model.json", "development set"),
    ("eval_100_heldout2_off2.json", "typed held-out, clean"),
    ("eval_100_heldout2_on.json", "typed held-out, clean"),
    ("eval_100_spoken2_off.json", "spoken, one speaker, read from a screen"),
    ("eval_100_spoken2_on.json", "spoken, one speaker, read from a screen"),
]

CATEGORIES = [
    ("A", "A. rule action (via=rule, routed skill is not catch)"),
    ("DOCS", "docs skill, LLM inside the skill (via=rule, routed=docs, llm_calls > 0)"),
    ("B", "B. model + slots (via=model, a real skill answered)"),
    ("C1", "C1. say it again, rule-catch (via=rule, routed=catch)"),
    ("C2", "C2. say it again, model-then-catch (via=model, routed=catch)"),
    ("D", "D. plain chat LLM (via=llm)"),
    ("U", "unclassified (trace could not be parsed)"),
]

DEFINITIONS = """\
Every turn ends in exactly one category. The categories were fixed before any number was
seen (18 Oct 2026). Checked in this order:

1. via=llm: D, plain chat LLM.
2. routed skill is catch: C, "say it again". C1 if via=rule, C2 if via=model.
3. via=rule, routed=docs, and the row has LLM calls: its own row, "docs skill, LLM inside the
   skill". Not folded into A.
4. via=rule: A, rule action.
5. via=model and a real skill answered: B, model + slots (one slot-LLM call expected; the
   actual count of `llm_calls` is printed, not assumed).
6. Anything else: unclassified. Any unclassified row makes the run fail and no file is written.

Field notes: the JSON has no `via` field. `via` is the prefix of `router_trace` (rule / model /
llm). The model class is the `[model <class> <conf>]` tag in `router_trace`; it is only there when
the router model was consulted. `passed` is the stored `status == "pass"`; nothing is re-scored.
"""

TRACE_RE = re.compile(r"^(rule|model|llm): (\S+)")
MODEL_RE = re.compile(r"\[model (\w+) ([\d.]+)\]")


class StatsError(Exception):
    pass


def parse_trace(trace):
    m = TRACE_RE.match(trace or "")
    via = m.group(1) if m else None
    mm = MODEL_RE.search(trace or "")
    return via, (mm.group(1) if mm else None)


def classify(row):
    via, _ = parse_trace(row.get("router_trace"))
    routed = row.get("routed")
    calls = len(row.get("llm_calls") or [])
    if via == "llm":
        return "D"
    if via is None:
        return "U"
    if routed == "catch":
        return "C1" if via == "rule" else "C2"
    if via == "rule":
        return "DOCS" if routed == "docs" and calls > 0 else "A"
    if via == "model" and routed not in ("llm", None):
        return "B"
    return "U"


def frac(c, n):
    return f"{c}/{n} = {100 * c / n:.1f}%"


def file_section(name, label, rows):
    n = len(rows)
    cat = {k: [] for k, _ in CATEGORIES}
    for r in rows:
        cat[classify(r)].append(r)
    if cat["U"] or sum(len(v) for v in cat.values()) != n or n == 0:
        raise StatsError(f"{name}: totals check failed (n={n}, unclassified={len(cat['U'])})")

    def passed(rs):
        return sum(1 for r in rs if r.get("status") == "pass")

    out = [f"## {name}", "", f"Input: {label}. n rows = {n}.", ""]
    out += ["| category | rows | share | passed |", "|---|---|---|---|"]
    for k, text in CATEGORIES:
        if k == "U":
            continue
        rs = cat[k]
        out.append(f"| {text} | {len(rs)} | {frac(len(rs), n)} | {passed(rs)}/{len(rs)} |")
    out.append("")
    other = Counter(r.get("status") for r in rows if r.get("status") not in ("pass", "fail"))
    if other:
        out.append(f"Rows with a status other than pass/fail (not counted as passed): {dict(other)}")
        out.append("")
    c_all = len(cat["C1"]) + len(cat["C2"])
    abc = len(cat["A"]) + len(cat["B"]) + c_all
    abc_rows = cat["A"] + cat["B"] + cat["C1"] + cat["C2"]
    out.append(
        f"- Rows that did not reach the chat LLM = A + B + C = {frac(abc, n)} "
        f"(passed {passed(abc_rows)}/{abc}). This is not the same as correct actions."
    )
    docs = len(cat["DOCS"])
    out.append(
        f"- The docs-skill row ({docs}) is not in A + B + C. "
        f"A + B + C + docs-skill = {frac(abc + docs, n)}."
    )
    zero = sum(1 for r in rows if len(r.get("llm_calls") or []) == 0)
    out.append(f"- Turns with no LLM call of any kind (len(llm_calls) == 0): {frac(zero, n)}.")
    for k in ("B", "C2"):
        dist = Counter(len(r.get("llm_calls") or []) for r in cat[k])
        out.append(f"- {k} rows by number of LLM calls: {dict(sorted(dist.items())) or 'no rows'}.")
    out.append("")

    tagged = [(parse_trace(r.get("router_trace"))[1], r) for r in rows]
    tagged = [(cls, r) for cls, r in tagged if cls]
    if not tagged:
        out.append("Model class vs expected skill: no model class recorded in this file, skipped.")
    else:
        out.append(
            f"Model class vs expected skill (raw counts), router model consulted on "
            f"{frac(len(tagged), n)} rows:"
        )
        out.append("")
        skills = sorted({r.get("expected_skill") for _, r in tagged})
        counts = Counter((cls, r.get("expected_skill")) for cls, r in tagged)
        out.append("| model class | " + " | ".join(skills) + " | total |")
        out.append("|---|" + "---|" * (len(skills) + 1))
        for cls in sorted({c for c, _ in tagged}):
            cells = [str(counts[(cls, s)]) for s in skills]
            total = sum(counts[(cls, s)] for s in skills)
            out.append(f"| {cls} | " + " | ".join(cells) + f" | {total} |")
    out.append("")
    return out


def build_report(results_dir):
    lines = [
        "# P7-04 router stats",
        "",
        (
            "Generated by scripts/p704_stats.py from existing eval result JSON files. Counts are "
            "printed next to every percentage. No claims beyond the data."
        ),
        "",
        "## Category definitions",
        "",
        DEFINITIONS,
    ]
    for name, label in INPUTS:
        path = Path(results_dir) / name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data["rows"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise StatsError(f"{name}: cannot read rows ({exc})") from exc
        lines += file_section(name, label, rows)
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-dir", default=str(ROOT / "evals" / "results"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "p704_stats.md"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print(f"refusing to overwrite {out}", file=sys.stderr)
        return 1
    try:
        report = build_report(args.results_dir)
    except StatsError as exc:
        print(f"error: {exc}; nothing written", file=sys.stderr)
        return 1
    try:
        with open(out, "x", encoding="utf-8") as fh:
            fh.write(report)
    except FileExistsError:
        print(f"refusing to overwrite {out}", file=sys.stderr)
        return 1
    print(report)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
