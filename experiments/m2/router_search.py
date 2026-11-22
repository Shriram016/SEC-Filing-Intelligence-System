"""M2 step 5: search test with a "perfect router" (free, no LLM). Q104.

Company = from the gold evidence document. Years = 4-digit years (and FY'22 forms) read from the
question text by code (what the router is told to do). Then the catalog chooses the documents
and the search keeps only those documents.

Versions (same 50 dev questions, k = 10):
  nofilter  - whole store (baseline)
  company   - company filter only
  rule_a    - company + year Y, else Y+1 (chosen rule)
  rule_b    - company + always Y and Y+1
  gold_doc  - exact gold document (best possible)

A compare-companies question is searched once per company (same as the M1d test).
"Blocked" = the chosen documents do not include the evidence document, so the page can never
be found.

Run:
    uv run --group embed python experiments/m2/router_search.py
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from filing_rag.config import get_settings
from filing_rag.evaluation.dev_set import DevQuestion, Route, validate_dev_set
from filing_rag.evaluation.retrieval import (
    TOP_SHOWN,
    QuestionResult,
    _summary,
    grouped,
    page_rank,
    render_markdown,
)
from filing_rag.ingest.embed import BgeEmbedder
from filing_rag.router.catalog import DocCatalog
from filing_rag.search.searcher import Hit, Searcher

OUT_DIR = Path("experiments/m2/router_search")
K = 10
YEAR4 = re.compile(r"\b(20[0-3]\d)\b")
FY2 = re.compile(r"\bFY\s?'?(\d{2})\b", re.IGNORECASE)

# version name -> function(company, years, gold_doc) -> doc list or None (no filter)
Chooser = Callable[[str, list[int], str], list[str] | None]


def years_in(text: str) -> list[int]:
    found = [int(y) for y in YEAR4.findall(text)]
    found += [2000 + int(y) for y in FY2.findall(text)]
    return sorted(set(found))


def run_version(
    name: str,
    questions: list[DevQuestion],
    searcher: Searcher,
    catalog_company: dict[str, str],
    chooser: Chooser | None,
) -> tuple[list[QuestionResult], list[dict[str, Any]]]:
    results: list[QuestionResult] = []
    details: list[dict[str, Any]] = []
    for q in questions:
        query = q.turns[-1]
        years = years_in(query)
        ranks: list[int | None] = []
        top: list[dict[str, Any]] = []
        chosen_all: dict[str, list[str] | None] = {}
        blocked: list[str] = []
        cache: dict[tuple[str, ...] | None, list[Hit]] = {}
        for e in q.evidence:
            company = catalog_company[e.doc_name]
            docs = None if chooser is None else chooser(company, years, e.doc_name)
            chosen_all[e.doc_name] = docs
            if docs is not None and e.doc_name not in docs:
                blocked.append(e.doc_name)
            key = None if docs is None else tuple(docs)
            if key not in cache:
                cache[key] = searcher.search(query, k=K, doc_names=docs) if docs != [] else []
                top += [_summary(h) for h in cache[key][:TOP_SHOWN]]
            ranks.append(page_rank(cache[key], e.doc_name, e.page))
        results.append(
            QuestionResult(
                id=q.id,
                category=str(q.category),
                answer_source=str(q.answer_source) if q.answer_source else "",
                question=query,
                evidence=[e.model_dump() for e in q.evidence],
                ranks=ranks,
                top=top,
            )
        )
        details.append({"id": q.id, "years": years, "chosen": chosen_all, "blocked": blocked})
    return results, details


def main() -> int:
    s = get_settings()
    report = validate_dev_set(s.eval_dir / "dev_set.jsonl")
    if report.errors:
        print("dev set has errors:", *report.errors, sep="\n")
        return 1
    questions = [q for q in report.questions if q.expected_route == Route.ANSWER and q.evidence]
    catalog = DocCatalog.from_settings(s)
    company_of = {d.doc_name: d.company for d in catalog.docs}

    if OUT_DIR.exists():
        print(f"{OUT_DIR} exists; remove it or rename it first (no overwrite)")
        return 1
    OUT_DIR.mkdir(parents=True)

    embedder = BgeEmbedder(s.embedding_model, s.embedding_query_prefix)
    client = QdrantClient(url=s.qdrant_url, timeout=s.qdrant_timeout_s)
    searcher = Searcher(client, s.qdrant_collection, embedder)

    def by_company(company: str, years: list[int], gold: str) -> list[str] | None:
        return catalog.select([company]).doc_names

    def rule(r: str) -> Chooser:
        def choose(company: str, years: list[int], gold: str) -> list[str] | None:
            return catalog.select([company], years, rule=r).doc_names  # type: ignore[arg-type]

        return choose

    versions: list[tuple[str, Chooser | None]] = [
        ("nofilter", None),
        ("company", by_company),
        ("rule_a", rule("A")),
        ("rule_b", rule("B")),
        ("gold_doc", lambda c, y, gold: [gold]),
    ]
    summary: dict[str, Any] = {}
    for name, chooser in versions:
        results, details = run_version(name, questions, searcher, company_of, chooser)
        scores = grouped(results, K)
        blocked = [d for d in details if d["blocked"]]
        summary[name] = {"scores": scores["all"], "blocked": [d["id"] for d in blocked]}
        payload = {
            "version": name,
            "k": K,
            "scores": scores,
            "questions": [
                asdict(r) | {"rank": r.rank} | d for r, d in zip(results, details, strict=True)
            ],
        }
        (OUT_DIR / f"{name}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        title = f"M2 router search test: {name}"
        (OUT_DIR / f"{name}.md").write_text(render_markdown(title, scores, results), "utf-8")
        print(name, json.dumps(scores["all"]), "blocked:", len(blocked))
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
