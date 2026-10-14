"""
evaluation/eval_helpers.py

Pure helpers for ragas_evaluator.py: no API calls, no model loading.
Kept separate so they can be unit-tested offline (tests/offline/test_eval_helpers.py).

Contents:
  - which metrics run for which query category
  - refusal detection (exact sentence + tolerant wording) and outcome rules
  - token usage tracker (input/output tokens per Groq call, from Groq's own replies)
  - run summary maths
  - git info for the run record
"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict

# Same sentence the synthesizer is told to emit when it cannot answer.
from scoring.scorer import REFUSAL_STRING

# ---------------------------------------------------------------------------
# Metrics per category (agreed in V2 polish step 2.0)
# ---------------------------------------------------------------------------

ALL_METRICS = [
    "faithfulness",
    "answer_relevance",
    "context_precision",
    "context_recall",
    "ground_truth_coverage",
]

# Short column names for the console table
METRIC_SHORT = {
    "faithfulness": "faith",
    "answer_relevance": "relev",
    "context_precision": "prec",
    "context_recall": "recall",
    "ground_truth_coverage": "gt_cover",
}

METRICS_BY_TYPE = {
    "single_factual": ["faithfulness", "answer_relevance", "context_precision",
                       "context_recall", "ground_truth_coverage"],
    # Comparisons: no precision (10 chunks per year/company makes it low by design)
    "cross_year":     ["faithfulness", "answer_relevance", "context_recall", "ground_truth_coverage"],
    "cross_company":  ["faithfulness", "answer_relevance", "context_recall", "ground_truth_coverage"],
    # Vague: no ground truth, so no precision / recall / correctness
    "vague":          ["faithfulness", "answer_relevance"],
}

# These get a yes/no check instead of RAGAS metrics.
CHECK_TYPES = {"should_refuse", "invalid"}

# ---------------------------------------------------------------------------
# Passages shown to the judge: same numbering and labels the answering model saw
# ---------------------------------------------------------------------------

def numbered_context_passages(chunks: list[dict]) -> list[str]:
    """
    One string per chunk, labelled exactly as Synthesizer._build_context labels it:
        [N] Company | Year | Section name
        "chunk text"
    Numbering and order follow the synthesizer, including its grouping by sub-query, so that
    "Passage [2]" in an answer points at the same text for the judge.
    """
    def label(n: int, chunk: dict) -> str:
        return (
            f"[{n}] {chunk.get('company', chunk.get('ticker'))} | "
            f"{chunk.get('year')} | "
            f"{chunk.get('section_name', chunk.get('section'))}\n"
            f"\"{chunk['text'].strip()}\""
        )

    if any(c.get("group") for c in chunks):
        grouped: dict = {}
        for chunk in chunks:
            grouped.setdefault(chunk.get("group") or "", []).append(chunk)
        ordered = [c for group_chunks in grouped.values() for c in group_chunks]
    else:
        ordered = list(chunks)
    return [label(n, c) for n, c in enumerate(ordered, 1)]


def coverage_from_verdicts(verdicts) -> float | None:
    """Ground-truth coverage = ground-truth facts supported by the answer / all ground-truth facts."""
    verdicts = [bool(v) for v in verdicts]
    return round(sum(verdicts) / len(verdicts), 4) if verdicts else None


# ---------------------------------------------------------------------------
# Refusal detection
# ---------------------------------------------------------------------------

_REFUSAL_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(does|do) not (contain|provide|include|have) (enough |sufficient |any |the )?(relevant )?information",
        r"\b(not|no) (enough|sufficient) information",
        r"\b(cannot|can't|can not|unable to|am unable to) (answer|determine|find|provide)",
        r"\bnot (mentioned|discussed|disclosed|addressed|covered|available) in (the )?(provided )?(context|excerpts?|passages?|filings?)",
        r"\b(context|excerpts?|passages?) (does not|do not|doesn't|don't) (mention|discuss|address|cover|include)",
        r"\bno information (about|on|regarding)",
    ]
]

# A refusal followed by a lot of other text may be "refuse, then guess anyway".
# Those are flagged for the manual read.
EXTRA_TEXT_WORDS = 40


def refusal_flags(answer: str) -> dict:
    """exact = the pipeline's own sentence; tolerant = exact or reworded refusal."""
    text = " ".join((answer or "").split())
    exact = REFUSAL_STRING in text
    tolerant = exact or any(p.search(text) for p in _REFUSAL_PATTERNS)
    return {
        "exact": exact,
        "tolerant": tolerant,
        "with_extra_text": tolerant and len(text.split()) > EXTRA_TEXT_WORDS,
    }


def classify_outcome(rejected: bool, answer: str) -> str:
    """rejected = the query parser stopped it; refused = tolerant refusal; else answered."""
    if rejected:
        return "rejected"
    return "refused" if refusal_flags(answer)["tolerant"] else "answered"


def check_passed(query_type: str, outcome: str):
    """Pass/fail for the yes/no categories. None for categories scored by metrics.

    should_refuse: any decline passes (refused by the synthesizer OR rejected by the query
    parser); the outcome label still records which path was taken.
    """
    if query_type == "invalid":
        return outcome == "rejected"
    if query_type == "should_refuse":
        return outcome in ("refused", "rejected")
    return None


# ---------------------------------------------------------------------------
# Token usage (read from Groq's replies, so costs are measured, not guessed)
# ---------------------------------------------------------------------------

def parse_usage(payload: dict):
    """(model, prompt_tokens, completion_tokens) from a chat-completion JSON body, or None."""
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not usage:
        return None
    return (
        payload.get("model", "unknown"),
        int(usage.get("prompt_tokens", 0)),
        int(usage.get("completion_tokens", 0)),
    )


class UsageTracker:
    """Collects one row per Groq call: which query, which step, which model, tokens in/out."""

    def __init__(self, prices: dict | None = None):
        """prices: {model: (usd_per_1M_input_tokens, usd_per_1M_output_tokens)}"""
        self.calls: list[dict] = []
        self.prices = prices or {}
        self.current_qid: str | None = None
        self.current_stage: str | None = None

    def set_query(self, qid: str | None) -> None:
        self.current_qid = qid

    def add(self, model: str, prompt_tokens: int, completion_tokens: int, stage: str | None = None) -> None:
        self.calls.append({
            "query_id": self.current_qid,
            "stage": stage or self.current_stage or "unknown",
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        })

    def _cost(self, row: dict):
        """USD cost of one call, or None if the model has no price entry."""
        price = self.prices.get(row["model"])
        if price is None:
            return None
        return row["prompt_tokens"] * price[0] / 1e6 + row["completion_tokens"] * price[1] / 1e6

    def _sum(self, rows) -> dict:
        rows = list(rows)
        costs = [self._cost(r) for r in rows]
        return {
            "calls": len(rows),
            "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
            "completion_tokens": sum(r["completion_tokens"] for r in rows),
            "cost_usd": round(sum(c for c in costs if c is not None), 6),
            "unpriced_calls": sum(1 for c in costs if c is None),
        }

    def total(self, qid: str | None = None) -> dict:
        return self._sum(r for r in self.calls if qid is None or r["query_id"] == qid)

    def _grouped(self, key: str) -> dict:
        groups = defaultdict(list)
        for r in self.calls:
            groups[r[key]].append(r)
        return {k: self._sum(v) for k, v in sorted(groups.items())}

    def to_dict(self) -> dict:
        return {
            "prices_per_million_tokens": {m: list(p) for m, p in self.prices.items()},
            "total": self.total(),
            "by_model": self._grouped("model"),
            "by_stage": self._grouped("stage"),
            "calls": self.calls,
        }

    def load_calls(self, calls: list[dict]) -> None:
        self.calls = list(calls)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _mean(values):
    return round(sum(values) / len(values), 4) if values else None


def build_summary(records: list[dict]) -> dict:
    """Per-category and overall results. Reports counts and every value, not only means."""
    cats: dict = {}
    for r in records:
        qtype = r["query_type"]
        c = cats.setdefault(qtype, {
            "n": 0, "n_scored": 0, "metrics": {}, "outcomes": defaultdict(int),
            "passed": 0, "checked": 0, "unexpected_rejections": [], "metric_errors": [],
            "pipeline_errors": [],
        })
        c["n"] += 1

        if r.get("status") == "pipeline_error":
            c["pipeline_errors"].append(r["query_id"])
            continue

        if r.get("status") == "unexpected_rejection":
            c["unexpected_rejections"].append(r["query_id"])
            continue

        if qtype in CHECK_TYPES:
            c["outcomes"][r.get("outcome")] += 1
            if r.get("passed") is not None:
                c["checked"] += 1
                c["passed"] += 1 if r["passed"] else 0
            continue

        if r.get("status") == "evaluated":
            c["n_scored"] += 1
            for name, value in (r.get("scores") or {}).items():
                m = c["metrics"].setdefault(name, {"values": {}})
                m["values"][r["query_id"]] = value
            for name, err in (r.get("metric_errors") or {}).items():
                c["metric_errors"].append(f"{r['query_id']}:{name}")

    overall = defaultdict(list)
    for qtype, c in cats.items():
        c["outcomes"] = dict(c["outcomes"])
        for name, m in c["metrics"].items():
            vals = [v for v in m["values"].values() if v is not None]
            m["n"] = len(vals)
            m["mean"] = _mean(vals)
            if qtype in METRICS_BY_TYPE:
                overall[name].extend(vals)

    return {
        "by_category": cats,
        "overall_answer_categories": {name: {"mean": _mean(v), "n": len(v)} for name, v in overall.items()},
    }


def format_summary(summary: dict) -> str:
    """Plain-text table for the console and run.log."""
    lines = []
    lines.append("=" * 86)
    lines.append(f"{'Category':<16}{'n':>3} {'scored':>6}  " +
                 "".join(f"{METRIC_SHORT[m]:>12}" for m in ALL_METRICS))
    lines.append("-" * 86)
    for qtype, c in summary["by_category"].items():
        if qtype in CHECK_TYPES:
            lines.append(f"{qtype:<16}{c['n']:>3}  checked {c['checked']}, passed {c['passed']}, outcomes {c['outcomes']}")
            if c["pipeline_errors"]:
                lines.append(f"   PIPELINE ERRORS (query not evaluated): {c['pipeline_errors']}")
            continue
        cells = []
        for m in ALL_METRICS:
            mean = c["metrics"].get(m, {}).get("mean")
            cells.append(f"{mean:>12.3f}" if mean is not None else f"{'-':>12}")
        lines.append(f"{qtype:<16}{c['n']:>3} {c['n_scored']:>6}  " + "".join(cells))
        if c["unexpected_rejections"]:
            lines.append(f"   unexpected rejections: {c['unexpected_rejections']}")
        if c["metric_errors"]:
            lines.append(f"   metric errors: {c['metric_errors']}")
        if c["pipeline_errors"]:
            lines.append(f"   PIPELINE ERRORS (query not evaluated): {c['pipeline_errors']}")
    lines.append("-" * 86)
    cells = []
    for m in ALL_METRICS:
        mean = summary["overall_answer_categories"].get(m, {}).get("mean")
        cells.append(f"{mean:>12.3f}" if mean is not None else f"{'-':>12}")
    lines.append(f"{'ALL ANSWERED':<16}{'':>3} {'':>6}  " + "".join(cells))
    lines.append("=" * 86)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Git info for the run record
# ---------------------------------------------------------------------------

def git_info() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=15).stdout.strip()
    try:
        return {"commit": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain"))}
    except Exception:
        return {"commit": None, "dirty": None}
