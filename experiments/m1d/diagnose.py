"""M1d diagnosis (free): split the search misses into causes.

1. Doc filter run: search only inside the evidence document (an "oracle" filter). If the page
   is found here but not in the company-filter run, the cause is "wrong document" (another
   year or a duplicate filing of the same company).
2. Wrong-document share: in the company-filter run, how many of the top 5 come from another
   document of the same company.
3. Neighbour page: the best rank of a chunk from the evidence document within +-1 page.

Run: uv run --group embed python experiments/m1d/diagnose.py [collection]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qdrant_client import QdrantClient, models

from filing_rag.config import get_settings
from filing_rag.evaluation.dev_set import Route, validate_dev_set
from filing_rag.evaluation.retrieval import page_rank
from filing_rag.ingest.embed import BgeEmbedder

HERE = Path(__file__).parent
K = 10


def main() -> None:
    s = get_settings()
    collection = sys.argv[1] if len(sys.argv) > 1 else s.qdrant_collection
    run = json.loads((HERE / f"search_{collection}_filter.json").read_text(encoding="utf-8"))
    company_rank = {q["id"]: q["rank"] for q in run["questions"]}
    company_top = {q["id"]: q["top"] for q in run["questions"]}
    client = QdrantClient(url=s.qdrant_url, timeout=s.qdrant_timeout_s)
    emb = BgeEmbedder(s.embedding_model, s.embedding_query_prefix)

    from filing_rag.search.searcher import Hit

    rows = []
    for q in validate_dev_set(s.eval_dir / "dev_set.jsonl").questions:
        if q.expected_route != Route.ANSWER:
            continue
        vec = emb.embed_query(q.turns[-1])
        ranks, near = [], []
        for e in q.evidence:
            flt = models.Filter(
                must=[
                    models.FieldCondition(key="doc_name", match=models.MatchValue(value=e.doc_name))
                ]
            )
            pts = client.query_points(collection, query=vec, query_filter=flt, limit=K).points
            hits = [Hit(float(p.score), dict(p.payload or {})) for p in pts]
            ranks.append(page_rank(hits, e.doc_name, e.page))
            nb = [page_rank(hits, e.doc_name, e.page + d) for d in (-1, 1)]
            near.append(min((r for r in nb if r), default=None))
        doc_rank = None if None in ranks else max(r for r in ranks if r)
        gold_docs = {e.doc_name for e in q.evidence}
        other = sum(1 for t in company_top[q.id] if t["doc_name"] not in gold_docs)
        rows.append({"id": q.id, "source": str(q.answer_source), "company_rank": company_rank[q.id],
                     "doc_rank": doc_rank, "near_rank": near, "other_doc_in_top": other,
                     "n_top": len(company_top[q.id])})  # fmt: skip

    def hit5(key: str, sub: list[dict]) -> str:
        n = sum(1 for r in sub if r[key] is not None and r[key] <= 5)
        return f"{n}/{len(sub)}"

    for name, sub in (("all", rows), ("table", [r for r in rows if r["source"] == "table"]),
                      ("text", [r for r in rows if r["source"] == "text"])):  # fmt: skip
        company, doc = hit5("company_rank", sub), hit5("doc_rank", sub)
        print(f"{name}: hit@5 company filter {company}, doc filter {doc}")
    share = sum(r["other_doc_in_top"] for r in rows) / sum(r["n_top"] for r in rows)
    print(f"company run: share of top-5 chunks from another document of the company = {share:.0%}")
    for r in rows:
        if r["company_rank"] is None or r["company_rank"] > 5:
            print(r)
    (HERE / f"diagnose_{collection}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
