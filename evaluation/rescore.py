"""
evaluation/rescore.py

Re-score a finished run's SAVED answers with the current scorers, without re-running the pipeline.
The original results.json is never touched; output goes next to it:

  rescored.json          new scores + per-statement/fact verdicts, with the old scores for comparison
  rescored_usage.json    tokens and cost of the re-scoring
  summary_rescored.json  per-category summary of the new scores
  rescore.log            console output

Reused as saved: answers, retrieved chunks, ground truths. Redone: every judge call, with the
judge shown the same numbered passages the answering model saw.

    python evaluation/rescore.py --run-id full1_20261013
    python evaluation/rescore.py --run-id full1_20261013 --queries Q05 Q06
"""

from __future__ import annotations

import os
import sys
import asyncio
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config import COMPANIES, JUDGE_MODEL, PRICES_CHECKED, PRICES_PER_M_TOKENS, TARGET_SECTIONS, TICKERS
from evaluation.eval_helpers import (
    METRICS_BY_TYPE,
    UsageTracker,
    build_summary,
    format_summary,
    numbered_context_passages,
)
from evaluation.ragas_evaluator import (
    DEFAULT_METRIC_DELAY,
    RUNS_DIR,
    Tee,
    ascii_safe,
    build_metrics,
    read_json,
    score_with_ragas,
    write_json,
)

TICKER_TO_COMPANY = dict(zip(TICKERS, COMPANIES))
OLD_NAME = {"ground_truth_coverage": "factual_correctness"}   # the metric this one replaced in full1


def judge_passages(record: dict) -> list[str]:
    """Numbered passages exactly as the answering model saw them, rebuilt from the saved chunks."""
    used = []
    for c in record["retrieved_chunks"]:
        if not c.get("used"):
            continue
        used.append(dict(
            c,
            company=c.get("company") or TICKER_TO_COMPANY.get(c.get("ticker"), c.get("ticker")),
            section_name=c.get("section_name") or TARGET_SECTIONS.get(c.get("section"), c.get("section")),
        ))
    return numbered_context_passages(used)


def fmt(v):
    return "  -  " if v is None else f"{v:5.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-score a finished run's saved answers")
    parser.add_argument("--run-id", required=True, help="existing run folder under evaluation/runs/")
    parser.add_argument("--queries", nargs="+", default=None)
    parser.add_argument("--judge-model", default=JUDGE_MODEL)
    parser.add_argument("--metric-delay", type=float, default=DEFAULT_METRIC_DELAY)
    args = parser.parse_args()

    run_dir = os.path.join(RUNS_DIR, args.run_id)
    source = read_json(os.path.join(run_dir, "results.json"), None)
    if source is None:
        print(f"ERROR: {run_dir}/results.json not found. Run from project root.")
        sys.exit(1)

    sys.stdout = Tee(sys.stdout, os.path.join(run_dir, "rescore.log"))
    out_path = os.path.join(run_dir, "rescored.json")
    usage_path = os.path.join(run_dir, "rescored_usage.json")
    rescored: dict = read_json(out_path, {})
    tracker = UsageTracker(prices=PRICES_PER_M_TOKENS)
    tracker.load_calls(read_json(usage_path, {}).get("calls", []))

    todo = [
        q for q, r in source.items()
        if r.get("status") == "evaluated" and r["query_type"] in METRICS_BY_TYPE
        and (not args.queries or q in args.queries) and q not in rescored
    ]
    print(f"Re-scoring run {args.run_id}: {len(todo)} queries to do, {len(rescored)} already done, judge {args.judge_model}")
    metrics = build_metrics(tracker, args.judge_model) if todo else None

    for i, qid in enumerate(todo, 1):
        old = source[qid]
        print(f"\n[{i}/{len(todo)}] {qid} ({old['query_type']})")
        tracker.set_query(qid)
        record = {
            "query": old["query"], "answer": old["answer"], "ground_truth": old.get("ground_truth"),
            "query_type": old["query_type"], "_contexts": judge_passages(old),
        }
        try:
            asyncio.run(score_with_ragas(record, metrics, tracker, args.metric_delay))
        except Exception as exc:   # one bad query must not lose the rest
            print(f"  ERROR: {ascii_safe(type(exc).__name__ + ': ' + str(exc))[:300]}")
            record.update({"scores": {}, "metric_errors": {"all": f"{type(exc).__name__}: {exc}"[:300]}, "metric_details": {}})

        rescored[qid] = {
            "query_type": old["query_type"],
            "scores": record["scores"],
            "metric_errors": record["metric_errors"],
            "metric_details": record["metric_details"],
            "old_scores": old.get("scores"),
            "usage": tracker.total(qid),
        }
        write_json(out_path, rescored)
        write_json(usage_path, tracker.to_dict())
        print(f"  saved. cost ${rescored[qid]['usage']['cost_usd']:.4f} | total so far ${tracker.total()['cost_usd']:.4f}")

    # --- comparison table: old -> new -----------------------------------------------------
    print("\n" + "=" * 100)
    print(f"{'ID':<4} {'type':<14} " + " ".join(f"{m[:9]:>15}" for m in
          ("faithfulness", "answer_relevance", "context_precision", "context_recall", "gt_coverage")))
    print("(each cell: old -> new)")
    print("-" * 100)
    for qid, r in rescored.items():
        cells = []
        for m in ("faithfulness", "answer_relevance", "context_precision", "context_recall", "ground_truth_coverage"):
            new = (r["scores"] or {}).get(m)
            old = (r["old_scores"] or {}).get(OLD_NAME.get(m, m))
            cells.append(f"{fmt(old)}->{fmt(new)}" if (new is not None or old is not None) else f"{'':>15}")
        print(f"{qid:<4} {r['query_type']:<14} " + " ".join(f"{c:>15}" for c in cells))

    records = [
        {"query_id": q, "query_type": r["query_type"], "status": "evaluated",
         "scores": r["scores"], "metric_errors": r["metric_errors"]}
        for q, r in rescored.items()
    ]
    summary = build_summary(records)
    summary["usage_total"] = tracker.total()
    summary["rescored_at"] = datetime.now().isoformat()
    write_json(os.path.join(run_dir, "summary_rescored.json"), summary)
    print("\nNEW SCORES (answers and chunks from the saved run; yes/no queries are unchanged)")
    print(format_summary(summary))
    total = tracker.total()
    print(f"\nRe-scoring cost: ${total['cost_usd']:.4f} over {total['calls']} calls "
          f"({total['prompt_tokens']:,} in / {total['completion_tokens']:,} out) [prices checked {PRICES_CHECKED}]")


if __name__ == "__main__":
    main()
