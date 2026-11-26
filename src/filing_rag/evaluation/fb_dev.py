"""FB-dev 50 as dev questions (Q112, docs/v3/evaluation.md §2).

The 50 open FinanceBench questions are built on the fly from `data/fb_dev/fb_dev_50.jsonl`
(`load_fb_dev`), so there is no second copy to keep in sync, and nothing from FinanceBench goes
into git (licence: do not redistribute).

- ID `fb_<5 digits>` from `financebench_id`; category = the FinanceBench question type.
- Evidence pages: FinanceBench `evidence_page_num` is a 0-based page index (checked on all 62
  FB-dev evidence pages, `experiments/m3/fb_dev/page_base.py`), so the viewer page is num + 1.
- `gold_value` / `gold_unit` only when the gold answer is one plain number (most metrics
  questions); every other answer is marked by the judge or by hand.
"""

from __future__ import annotations

import re
from typing import Any

from filing_rag.config import Settings
from filing_rag.evaluation.dev_set import Category, DevQuestion, Evidence, Route, Status
from filing_rag.evaluation.locked import load_fb_dev

CATEGORY = {
    "metrics-generated": Category.FB_METRICS,
    "domain-relevant": Category.FB_DOMAIN,
    "novel-generated": Category.FB_NOVEL,
}
PAGE_BASE = 0  # FinanceBench evidence_page_num is 0-based
_NUMBER_RE = re.compile(r"^\(?(-)?\$?\s*(-)?([\d,]*\.?\d+)\)?\s*(%)?$")
_SCALE_RE = re.compile(r"\b(?:usd|us\s*\$|\$)\s*(thousand|million|billion)s?\b", re.IGNORECASE)


def fb_id(financebench_id: str) -> str:
    m = re.search(r"(\d+)$", financebench_id)
    if not m:
        raise ValueError(f"no number in {financebench_id!r}")
    return f"fb_{int(m.group(1)):05d}"


def parse_gold(answer: str, question: str) -> tuple[float | None, str | None]:
    """One plain number → (value, unit). "$1577.00" + "in USD millions" → (1577.0, "USD
    million"); "2.8%" → (2.8, "%"); "0.83" → (0.83, "ratio"). Anything else → (None, None)."""
    m = _NUMBER_RE.match(answer.strip())
    if not m:
        return None, None
    value = float(m.group(3).replace(",", ""))
    if m.group(1) or m.group(2) or answer.strip().startswith("("):
        value = -value
    if m.group(4):
        return value, "%"
    if "$" in answer:
        scale = _SCALE_RE.search(question)
        return value, f"USD {scale.group(1).lower()}" if scale else "USD"
    return value, "ratio"


def to_dev_question(row: dict[str, Any]) -> DevQuestion:
    pages: list[Evidence] = []
    for ev in row.get("evidence") or []:
        e = Evidence(
            doc_name=str(ev["doc_name"]), page=int(ev["evidence_page_num"]) + 1 - PAGE_BASE
        )
        if e not in pages:
            pages.append(e)
    qtype = str(row["question_type"])
    value, unit = parse_gold(str(row["answer"]), str(row["question"]))
    if qtype != "metrics-generated":
        value, unit = None, None  # a number inside a judgement answer is not the whole answer
    notes = f"reasoning: {row.get('question_reasoning')}; justification: {row.get('justification')}"
    return DevQuestion(
        id=fb_id(str(row["financebench_id"])),
        source="financebench",
        category=CATEGORY[qtype],
        turns=[str(row["question"])],
        expected_route=Route.ANSWER,
        gold_answer=str(row["answer"]),
        evidence=pages,
        gold_value=value,
        gold_unit=unit,
        status=Status.CONFIRMED,  # human-written benchmark answers
        notes=notes,
    )


def load_fb_dev_questions(settings: Settings) -> list[DevQuestion]:
    """The 50 FB-dev questions in the dev format, sorted by ID."""
    return sorted((to_dev_question(r) for r in load_fb_dev(settings)), key=lambda q: q.id)
