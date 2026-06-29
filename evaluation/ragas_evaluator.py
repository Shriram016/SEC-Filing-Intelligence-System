"""
evaluation/ragas_evaluator.py

RAG Evaluation using RAGAS 0.4.3 library with checkpointing.

Runs 24 queries from eval_queries_v2.json through the pipeline and scores
with RAGAS metrics using Groq (llama-3.3-70b-versatile) as the LLM judge.

Metrics:
  1. Faithfulness      — does the answer stay within retrieved context?
  2. Answer Relevance  — does the answer address the question?
  3. Context Precision — are relevant chunks ranked at the top? (needs ground truth)
  4. Context Recall    — does retrieved context cover the ground truth? (needs ground truth)

Query type handling:
  - single_factual, cross_year, cross_company, conflict_triggering → all 4 metrics
  - vague → faithfulness + answer relevance only (no ground truth)
  - invalid → no metrics, just verify rejection

Checkpointing:
  After each query completes, results are saved to eval_checkpoint.json.
  On rerun, already-completed queries are skipped.
  Delete eval_checkpoint.json to force a fresh run.

Run from project root:
    python evaluation/ragas_evaluator.py
"""

from __future__ import annotations

import os
import sys
import json
import time
import asyncio
import warnings
from datetime import datetime

warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config import GROQ_MODEL, CONFLICT_MODEL
from retrieval.retriever import Retriever
from synthesis.synthesizer import Synthesizer
from logger import setup_query_logger

from ragas.metrics.collections import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecisionWithReference,
    ContextRecall,
)
from ragas.llms import llm_factory
from ragas.embeddings.base import embedding_factory
from openai import AsyncOpenAI

EVAL_QUERIES_PATH = "evaluation/eval_queries_v2.json"
EVAL_RESULTS_PATH = "evaluation/eval_results_v2.json"
CHECKPOINT_PATH = "evaluation/eval_checkpoint.json"

PIPELINE_QUERY_DELAY = 10
PIPELINE_REJECT_DELAY = 5
RAGAS_METRIC_DELAY = 10
RAGAS_QUERY_DELAY = 20
MAX_JUDGE_CHUNKS = None

FULL_METRICS_TYPES = {"single_factual", "cross_year", "cross_company", "conflict_triggering"}
PARTIAL_METRICS_TYPES = {"vague"}
NO_METRICS_TYPES = {"invalid"}


# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------

def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_checkpoint(checkpoint: dict) -> None:
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# RAGAS LLM + Embeddings setup
# ---------------------------------------------------------------------------

def get_ragas_llm():
    client = AsyncOpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
    return llm_factory(
        model=CONFLICT_MODEL,
        provider="openai",
        client=client,
        max_tokens=8192,
    )


def get_ragas_embeddings():
    from config import EMBEDDING_MODEL
    return embedding_factory(
        provider="huggingface",
        model=EMBEDDING_MODEL,
        interface="modern",
    )


# ---------------------------------------------------------------------------
# Phase 1 — Pipeline run (retrieve + synthesize)
# ---------------------------------------------------------------------------

def run_pipeline_for_query(
    entry: dict, retriever: Retriever, synthesizer: Synthesizer
) -> dict:
    qid = entry["query_id"]
    query = entry["query"]
    gt = entry.get("ground_truth") or ""
    is_valid = entry.get("is_valid", True)
    query_type = entry.get("query_type", "unknown")

    log = setup_query_logger(f"[EVAL {qid}] {query}")

    chunks = retriever.retrieve(query, logger=log)

    if isinstance(chunks, dict) and "error" in chunks:
        status = "correctly_rejected" if not is_valid else "unexpected_rejection"
        print(f"  {'Correctly rejected' if not is_valid else 'UNEXPECTED rejection'}: {chunks['error']}")
        log.info(f"EVAL | {qid} | status={status} | reason={chunks['error']}")
        return {
            "query_id": qid, "query": query,
            "query_type": query_type,
            "is_valid": is_valid, "ground_truth": gt,
            "status": status, "rejection_reason": chunks["error"],
        }

    synth_result = synthesizer.synthesize(query, chunks, logger=log)
    answer = synth_result["answer"]
    sources = synth_result["sources"]
    print(f"  Answer: {answer[:100].encode('ascii', 'replace').decode()}...")
    print(f"  Chunks retrieved: {len(chunks)}, used: {len(sources)}")

    return {
        "query_id": qid, "query": query,
        "query_type": query_type,
        "is_valid": is_valid, "ground_truth": gt,
        "status": "evaluated",
        "answer": answer,
        "chunks_retrieved": len(chunks),
        "chunks_used": len(sources),
        "context_texts": [c["text"].strip() for c in sources],
    }


# ---------------------------------------------------------------------------
# Phase 2 — RAGAS scoring
# ---------------------------------------------------------------------------

async def score_query_with_ragas(
    entry: dict,
    faithfulness_metric,
    relevancy_metric,
    precision_metric,
    recall_metric,
) -> dict:
    query = entry["query"]
    answer = entry["answer"]
    ref = entry.get("ground_truth") or ""
    query_type = entry.get("query_type", "unknown")
    contexts = entry["context_texts"]

    run_all = query_type in FULL_METRICS_TYPES
    run_partial = query_type in PARTIAL_METRICS_TYPES

    print("    Faithfulness...")
    f_result = await faithfulness_metric.ascore(
        user_input=query, response=answer, retrieved_contexts=contexts,
    )
    entry["faithfulness"] = round(float(f_result.value), 4)
    print(f"      = {entry['faithfulness']}")
    await asyncio.sleep(RAGAS_METRIC_DELAY)

    print("    Answer Relevancy...")
    ar_result = await relevancy_metric.ascore(
        user_input=query, response=answer,
    )
    entry["answer_relevance"] = round(float(ar_result.value), 4)
    print(f"      = {entry['answer_relevance']}")
    await asyncio.sleep(RAGAS_METRIC_DELAY)

    if run_all:
        print("    Context Precision...")
        cp_result = await precision_metric.ascore(
            user_input=query, retrieved_contexts=contexts, reference=ref,
        )
        entry["context_precision"] = round(float(cp_result.value), 4)
        print(f"      = {entry['context_precision']}")
        await asyncio.sleep(RAGAS_METRIC_DELAY)

        print("    Context Recall...")
        cr_result = await recall_metric.ascore(
            user_input=query, retrieved_contexts=contexts, reference=ref,
        )
        entry["context_recall"] = round(float(cr_result.value), 4)
        print(f"      = {entry['context_recall']}")
    else:
        entry["context_precision"] = None
        entry["context_recall"] = None
        print("    Context Precision... SKIPPED (no ground truth)")
        print("    Context Recall... SKIPPED (no ground truth)")

    return entry


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(results: list) -> None:
    print("\n" + "=" * 75)
    print("EVALUATION SUMMARY (RAGAS 0.4.3 — eval_queries_v2)")
    print("=" * 75)

    header = f"{'ID':<5} {'Type':<22} {'Faith':>6} {'Relev':>6} {'Prec':>6} {'Rec':>6}  {'Status'}"
    print(header)
    print("-" * 75)

    scores_by_type = {}

    for r in results:
        status = r.get("status", "?")
        qtype = r.get("query_type", "?")

        if status == "correctly_rejected":
            line = (f"{r['query_id']:<5} {qtype:<22} "
                    f"{'N/A':>6} {'N/A':>6} {'N/A':>6} {'N/A':>6}  rejected")
        elif status in ("unexpected_rejection", "evaluated"):
            f = r.get("faithfulness", 0.0) or 0.0
            ar = r.get("answer_relevance", 0.0) or 0.0
            cp = r.get("context_precision")
            cr = r.get("context_recall")
            cp_str = f"{cp:>6.3f}" if cp is not None else f"{'N/A':>6}"
            cr_str = f"{cr:>6.3f}" if cr is not None else f"{'N/A':>6}"
            mark = "BAD REJECT" if status == "unexpected_rejection" else ""
            line = (f"{r['query_id']:<5} {qtype:<22} "
                    f"{f:>6.3f} {ar:>6.3f} {cp_str} {cr_str}  {mark}")

            if status == "evaluated":
                if qtype not in scores_by_type:
                    scores_by_type[qtype] = {"faithfulness": [], "answer_relevance": [],
                                             "context_precision": [], "context_recall": []}
                scores_by_type[qtype]["faithfulness"].append(f)
                scores_by_type[qtype]["answer_relevance"].append(ar)
                if cp is not None:
                    scores_by_type[qtype]["context_precision"].append(cp)
                if cr is not None:
                    scores_by_type[qtype]["context_recall"].append(cr)
        else:
            line = f"{r['query_id']:<5} {qtype:<22} - {status}"

        print(line)

    print("-" * 75)

    avg = lambda lst: round(sum(lst) / len(lst), 4) if lst else None

    all_f, all_ar, all_cp, all_cr = [], [], [], []

    for qtype, scores in sorted(scores_by_type.items()):
        f_avg = avg(scores["faithfulness"])
        ar_avg = avg(scores["answer_relevance"])
        cp_avg = avg(scores["context_precision"])
        cr_avg = avg(scores["context_recall"])
        cp_str = f"{cp_avg:>6.3f}" if cp_avg is not None else f"{'N/A':>6}"
        cr_str = f"{cr_avg:>6.3f}" if cr_avg is not None else f"{'N/A':>6}"
        print(f"  avg {qtype:<20} {f_avg:>6.3f} {ar_avg:>6.3f} {cp_str} {cr_str}")
        all_f.extend(scores["faithfulness"])
        all_ar.extend(scores["answer_relevance"])
        all_cp.extend(scores["context_precision"])
        all_cr.extend(scores["context_recall"])

    print("-" * 75)
    f_all = avg(all_f)
    ar_all = avg(all_ar)
    cp_all = avg(all_cp)
    cr_all = avg(all_cr)
    cp_str = f"{cp_all:>6.3f}" if cp_all is not None else f"{'N/A':>6}"
    cr_str = f"{cr_all:>6.3f}" if cr_all is not None else f"{'N/A':>6}"
    if f_all is not None:
        print(f"  {'OVERALL':<25} {f_all:>6.3f} {ar_all:>6.3f} {cp_str} {cr_str}")
    print("=" * 75)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="RAG Evaluation (RAGAS 0.4.3)")
    parser.add_argument(
        "--queries", nargs="+", default=None,
        help="Run only specific query IDs, e.g. --queries Q04 Q05 Q12"
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Ignore checkpoint for specified queries (re-score them)"
    )
    args = parser.parse_args()

    print("=" * 75)
    print("ragas_evaluator.py — RAG Evaluation (RAGAS 0.4.3 + checkpointing)")
    print("=" * 75)

    if not os.path.exists(EVAL_QUERIES_PATH):
        print(f"ERROR: {EVAL_QUERIES_PATH} not found. Run from project root.")
        sys.exit(1)

    with open(EVAL_QUERIES_PATH, "r", encoding="utf-8") as f:
        all_queries = json.load(f)

    if args.queries:
        query_ids = set(args.queries)
        queries = [q for q in all_queries if q["query_id"] in query_ids]
        missing = query_ids - {q["query_id"] for q in queries}
        if missing:
            print(f"WARNING: query IDs not found in eval set: {missing}")
        print(f"\nRunning {len(queries)} selected queries: {args.queries}")
    else:
        queries = all_queries
        print(f"\nRunning all {len(queries)} queries")

    checkpoint = load_checkpoint()

    if args.fresh and args.queries:
        for qid in args.queries:
            checkpoint.pop(qid, None)

    completed_ids = set(checkpoint.keys())

    print(f"Checkpoint: {len(completed_ids)} already completed")

    remaining = [q for q in queries if q["query_id"] not in completed_ids]
    if not remaining:
        print("\nAll selected queries already completed. Use --fresh to re-score.")
        results = [checkpoint[q["query_id"]] for q in queries]
        print_summary(results)
        return

    print(f"Remaining: {len(remaining)} queries to process")
    print("Initialising pipeline components...\n")

    retriever = Retriever()
    synthesizer = Synthesizer()

    llm = get_ragas_llm()
    embeddings = get_ragas_embeddings()
    faithfulness_metric = Faithfulness(llm=llm)
    relevancy_metric = AnswerRelevancy(llm=llm, embeddings=embeddings)
    precision_metric = ContextPrecisionWithReference(llm=llm)
    recall_metric = ContextRecall(llm=llm)

    for i, entry in enumerate(remaining, start=1):
        qid = entry["query_id"]
        query_type = entry.get("query_type", "unknown")

        print(f"\n{'='*60}")
        print(f"[{len(completed_ids)+1}/{len(queries)}] {qid} ({query_type}): {entry['query'][:60]}")
        print("=" * 60)

        # Phase 1 — Pipeline
        print("\n  Phase 1: Pipeline (retrieve + synthesize)...")
        result = run_pipeline_for_query(entry, retriever, synthesizer)

        # Phase 2 — RAGAS scoring
        if result["status"] == "evaluated" and query_type not in NO_METRICS_TYPES:
            print(f"\n  Phase 2: RAGAS scoring...")
            result = asyncio.run(score_query_with_ragas(
                result, faithfulness_metric, relevancy_metric,
                precision_metric, recall_metric,
            ))
        elif result["status"] == "correctly_rejected":
            result.update({"faithfulness": None, "answer_relevance": None,
                           "context_precision": None, "context_recall": None})
        elif result["status"] == "unexpected_rejection":
            result.update({"faithfulness": 0.0, "answer_relevance": 0.0,
                           "context_precision": 0.0, "context_recall": 0.0})

        result.pop("context_texts", None)

        checkpoint[qid] = result
        save_checkpoint(checkpoint)
        completed_ids.add(qid)
        print(f"\n  Checkpointed {qid}. ({len(completed_ids)}/{len(queries)} done)")

        if i < len(remaining):
            print(f"  [rate-limit guard] waiting {RAGAS_QUERY_DELAY}s...")
            time.sleep(RAGAS_QUERY_DELAY)

    # -- Final output --
    results = [checkpoint[q["query_id"]] for q in queries if q["query_id"] in checkpoint]

    # Compute aggregates
    metric_names = ["faithfulness", "answer_relevance", "context_precision", "context_recall"]
    scored = [r for r in results if r.get("status") == "evaluated"]
    aggregate = {}
    for m in metric_names:
        values = [r[m] for r in scored if r.get(m) is not None]
        aggregate[m] = round(sum(values) / len(values), 4) if values else None

    output = {
        "run_timestamp": datetime.now().isoformat(),
        "pipeline_model": GROQ_MODEL,
        "judge_model": CONFLICT_MODEL,
        "eval_framework": "ragas-0.4.3",
        "eval_set": EVAL_QUERIES_PATH,
        "num_queries": len(queries),
        "num_evaluated": len(scored),
        "aggregate": aggregate,
        "results": results,
    }

    print_summary(results)

    if args.fresh and args.queries:
        print(f"\n[--fresh mode] Skipping write to {EVAL_RESULTS_PATH} (partial run)")
    else:
        os.makedirs(os.path.dirname(EVAL_RESULTS_PATH), exist_ok=True)
        with open(EVAL_RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\nResults written to: {EVAL_RESULTS_PATH}")

    print("\nAggregate scores:")
    for m, v in aggregate.items():
        print(f"  {m:<22}: {v if v is not None else 'N/A'}")


if __name__ == "__main__":
    main()
