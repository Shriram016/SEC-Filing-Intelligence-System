"""Free search test (Q109): "perfect router" with the gold steps. No LLM call.

Compares, for the 50 answerable dev questions:
- M2: one search over the documents of all steps together (top 5 + table parts);
- Q109: one search per step (top 5 + table parts each), merged.
The search text is the question text in both (the gold steps have no search text), so the test
measures the effect of one filtered search per step only.

Run: uv run --group embed python experiments/m3/router_steps/perfect_steps.py
"""

from __future__ import annotations

import json
from typing import Any

from qdrant_client import QdrantClient

from filing_rag.config import get_settings
from filing_rag.engine.routed import RoutedPipeline
from filing_rag.evaluation.baseline import answerable
from filing_rag.evaluation.dev_set import validate_dev_set
from filing_rag.ingest.embed import BgeEmbedder
from filing_rag.llm.fake import FakeLLM
from filing_rag.router.catalog import DocCatalog
from filing_rag.router.router import RouteDecision, Router
from filing_rag.search.searcher import Hit, Searcher


def gold_decision(router: Router, q: Any) -> RouteDecision:
    steps = [{"company": s.company, "year": s.year, "search": q.turns[-1]} for s in q.gold_steps]
    reply = json.dumps({"route": "answer", "standalone_question": q.turns[-1], "reason": "gold",
                        "steps": steps, "other_companies": [], "doc_type": None,
                        "metric": None})  # fmt: skip
    router.llm = FakeLLM([reply])
    return router.decide(q.turns[-1])


def found(q: Any, hits: list[Hit]) -> bool:
    return any(h.covers(e.doc_name, e.page) for h in hits for e in q.evidence)


def found_all(q: Any, hits: list[Hit]) -> bool:
    return all(any(h.covers(e.doc_name, e.page) for h in hits) for e in q.evidence)


def main() -> None:
    s = get_settings()
    qs = answerable(validate_dev_set(s.eval_dir / "dev_set.jsonl").questions)
    catalog = DocCatalog.from_settings(s)
    searcher = Searcher(QdrantClient(url=s.qdrant_url, timeout=s.qdrant_timeout_s),
                        s.qdrant_collection, BgeEmbedder(s.embedding_model,
                                                         s.embedding_query_prefix))  # fmt: skip
    router = Router(FakeLLM(["{}"]), catalog, year_rule=s.router_year_rule)
    pipe = RoutedPipeline(router, searcher, None, s.baseline_top_k, s.table_parts_max_extra)  # type: ignore[arg-type]
    rows = []
    for q in qs:
        d = gold_decision(router, q)
        one, _ = pipe.retrieve(q.turns[-1], d.doc_names)
        many, _, _ = pipe.retrieve_steps(d)
        rows.append({"id": q.id, "steps": len(d.steps), "route": str(d.route),
                     "m2": found(q, one), "q109": found(q, many),
                     "m2_all": found_all(q, one), "q109_all": found_all(q, many),
                     "m2_chunks": len(one), "q109_chunks": len(many)})  # fmt: skip
    for label, sub in [("all", rows), ("1 step", [r for r in rows if r["steps"] == 1]),
                       ("2+ steps", [r for r in rows if r["steps"] > 1])]:  # fmt: skip
        n = len(sub)
        m2 = sum(r["m2"] for r in sub)
        q109 = sum(r["q109"] for r in sub)
        m2a = sum(r["m2_all"] for r in sub)
        q109a = sum(r["q109_all"] for r in sub)
        c1 = sum(r["m2_chunks"] for r in sub) / max(n, 1)
        c2 = sum(r["q109_chunks"] for r in sub) / max(n, 1)
        print(
            f"{label:9} n={n:2}  any gold page: M2 {m2}/{n}, Q109 {q109}/{n};  "
            f"all gold pages: M2 {m2a}/{n}, Q109 {q109a}/{n};  "
            f"chunks/question M2 {c1:.1f}, Q109 {c2:.1f}"
        )
    for r in rows:
        if r["m2"] != r["q109"] or r["m2_all"] != r["q109_all"] or r["route"] != "answer":
            print(r)


if __name__ == "__main__":
    main()
