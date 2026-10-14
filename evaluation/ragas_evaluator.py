"""
evaluation/ragas_evaluator.py

Runs the eval queries through the real pipeline and scores them.

Per query category (see evaluation/eval_helpers.py):
  single_factual / cross_year / cross_company / vague -> RAGAS metrics (LLM judge)
  should_refuse / invalid                             -> yes/no check, no RAGAS

Every run gets its own folder, evaluation/runs/<run_id>/, and nothing is overwritten:
  meta.json     models, git commit, arguments, query file
  results.json  full record per query (retrieved chunks, filters, answer, confidence, scores)
  usage.json    input/output tokens for every Groq call (read from Groq's replies)
  summary.json  per-category results
  run.log       everything printed to the console

Resume an interrupted run with --run-id <existing id>: finished queries are skipped.

Run from project root (use --dry-run first; it makes no API calls):
    python evaluation/ragas_evaluator.py --dry-run
    python evaluation/ragas_evaluator.py --queries Q03 Q25
    python evaluation/ragas_evaluator.py
"""

from __future__ import annotations

import os
import sys
import json
import math
import time
import shutil
import asyncio
import argparse
import warnings
from datetime import datetime
from types import SimpleNamespace

warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config import GROQ_MODEL, JUDGE_MODEL, EMBEDDING_MODEL, PRICES_PER_M_TOKENS, PRICES_CHECKED
from evaluation.eval_helpers import (
    CHECK_TYPES,
    METRICS_BY_TYPE,
    UsageTracker,
    build_summary,
    check_passed,
    classify_outcome,
    coverage_from_verdicts,
    format_summary,
    git_info,
    numbered_context_passages,
    parse_usage,
    refusal_flags,
)

EVALUATOR_VERSION = "2026-10-14b: numbered judge passages, ground_truth_coverage (atomicity=high), per-statement details"

EVAL_QUERIES_PATH = "evaluation/eval_queries_v2.json"
RUNS_DIR = "evaluation/runs"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

DEFAULT_METRIC_DELAY = 5     # seconds between judge calls (rate-limit guard)
DEFAULT_QUERY_DELAY = 10     # seconds between queries
JUDGE_RETRIES = 2            # extra attempts for a failed judge call
JUDGE_RETRY_WAIT = 20        # seconds before a retry


def ascii_safe(text: str) -> str:
    return text.encode("ascii", "replace").decode()


# ---------------------------------------------------------------------------
# Console output is also written to run.log
# ---------------------------------------------------------------------------

class Tee:
    def __init__(self, stream, path):
        self.stream = stream
        self.file = open(path, "a", encoding="utf-8", errors="replace")

    def write(self, data):
        try:
            self.stream.write(data)
        except UnicodeEncodeError:
            self.stream.write(ascii_safe(data))
        self.file.write(data)
        self.file.flush()

    def flush(self):
        self.stream.flush()
        self.file.flush()


# ---------------------------------------------------------------------------
# Token-counting clients (usage comes from Groq's own replies)
# ---------------------------------------------------------------------------

def make_pipeline_client(tracker: UsageTracker, stage: str):
    """A Groq client for the pipeline that records tokens for every call it makes."""
    import httpx
    from groq import Groq

    def hook(response):
        try:
            response.read()
            parsed = parse_usage(response.json())
            if parsed:
                tracker.add(*parsed, stage=stage)
        except Exception:
            pass

    return Groq(
        api_key=os.getenv("GROQ_API_KEY"),
        timeout=90.0,
        http_client=httpx.Client(timeout=90.0, event_hooks={"response": [hook]}),
    )


def make_judge_client(tracker: UsageTracker):
    """OpenAI-compatible async client pointed at Groq; records tokens for every judge call."""
    import httpx
    from openai import AsyncOpenAI

    async def hook(response):
        try:
            await response.aread()
            parsed = parse_usage(response.json())
            if parsed:
                tracker.add(*parsed, stage=tracker.current_stage)
        except Exception:
            pass

    return AsyncOpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url=GROQ_BASE_URL,
        timeout=180.0,
        http_client=httpx.AsyncClient(timeout=180.0, event_hooks={"response": [hook]}),
    )


class FaithfulnessWithDetail:
    """
    Same formula as RAGAS Faithfulness (supported statements / all statements), but keeps the
    statements and verdicts so the score can be re-checked. Uses RAGAS's own steps; the private
    methods are why `ragas` is pinned to 0.4.3.
    """

    def __init__(self, llm):
        from ragas.metrics.collections import Faithfulness
        self._metric = Faithfulness(llm=llm)

    async def ascore(self, user_input: str, response: str, retrieved_contexts: list):
        statements = await self._metric._create_statements(user_input, response)
        if not statements:
            return SimpleNamespace(value=float("nan"), detail=[])
        verdicts = await self._metric._create_verdicts(statements, "\n".join(retrieved_contexts))
        return SimpleNamespace(
            value=self._metric._compute_score(verdicts),
            detail=[
                {"statement": s.statement, "supported": bool(s.verdict), "reason": getattr(s, "reason", None)}
                for s in verdicts.statements
            ],
        )


class GroundTruthCoverage:
    """
    Share of ground-truth facts that the answer supports.
    RAGAS's claim-splitting and claim-checking steps, with our own final arithmetic. The stock
    FactualCorrectness(recall) divides by (TP + FN) where TP counts the ANSWER's claims found in the
    ground truth, which returns 0.0 for a correct answer when that count is 0. See docs/EVAL_METRICS_GUIDE.md.
    """

    def __init__(self, llm):
        from ragas.metrics.collections import FactualCorrectness
        self._metric = FactualCorrectness(llm=llm, mode="recall", atomicity="high")  # atomicity="high": many small facts, so partly covered answers earn partial credit

    async def ascore(self, response: str, reference: str):
        facts = await self._metric._decompose_claims(reference)
        if not facts:
            raise ValueError("no facts could be extracted from the ground truth")
        verdicts = await self._metric._verify_claims(facts, response)
        detail = [
            {"fact": s.statement, "supported": bool(s.verdict), "reason": getattr(s, "reason", None)}
            for s in verdicts.statements
        ]
        return SimpleNamespace(value=coverage_from_verdicts([d["supported"] for d in detail]), detail=detail)


def build_metrics(tracker: UsageTracker, judge_model: str) -> dict:
    from ragas.llms import llm_factory
    from ragas.embeddings.base import embedding_factory
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecisionWithReference,
        ContextRecall,
    )

    llm = llm_factory(
        model=judge_model, provider="openai", client=make_judge_client(tracker), max_tokens=8192,
    )
    embeddings = embedding_factory(provider="huggingface", model=EMBEDDING_MODEL, interface="modern")
    return {
        "faithfulness": FaithfulnessWithDetail(llm),
        "answer_relevance": AnswerRelevancy(llm=llm, embeddings=embeddings),
        "context_precision": ContextPrecisionWithReference(llm=llm),
        "context_recall": ContextRecall(llm=llm),
        "ground_truth_coverage": GroundTruthCoverage(llm),
    }


# ---------------------------------------------------------------------------
# Phase 1 — pipeline (retrieve, synthesize, app confidence)
# ---------------------------------------------------------------------------

def run_pipeline_for_query(entry: dict, retriever, synthesizer, scorer, tracker: UsageTracker, holder: dict) -> dict:
    from logger import setup_query_logger

    qid, query = entry["query_id"], entry["query"]
    qtype = entry.get("query_type", "unknown")
    tracker.set_query(qid)
    log = setup_query_logger(f"[EVAL {qid}] {query}")
    holder["log"] = log   # lets the caller copy this query's log into the run folder, even after an error

    # Capture the filters the parser extracted, without touching pipeline code.
    captured = {}
    original = retriever._extract_filters

    def capturing_extract(q, logger=None):
        out = original(q, logger)
        captured["filters"] = out
        return out

    retriever._extract_filters = capturing_extract
    try:
        chunks = retriever.retrieve(query, logger=log)
    finally:
        retriever._extract_filters = original

    record = {
        "query_id": qid,
        "query": query,
        "query_type": qtype,
        "is_valid": entry.get("is_valid", True),
        "ground_truth": entry.get("ground_truth"),
        "expected_tickers": entry.get("expected_tickers", []),
        "expected_years": entry.get("expected_years", []),
        "expected_sections": entry.get("expected_sections", []),
        "reject_also_ok": entry.get("reject_also_ok", False),
        "filters": captured.get("filters"),
    }

    if isinstance(chunks, dict) and "error" in chunks:
        unexpected = qtype not in CHECK_TYPES
        print(f"  {'UNEXPECTED rejection' if unexpected else 'Rejected'}: {chunks['error']}")
        record.update({
            "status": "unexpected_rejection" if unexpected else "evaluated",
            "outcome": "rejected",
            "rejection_reason": chunks["error"],
        })
        return record

    synth = synthesizer.synthesize(query, chunks, logger=log)
    answer = synth["answer"]
    sources = synth["sources"]
    used_ids = {c["chunk_id"] for c in sources}
    print(f"  Answer: {ascii_safe(answer[:100])}...")
    print(f"  Chunks retrieved: {len(chunks)}, used: {len(sources)}")

    confidence = scorer.score(synth, logger=log)

    groups_retrieved = sorted({c.get("group") or "" for c in chunks})
    groups_used = sorted({c.get("group") or "" for c in sources})

    record.update({
        "status": "evaluated",
        "answer": answer,
        "refusal": refusal_flags(answer),
        "app_confidence": confidence,
        "chunks_retrieved": len(chunks),
        "chunks_used": len(sources),
        "groups_retrieved": groups_retrieved,
        "groups_used": groups_used,
        "retrieved_chunks": [
            {
                "chunk_id": c["chunk_id"],
                "ticker": c.get("ticker"),
                "company": c.get("company"),
                "year": c.get("year"),
                "section": c.get("section"),
                "section_name": c.get("section_name"),
                "group": c.get("group"),
                "similarity_score": c.get("similarity_score"),
                "reranker_score": c.get("reranker_score"),
                "used": c["chunk_id"] in used_ids,
                "text": c["text"],
            }
            for c in chunks
        ],
        # Judge sees the same numbered passages the answering model saw (answers cite "Passage [N]")
        "_contexts": numbered_context_passages(sources),
    })
    record["outcome"] = classify_outcome(False, answer)
    return record


# ---------------------------------------------------------------------------
# Phase 2 — scoring
# ---------------------------------------------------------------------------

async def safe_score(make_call, retries: int = JUDGE_RETRIES, wait: float = JUDGE_RETRY_WAIT):
    """One judge call. Retry on failure, then return (None, error) instead of crashing the run."""
    last = None
    for attempt in range(retries + 1):
        try:
            result = await make_call()
            value = float(result.value)
            detail = getattr(result, "detail", None)   # statement/fact verdicts, when the metric keeps them
            return (None if math.isnan(value) else round(value, 4)), None, detail
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"[:300]
            print(f"      judge call failed (attempt {attempt + 1}): {ascii_safe(last)}")
            if attempt < retries:
                await asyncio.sleep(wait)
    return None, last, None


async def score_with_ragas(record: dict, metrics: dict, tracker: UsageTracker, delay: float) -> None:
    plan = METRICS_BY_TYPE[record["query_type"]]
    q, a = record["query"], record["answer"]
    ref, ctx = record.get("ground_truth") or "", record["_contexts"]

    calls = {
        "faithfulness": lambda m: m.ascore(user_input=q, response=a, retrieved_contexts=ctx),
        "answer_relevance": lambda m: m.ascore(user_input=q, response=a),
        "context_precision": lambda m: m.ascore(user_input=q, retrieved_contexts=ctx, reference=ref),
        "context_recall": lambda m: m.ascore(user_input=q, retrieved_contexts=ctx, reference=ref),
        "ground_truth_coverage": lambda m: m.ascore(response=a, reference=ref),
    }

    scores, errors, details = {}, {}, {}
    for i, name in enumerate(plan):
        tracker.current_stage = f"judge:{name}"
        print(f"    {name}...")
        value, err, detail = await safe_score(lambda n=name: calls[n](metrics[n]))
        scores[name] = value
        if err:
            errors[name] = err
        if detail is not None:
            details[name] = detail
        print(f"      = {value}")
        if i < len(plan) - 1:
            await asyncio.sleep(delay)
    tracker.current_stage = None
    record["scores"] = scores
    record["metric_errors"] = errors
    record["metric_details"] = details


# ---------------------------------------------------------------------------
# Run folder helpers
# ---------------------------------------------------------------------------

def write_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def read_json(path: str, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def dry_run(queries: list[dict]) -> None:
    print("DRY RUN: no API calls, no models loaded\n")
    print(f"{'ID':<5} {'Type':<16} Metrics / check")
    print("-" * 80)
    for q in queries:
        qtype = q.get("query_type", "unknown")
        if qtype in METRICS_BY_TYPE:
            what = ", ".join(METRICS_BY_TYPE[qtype])
        elif qtype in CHECK_TYPES:
            what = "yes/no check (declined: refused or rejected?)"
        else:
            what = "UNKNOWN TYPE: would be skipped"
        gt_missing = qtype in METRICS_BY_TYPE and "context_recall" in METRICS_BY_TYPE[qtype] and not q.get("ground_truth")
        print(f"{q['query_id']:<5} {qtype:<16} {what}" + ("   [MISSING GROUND TRUTH]" if gt_missing else ""))
    by_type = {}
    for q in queries:
        by_type[q.get("query_type")] = by_type.get(q.get("query_type"), 0) + 1
    print("\nQueries per type:", by_type)
    print("Pipeline models:", GROQ_MODEL, "| judge model default:", JUDGE_MODEL)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RAG evaluation (RAGAS 0.4.3), one folder per run")
    parser.add_argument("--queries", nargs="+", default=None, help="only these query IDs, e.g. --queries Q03 Q25")
    parser.add_argument("--run-id", default=None, help="resume an existing run folder (finished queries are skipped)")
    parser.add_argument("--judge-model", default=JUDGE_MODEL, help=f"judge model on Groq (default {JUDGE_MODEL})")
    parser.add_argument("--metric-delay", type=float, default=DEFAULT_METRIC_DELAY)
    parser.add_argument("--query-delay", type=float, default=DEFAULT_QUERY_DELAY)
    parser.add_argument("--dry-run", action="store_true", help="show the plan only; no API calls")
    args = parser.parse_args()

    if not os.path.exists(EVAL_QUERIES_PATH):
        print(f"ERROR: {EVAL_QUERIES_PATH} not found. Run from project root.")
        sys.exit(1)
    with open(EVAL_QUERIES_PATH, "r", encoding="utf-8") as f:
        all_queries = json.load(f)

    queries = all_queries
    if args.queries:
        wanted = set(args.queries)
        queries = [q for q in all_queries if q["query_id"] in wanted]
        missing = wanted - {q["query_id"] for q in queries}
        if missing:
            print(f"WARNING: query IDs not found: {sorted(missing)}")

    if args.dry_run:
        dry_run(queries)
        return

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(RUNS_DIR, run_id)
    resuming = os.path.isdir(run_dir)
    os.makedirs(run_dir, exist_ok=True)
    sys.stdout = Tee(sys.stdout, os.path.join(run_dir, "run.log"))

    results_path = os.path.join(run_dir, "results.json")
    usage_path = os.path.join(run_dir, "usage.json")
    results: dict = read_json(results_path, {})
    tracker = UsageTracker(prices=PRICES_PER_M_TOKENS)
    tracker.load_calls(read_json(usage_path, {}).get("calls", []))
    for model in {GROQ_MODEL, args.judge_model}:
        if model not in PRICES_PER_M_TOKENS:
            print(f"WARNING: no price for {model} in config.PRICES_PER_M_TOKENS; its cost will show as unpriced")

    print("=" * 75)
    print(f"ragas_evaluator.py: run {run_id} ({'RESUMING' if resuming else 'new'})")
    print(f"Queries: {len(queries)} | already done: {len(results)} | judge: {args.judge_model}")
    print("=" * 75)

    meta = read_json(os.path.join(run_dir, "meta.json"), {})
    meta.update({
        "run_id": run_id,
        "started": meta.get("started") or datetime.now().isoformat(),
        "pipeline_model": GROQ_MODEL,
        "judge_model": args.judge_model,
        "eval_framework": "ragas-0.4.3",
        "evaluator_version": EVALUATOR_VERSION,
        "ground_truth_coverage": "share of ground-truth facts (fine-grained, atomicity=high) supported by the answer (RAGAS claim checking, own aggregation)",
        "prices_per_million_tokens": {m: list(p) for m, p in PRICES_PER_M_TOKENS.items()},
        "prices_checked": PRICES_CHECKED,
        "query_file": EVAL_QUERIES_PATH,
        "num_queries_selected": len(queries),
        "git": git_info(),
        "args": vars(args),
    })
    write_json(os.path.join(run_dir, "meta.json"), meta)

    remaining = [q for q in queries if q["query_id"] not in results]
    if remaining:
        print("Loading pipeline components and judge...\n")
        from retrieval.retriever import Retriever
        from synthesis.synthesizer import Synthesizer
        from scoring.scorer import Scorer

        retriever, synthesizer, scorer = Retriever(), Synthesizer(), Scorer()
        retriever.groq_client = make_pipeline_client(tracker, "pipeline:filter_extraction")
        synthesizer.groq_client = make_pipeline_client(tracker, "pipeline:synthesis")
        scorer.groq_client = make_pipeline_client(tracker, "pipeline:app_confidence")
        metrics = build_metrics(tracker, args.judge_model)

        for i, entry in enumerate(remaining, start=1):
            qid, qtype = entry["query_id"], entry.get("query_type", "unknown")
            print(f"\n{'=' * 60}\n[{len(results) + 1}/{len(queries)}] {qid} ({qtype}): {entry['query'][:60]}\n{'=' * 60}")

            if qtype not in METRICS_BY_TYPE and qtype not in CHECK_TYPES:
                print(f"  SKIPPED: unknown query type {qtype!r}")
                continue

            started = time.time()
            holder: dict = {}
            try:
                print("\n  Phase 1: pipeline (retrieve, synthesize, app confidence)...")
                record = run_pipeline_for_query(entry, retriever, synthesizer, scorer, tracker, holder)

                if record["status"] == "evaluated" and qtype in CHECK_TYPES:
                    record["passed"] = check_passed(qtype, record["outcome"])
                    print(f"  Outcome: {record['outcome']} | pass: {record['passed']}")
                elif record["status"] == "evaluated":
                    print("\n  Phase 2: RAGAS scoring...")
                    asyncio.run(score_with_ragas(record, metrics, tracker, args.metric_delay))
            except Exception as exc:
                # A bad key stops everything; any other failure only loses this query.
                if "AuthenticationError" in type(exc).__name__:
                    raise
                error = f"{type(exc).__name__}: {exc}"[:400]
                print(f"  PIPELINE ERROR: {ascii_safe(error)}")
                record = {
                    "query_id": qid, "query": entry["query"], "query_type": qtype,
                    "ground_truth": entry.get("ground_truth"),
                    "status": "pipeline_error", "error": error,
                }

            record.pop("_contexts", None)
            record["seconds"] = round(time.time() - started, 1)
            record["usage"] = tracker.total(qid)

            # Keep this query's pipeline log (filters, reranker, synthesis) inside the run folder.
            log = holder.get("log")
            if log is not None and log.handlers:
                log.handlers[0].flush()
                log_dir = os.path.join(run_dir, "query_logs")
                os.makedirs(log_dir, exist_ok=True)
                shutil.copyfile(log.handlers[0].baseFilename, os.path.join(log_dir, f"{qid}.log"))

            results[qid] = record
            write_json(results_path, results)
            write_json(usage_path, tracker.to_dict())
            run_total = tracker.total()
            print(f"\n  Saved {qid}. tokens in/out: {record['usage']['prompt_tokens']:,}/"
                  f"{record['usage']['completion_tokens']:,} | cost ${record['usage']['cost_usd']:.4f} "
                  f"| run total so far ${run_total['cost_usd']:.4f}")

            if i < len(remaining):
                time.sleep(args.query_delay)

    ordered = [results[q["query_id"]] for q in queries if q["query_id"] in results]
    summary = build_summary(ordered)
    summary["usage_total"] = tracker.total()
    write_json(os.path.join(run_dir, "summary.json"), summary)
    write_json(usage_path, tracker.to_dict())
    meta["finished"] = datetime.now().isoformat()
    write_json(os.path.join(run_dir, "meta.json"), meta)

    print("\n" + format_summary(summary))
    usage = tracker.to_dict()
    total = usage["total"]
    print(f"\nTokens: {total['prompt_tokens']:,} in / {total['completion_tokens']:,} out "
          f"over {total['calls']} Groq calls")
    for model, row in usage["by_model"].items():
        print(f"  {model}: {row['prompt_tokens']:,} in / {row['completion_tokens']:,} out -> ${row['cost_usd']:.4f}")
    print(f"TOTAL COST: ${total['cost_usd']:.4f}" +
          (f"  (+ {total['unpriced_calls']} unpriced calls)" if total["unpriced_calls"] else "") +
          f"  [prices checked {PRICES_CHECKED}]")
    print(f"Run folder: {run_dir}")


if __name__ == "__main__":
    main()
