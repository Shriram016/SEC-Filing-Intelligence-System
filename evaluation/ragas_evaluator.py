"""
evaluation/ragas_evaluator.py

Component 16 — RAG Evaluation (custom, Groq-based)

Runs 10 predefined queries through the full pipeline and computes 4 metrics:

  1. Faithfulness      — does the answer stay within retrieved context?  (0-1)
  2. Answer Relevance  — does the answer address the question?           (0-1)
  3. Context Precision — what fraction of retrieved chunks are relevant? (0-1)
  4. Context Recall    — does retrieved context cover the ground truth?  (0-1)

All metrics use Groq LLM-as-judge at temperature=0.
Faithfulness reuses the same rubric as scoring/scorer.py.

Input:
    evaluation/eval_queries.json — 10 predefined queries with ground truths

Output:
    evaluation/eval_results.json — per-query scores + aggregate averages
    Printed summary table to stdout

Run from project root:
    python evaluation/ragas_evaluator.py
"""

from __future__ import annotations

import os
import sys
import re
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from config import GROQ_MODEL
from retrieval.retriever import Retriever
from synthesis.synthesizer import Synthesizer
from scoring.scorer import Scorer, REFUSAL_STRING

EVAL_QUERIES_PATH = "evaluation/eval_queries.json"
EVAL_RESULTS_PATH = "evaluation/eval_results.json"

# Seconds between successive Groq judge calls within one query to stay within
# the free-tier rate limit (~30 req/min on llama-3.1-8b-instant).
INTER_JUDGE_DELAY = 5


# ---------------------------------------------------------------------------
# Groq client (shared singleton)
# ---------------------------------------------------------------------------

_client: Groq | None = None


def get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in .env")
        _client = Groq(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# LLM judge helpers
# ---------------------------------------------------------------------------

def _call_judge(system: str, user: str, max_tokens: int = 20) -> str:
    """Single Groq call for a judge prompt. Returns raw content string."""
    resp = get_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def judge_faithfulness(answer: str, sources: list) -> float:
    """
    Same rubric as scorer.py faithfulness judge.
    Returns normalised score: (raw_1to5 - 1) / 4 → 0.0–1.0.
    Refusal string → 1.0 (correct behaviour).
    """
    if REFUSAL_STRING in answer:
        return 1.0

    if not sources:
        return 0.0

    context_block = "Source passages:\n\n" + "\n".join(
        f"[{i}] {c.get('company', c.get('ticker'))} | {c.get('year')} | "
        f"{c.get('section_name', c.get('section'))}\n\"{c['text'].strip()}\"\n"
        for i, c in enumerate(sources, 1)
    )

    rubric = (
        "Score the answer on a scale of 1 to 5 using this rubric:\n"
        "  5 = Every claim in the answer is directly supported by the passages\n"
        "  4 = Most claims are supported; minor inference is present\n"
        "  3 = Answer is partially supported; some claims go beyond the passages\n"
        "  2 = Answer makes claims that are not in the passages\n"
        "  1 = Answer contradicts or ignores the passages entirely\n"
        "Respond with a single integer (1, 2, 3, 4, or 5) and nothing else."
    )

    prompt = (
        f"{context_block}\n"
        f"Answer to evaluate:\n\"{answer.strip()}\"\n\n"
        f"{rubric}"
    )

    raw = _call_judge(
        "You are a faithfulness evaluator. Respond with a single integer 1-5 only.",
        prompt,
        max_tokens=5,
    )
    m = re.search(r"[1-5]", raw)
    raw_score = int(m.group()) if m else 3
    return round((raw_score - 1) / 4, 4)


def judge_answer_relevance(query: str, answer: str) -> float:
    """
    Scores 1-5 whether the answer addresses the question.
    Refusal on an INVALID query = N/A (returned as None).
    Refusal on a VALID query = 0.0 (couldn't answer).
    """
    if REFUSAL_STRING in answer:
        return 0.0

    prompt = (
        f"Question: {query}\n"
        f"Answer: {answer}\n\n"
        "Does this answer address the question? Score 1 to 5:\n"
        "  5 = completely and accurately addresses the question\n"
        "  4 = mostly addresses the question with minor gaps\n"
        "  3 = partially addresses the question\n"
        "  2 = tangentially related but does not answer the question\n"
        "  1 = does not address the question at all\n"
        "Respond with a single integer (1, 2, 3, 4, or 5) and nothing else."
    )

    raw = _call_judge(
        "You are an answer quality evaluator. Respond with a single integer 1-5 only.",
        prompt,
        max_tokens=5,
    )
    m = re.search(r"[1-5]", raw)
    raw_score = int(m.group()) if m else 3
    return round((raw_score - 1) / 4, 4)


def judge_context_precision(query: str, sources: list) -> float:
    """
    For each retrieved chunk, judges whether it is relevant to the query.
    Returns fraction of retrieved chunks that are relevant (0.0–1.0).

    NOTE: Full chunk text is passed (not truncated). A 10-chunk prompt is
    ~3,500 words — well within the 128K-token context of llama-3.1-8b-instant.
    Truncating to 300 chars (< 20% of each chunk) causes the judge to miss
    facts that appear later in the passage, systematically underestimating
    precision.
    """
    if not sources:
        return 0.0

    context_block = "\n".join(
        f"[{i}] {c.get('company', c.get('ticker'))} | {c.get('year')} | "
        f"{c.get('section_name', c.get('section'))}: "
        f"\"{c['text'].strip()}\""
        for i, c in enumerate(sources, 1)
    )

    prompt = (
        f"Question: {query}\n\n"
        f"Retrieved chunks:\n{context_block}\n\n"
        f"For each chunk numbered 1 to {len(sources)}, answer YES if the chunk is relevant "
        f"to answering the question, or NO if it is not relevant.\n"
        f"Respond with exactly {len(sources)} answers as a comma-separated list "
        f"(e.g. YES,YES,NO,YES). No other text."
    )

    raw = _call_judge(
        "You are a relevance evaluator. Respond only with a comma-separated list of YES/NO values.",
        prompt,
        max_tokens=60,
    ).upper()

    answers = [a.strip() for a in raw.split(",") if a.strip() in ("YES", "NO")]
    if not answers:
        print(f"    [context_precision] could not parse: {raw!r} — defaulting to 0.5")
        return 0.5
    return round(sum(1 for a in answers if a == "YES") / len(answers), 4)


def judge_context_recall(query: str, ground_truth: str, sources: list) -> float:
    """
    Checks whether the retrieved chunks contain enough information to derive
    the ground truth answer.
    Returns 1.0 (YES), 0.5 (PARTIAL), or 0.0 (NO).

    NOTE: Full chunk text is passed. Truncating to 300 chars caused the judge
    to always return PARTIAL because key facts appear beyond character 300 in
    most chunks. Recall was consistently 0.5 — a measurement artefact, not a
    real retrieval signal.
    """
    if not sources:
        return 0.0

    context_block = "\n".join(
        f"[{i}] {c.get('company', c.get('ticker'))} | {c.get('year')} | "
        f"{c.get('section_name', c.get('section'))}: "
        f"\"{c['text'].strip()}\""
        for i, c in enumerate(sources, 1)
    )

    prompt = (
        f"Question: {query}\n"
        f"Ground truth answer: {ground_truth}\n\n"
        f"Retrieved chunks:\n{context_block}\n\n"
        "Can the ground truth answer be derived from the retrieved chunks above?\n"
        "Answer with a single word:\n"
        "  YES     = all key facts in the ground truth are present in the chunks\n"
        "  PARTIAL = some key facts are present but others are missing\n"
        "  NO      = the chunks do not contain the information needed\n"
        "Respond with YES, PARTIAL, or NO and nothing else."
    )

    raw = _call_judge(
        "You are a retrieval evaluator. Respond with YES, PARTIAL, or NO only.",
        prompt,
        max_tokens=10,
    ).upper()

    if "YES" in raw and "PARTIAL" not in raw:
        return 1.0
    elif "PARTIAL" in raw:
        return 0.5
    else:
        return 0.0


# ---------------------------------------------------------------------------
# Per-query evaluation driver
# ---------------------------------------------------------------------------

def evaluate_query(
    entry: dict,
    retriever: Retriever,
    synthesizer: Synthesizer,
    scorer: Scorer,
) -> dict:
    """
    Runs the full pipeline on one query entry and computes all 4 metrics.

    For invalid queries: checks that the retriever correctly rejects them.
    For valid queries: runs synthesis + scoring + all 4 judges.
    """
    qid         = entry["query_id"]
    query       = entry["query"]
    ground_truth = entry.get("ground_truth", "")
    is_valid    = entry.get("is_valid", True)

    print(f"\n{'=' * 65}")
    print(f"  {qid} [{entry.get('query_type','?')}]: {query[:70]}")
    print(f"{'=' * 65}")

    base = {
        "query_id":   qid,
        "query":      query,
        "query_type": entry.get("query_type", "unknown"),
        "is_valid":   is_valid,
        "ground_truth": ground_truth,
    }

    # ------------------------------------------------------------------
    # Step 1 — Retrieval
    # ------------------------------------------------------------------
    print("  [1/5] Retrieving...")
    chunks = retriever.retrieve(query)

    if isinstance(chunks, dict) and "error" in chunks:
        if not is_valid:
            # Correct rejection — full marks for this special case
            print(f"  ✓ Correctly rejected: {chunks['error']}")
            return {**base, "status": "correctly_rejected",
                    "rejection_reason": chunks["error"],
                    "faithfulness": None, "answer_relevance": None,
                    "context_precision": None, "context_recall": None}
        else:
            # Valid query unexpectedly rejected
            print(f"  ✗ Unexpected rejection: {chunks['error']}")
            return {**base, "status": "unexpected_rejection",
                    "rejection_reason": chunks["error"],
                    "faithfulness": 0.0, "answer_relevance": 0.0,
                    "context_precision": 0.0, "context_recall": 0.0}

    if not is_valid:
        # Invalid query that was NOT rejected
        print(f"  ✗ Invalid query not rejected — {len(chunks)} chunks retrieved")

    # ------------------------------------------------------------------
    # Step 2 — Synthesis
    # ------------------------------------------------------------------
    print("  [2/5] Synthesizing...")
    synth_result = synthesizer.synthesize(query, chunks)
    answer  = synth_result["answer"]
    sources = synth_result["sources"]
    print(f"  Answer preview: {answer[:100]}...")

    # ------------------------------------------------------------------
    # Step 3 — Faithfulness (via Scorer for consistency)
    # ------------------------------------------------------------------
    print("  [3/5] Faithfulness judge...")
    score_dict   = scorer.score(synth_result)
    faithfulness = score_dict["faithfulness_score"]
    time.sleep(INTER_JUDGE_DELAY)

    # ------------------------------------------------------------------
    # Step 4 — Answer Relevance
    # ------------------------------------------------------------------
    print("  [4/5] Answer relevance judge...")
    answer_relevance = judge_answer_relevance(query, answer)
    time.sleep(INTER_JUDGE_DELAY)

    # ------------------------------------------------------------------
    # Step 5 — Context Precision + Recall (two calls)
    # ------------------------------------------------------------------
    print("  [5/5] Context precision + recall judges...")
    context_precision = judge_context_precision(query, sources)
    time.sleep(INTER_JUDGE_DELAY)
    context_recall = judge_context_recall(query, ground_truth, sources)

    print(
        f"\n  faithfulness={faithfulness:.3f} | "
        f"relevance={answer_relevance:.3f} | "
        f"precision={context_precision:.3f} | "
        f"recall={context_recall:.3f}"
    )

    return {
        **base,
        "status":             "evaluated",
        "answer":             answer,
        "chunks_retrieved":   len(chunks),
        "chunks_used":        len(sources),
        "avg_retrieval_sim":  score_dict["avg_retrieval_similarity"],
        "confidence":         score_dict["confidence_score"],
        "faithfulness":       round(faithfulness, 4),
        "answer_relevance":   round(answer_relevance, 4),
        "context_precision":  round(context_precision, 4),
        "context_recall":     round(context_recall, 4),
    }


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(results: list) -> None:
    print("\n" + "=" * 65)
    print("EVALUATION SUMMARY")
    print("=" * 65)

    header = f"{'ID':<5} {'Type':<20} {'Faith':>6} {'Relev':>6} {'Prec':>6} {'Rec':>6} {'Status'}"
    print(header)
    print("-" * 65)

    valid_scores = {"faithfulness": [], "answer_relevance": [],
                    "context_precision": [], "context_recall": []}

    for r in results:
        status = r.get("status", "?")
        if status == "correctly_rejected":
            line = (f"{r['query_id']:<5} {r['query_type']:<20} "
                    f"{'N/A':>6} {'N/A':>6} {'N/A':>6} {'N/A':>6}  ✓ rejected")
        elif status in ("unexpected_rejection", "evaluated"):
            f  = r.get("faithfulness",      0.0) or 0.0
            ar = r.get("answer_relevance",  0.0) or 0.0
            cp = r.get("context_precision", 0.0) or 0.0
            cr = r.get("context_recall",    0.0) or 0.0
            mark = "✗ bad reject" if status == "unexpected_rejection" else ""
            line = (f"{r['query_id']:<5} {r['query_type']:<20} "
                    f"{f:>6.3f} {ar:>6.3f} {cp:>6.3f} {cr:>6.3f}  {mark}")
            if status == "evaluated" and r.get("is_valid", True):
                valid_scores["faithfulness"].append(f)
                valid_scores["answer_relevance"].append(ar)
                valid_scores["context_precision"].append(cp)
                valid_scores["context_recall"].append(cr)
        else:
            line = f"{r['query_id']:<5} {r['query_type']:<20} — {status}"

        print(line)

    print("-" * 65)
    if any(valid_scores.values()):
        avg = lambda lst: sum(lst) / len(lst) if lst else 0.0
        print(
            f"{'AVERAGE':<26} "
            f"{avg(valid_scores['faithfulness']):>6.3f} "
            f"{avg(valid_scores['answer_relevance']):>6.3f} "
            f"{avg(valid_scores['context_precision']):>6.3f} "
            f"{avg(valid_scores['context_recall']):>6.3f}"
        )
    print("=" * 65)
    print(f"\nResults written to: {EVAL_RESULTS_PATH}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 65)
    print("ragas_evaluator.py — RAG Pipeline Evaluation")
    print("=" * 65)

    # Load eval queries
    if not os.path.exists(EVAL_QUERIES_PATH):
        print(f"ERROR: {EVAL_QUERIES_PATH} not found. Run from project root.")
        sys.exit(1)

    with open(EVAL_QUERIES_PATH, "r", encoding="utf-8") as f:
        queries = json.load(f)

    print(f"\nLoaded {len(queries)} eval queries from {EVAL_QUERIES_PATH}")
    print("Initialising pipeline components...\n")

    retriever   = Retriever()
    synthesizer = Synthesizer()
    scorer      = Scorer()

    results = []
    for i, entry in enumerate(queries, start=1):
        print(f"\n[{i}/{len(queries)}] Processing {entry['query_id']}...")
        result = evaluate_query(entry, retriever, synthesizer, scorer)
        results.append(result)

        # Brief pause between queries to respect rate limits
        if i < len(queries):
            print(f"\n  [rate-limit guard] waiting 10s before next query...")
            time.sleep(10)

    # Compute aggregate averages and add to output
    valid_results = [r for r in results if r.get("status") == "evaluated" and r.get("is_valid")]
    metrics = ["faithfulness", "answer_relevance", "context_precision", "context_recall"]
    aggregate = {}
    for m in metrics:
        scores = [r[m] for r in valid_results if r.get(m) is not None]
        aggregate[m] = round(sum(scores) / len(scores), 4) if scores else None

    output = {
        "run_timestamp": datetime.now().isoformat(),
        "model":         GROQ_MODEL,
        "num_queries":   len(queries),
        "num_evaluated": len(valid_results),
        "aggregate":     aggregate,
        "results":       results,
    }

    # Save to file
    os.makedirs(os.path.dirname(EVAL_RESULTS_PATH), exist_ok=True)
    with open(EVAL_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print_summary(results)

    print("\nAggregate scores (valid queries only):")
    for m, v in aggregate.items():
        label = v if v is not None else "N/A"
        print(f"  {m:<22}: {label}")


if __name__ == "__main__":
    main()
