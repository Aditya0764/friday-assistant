"""RAG mini eval (P4-10): 20 questions over the 3 documents in evals/docs.

Runs two chunk settings on a throwaway database each time (your real friday.db is untouched):
  production: 500-word chunks, 50 overlap (the brief's setting)
  stress:     40-word chunks, 8 overlap (many chunks, so retrieval has to pick the right ones)

Per setting it reports:
  retrieval hit: for questions in a document, did the top-4 chunks include one from the
                 right document that contains the expected answer text?
  answer correct: the reply is grounded and contains the expected text (in-document questions),
                  or the reply is the refusal (questions not in any document).
The match is plain text matching, so READ every answer in the results file before trusting it.

Run: set PYTHONPATH=.  then  python evals\\run_rag_eval.py
Writes evals/results/rag_eval_results.md and .json
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from datetime import date
from pathlib import Path

import yaml

from friday import db
from friday.rag import answer, store
from friday.rag.ingest import load_text

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
QUESTIONS = ROOT / "rag_eval.yaml"
OUT = ROOT / "results"

K = 4
SETTINGS = [("production", 500, 50), ("stress", 40, 8)]


def mentions(text: str, needles: list[str]) -> bool:
    """True if any needle appears in the text as a whole word (case-insensitive)."""
    low = text.lower()
    return any(re.search(rf"\b{re.escape(n.lower())}\b", low) for n in needles)


def run_setting(label: str, size: int, overlap: int, questions: list[dict]) -> dict:
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        conn = db.connect(Path(tmp) / "eval.db")
        try:
            for path in sorted(DOCS.iterdir()):
                if path.suffix.lower() in {".pdf", ".txt"}:
                    store.add_document(conn, path.name, load_text(path), size=size, overlap=overlap)
            chunks = {d["name"]: d["chunk_count"] for d in store.list_documents(conn)}
            total = sum(chunks.values())
            print(f"\n[{label}] size={size} overlap={overlap} chunks={chunks} (total {total})")

            for q in questions:
                hits = store.search(conn, q["question"], k=K)
                hit = None
                if q["in_doc"]:
                    hit = any(
                        h["doc_name"] == q["doc"] and mentions(h["text"], q["answer_any"])
                        for h in hits
                    )
                start = time.perf_counter()
                error = ""
                try:
                    result = answer.answer_question(conn, q["question"], k=K)
                    reply, grounded = result.text, result.grounded
                except Exception as exc:  # noqa: BLE001 - keep going; an error counts as incorrect
                    reply, grounded, error = "", False, str(exc)[:200]
                ms = round((time.perf_counter() - start) * 1000)
                if error:
                    correct = False
                elif q["in_doc"]:
                    correct = grounded and mentions(reply, q["answer_any"])
                else:
                    correct = not grounded
                rows.append(
                    {
                        "id": q["id"],
                        "question": q["question"],
                        "in_doc": q["in_doc"],
                        "retrieval_hit": hit,
                        "grounded": grounded,
                        "correct": correct,
                        "reply": reply or f"ERROR: {error}",
                        "ms": ms,
                    }
                )
                print(f"  Q{q['id']:>2} hit={hit} grounded={grounded} correct={correct}")
        finally:
            conn.close()

    in_rows = [r for r in rows if r["in_doc"]]
    out_rows = [r for r in rows if not r["in_doc"]]
    return {
        "setting": label,
        "chunk_words": size,
        "overlap_words": overlap,
        "chunks_per_doc": chunks,
        "retrieval_hits": sum(1 for r in in_rows if r["retrieval_hit"]),
        "in_doc_total": len(in_rows),
        "in_doc_correct": sum(1 for r in in_rows if r["correct"]),
        "refusals_correct": sum(1 for r in out_rows if r["correct"]),
        "out_doc_total": len(out_rows),
        "all_correct": sum(1 for r in rows if r["correct"]),
        "total": len(rows),
        "rows": rows,
    }


def write_reports(results: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "rag_eval_results.json").write_text(
        json.dumps({"date": str(date.today()), "k": K, "results": results}, indent=2),
        encoding="utf-8",
    )
    lines = [
        f"# RAG mini eval results ({date.today()})",
        "",
        "Embeddings: all-MiniLM-L6-v2. LLM: Groq (Gemini fallback). Top-4 chunks.",
        "Scoring is automatic text matching. The tables below show every answer so it can be read.",
        "",
        "## Summary",
        "",
        (
            "| Setting | Chunk words | Retrieval hit (in-doc) | Answer correct (in-doc) "
            "| Refusal correct (not in doc) | All correct |"
        ),
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['setting']} | {r['chunk_words']} | {r['retrieval_hits']}/{r['in_doc_total']} "
            f"| {r['in_doc_correct']}/{r['in_doc_total']} "
            f"| {r['refusals_correct']}/{r['out_doc_total']} | {r['all_correct']}/{r['total']} |"
        )
    for r in results:
        lines += [
            "",
            f"## Every answer: {r['setting']} (chunks per document: {r['chunks_per_doc']})",
            "",
            "| Q | Question | Retrieval hit | Grounded | Correct (auto) | Reply |",
            "|---|---|---|---|---|---|",
        ]
        for row in r["rows"]:
            hit = "n/a" if row["retrieval_hit"] is None else str(row["retrieval_hit"])
            reply = row["reply"].replace("|", "/").replace("\n", " ")
            lines.append(
                f"| {row['id']} | {row['question']} | {hit} | {row['grounded']} "
                f"| {row['correct']} | {reply} |"
            )
    (OUT / "rag_eval_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    results = [run_setting(label, size, overlap, questions) for label, size, overlap in SETTINGS]
    write_reports(results)
    print("\nSummary")
    for r in results:
        print(
            f"  {r['setting']}: retrieval {r['retrieval_hits']}/{r['in_doc_total']}, "
            f"answers {r['in_doc_correct']}/{r['in_doc_total']}, "
            f"refusals {r['refusals_correct']}/{r['out_doc_total']}, "
            f"all {r['all_correct']}/{r['total']}"
        )
    print(f"\nWrote {OUT / 'rag_eval_results.md'}")


if __name__ == "__main__":
    main()