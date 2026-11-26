"""Free search test (Q111): reranker vs no reranker. No LLM call.

Uses the real router plans of the Q110 router check (steps with search text + documents), so
the search is the same as in the engine. One step → the question text is searched (the engine
uses `standalone_question`, which the router check does not save; for a first-turn question it
is the question). 2+ steps → each step's search text.

Per configuration and question:
- page@5: a gold page is in the final chunks (top 5 per step + split-table parts, merged);
- all@5: every gold page is in the final chunks;
- pool: a gold page is in the candidates (the ceiling a reranker can reach).
Time: reranker seconds per step (GPU).

Run: uv run --group embed python experiments/m3/reranker/search_test.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from statistics import median
from typing import Any

from qdrant_client import QdrantClient

from filing_rag.config import get_settings
from filing_rag.engine.tables import chunk_key, expand_tables
from filing_rag.evaluation.baseline import answerable
from filing_rag.evaluation.dev_set import validate_dev_set
from filing_rag.ingest.embed import BgeEmbedder
from filing_rag.search.reranker import CrossEncoderReranker, RerankingSearcher
from filing_rag.search.searcher import Hit, Searcher

PLANS = Path("experiments/m3/router_check/20261126-103711/results.json")
OUT = Path("experiments/m3/reranker")
MODELS = ["BAAI/bge-reranker-base", "BAAI/bge-reranker-v2-m3"]
POOLS = [20, 50, 100]
TOP_K = 5


def covers(q: Any, hits: list[Hit]) -> tuple[bool, bool]:
    any_ = any(h.covers(e.doc_name, e.page) for h in hits for e in q.evidence)
    all_ = all(any(h.covers(e.doc_name, e.page) for h in hits) for e in q.evidence)
    return any_, all_


def run(q: Any, steps: list[tuple[str, list[str] | None]], searcher: Any, max_extra: int,
        pool_k: int | None) -> dict[str, Any]:  # fmt: skip
    merged: list[Hit] = []
    pool_hits: list[Hit] = []
    seen: set[str] = set()
    for query, docs in steps:
        hits = searcher.search(query, k=TOP_K, doc_names=docs)
        if pool_k:
            pool_hits += searcher.searcher.search(query, k=pool_k, doc_names=docs)
        hits, _ = expand_tables(hits, searcher, max_extra)
        for h in hits:
            if chunk_key(h) not in seen:
                seen.add(chunk_key(h))
                merged.append(h)
    page, all_ = covers(q, merged)
    return {"page": page, "all": all_, "pool": covers(q, pool_hits)[0] if pool_k else None,
            "chunks": len(merged)}  # fmt: skip


def main() -> int:
    s = get_settings()
    qs = {q.id: q for q in answerable(validate_dev_set(s.eval_dir / "dev_set.jsonl").questions)}
    plans = {r["id"]: r for r in json.loads(PLANS.read_text(encoding="utf-8"))["questions"]}
    base = Searcher(QdrantClient(url=s.qdrant_url, timeout=s.qdrant_timeout_s),
                    s.qdrant_collection, BgeEmbedder(s.embedding_model,
                                                     s.embedding_query_prefix))  # fmt: skip
    items = []
    for qid, q in qs.items():
        st = plans[qid]["steps"]
        steps = ([(q.turns[-1], st[0]["doc_names"])] if len(st) == 1
                 else [(x["search"], x["doc_names"]) for x in st])  # fmt: skip
        items.append((q, steps))

    results: dict[str, dict[str, Any]] = {}

    class Plain:  # the plain searcher with the same `.searcher` attribute as the wrapper
        searcher = base

        def search(self, *a: Any, **kw: Any) -> list[Hit]:
            return base.search(*a, **kw)

        def table_parts(self, table_id: str) -> list[Hit]:
            return base.table_parts(table_id)

    t0 = time.perf_counter()
    results["none"] = {q.id: run(q, st, Plain(), s.table_parts_max_extra, 100) for q, st in items}
    results["none"]["_seconds"] = {"search_total": round(time.perf_counter() - t0, 1)}
    for model in MODELS:
        rr = CrossEncoderReranker(model, max_length=s.reranker_max_length,
                                  batch_size=s.reranker_batch_size)  # fmt: skip
        RerankingSearcher(base, rr, 5).search("warm up", k=1)  # load kernels before timing
        for pool in POOLS:
            name = f"{model.split('/')[-1]}@{pool}"
            wrapped = RerankingSearcher(base, rr, pool)
            rows = {q.id: run(q, st, wrapped, s.table_parts_max_extra, None) for q, st in items}
            secs = wrapped.stats.seconds
            rows["_seconds"] = {"per_step_median": round(median(secs), 3),
                                "per_step_max": round(max(secs), 3)}  # fmt: skip
            results[name] = rows
            print(name, "done", rows["_seconds"], flush=True)
        del rr

    ids = [q.id for q, _ in items]
    lines = ["| Config | Gold page in chunks | All gold pages | Rerank s/step (median, max) |",
             "|---|---|---|---|"]  # fmt: skip
    for name, rows in results.items():
        n = len(ids)
        page = sum(rows[i]["page"] for i in ids)
        all_ = sum(rows[i]["all"] for i in ids)
        t = rows["_seconds"]
        tt = f"{t['per_step_median']}, {t['per_step_max']}" if "per_step_median" in t else "-"
        lines.append(f"| {name} | {page}/{n} | {all_}/{n} | {tt} |")
    pool = sum(bool(results["none"][i]["pool"]) for i in ids)
    lines.append("")
    lines.append(f"Ceiling: a gold page is in the top 100 vector candidates for {pool}/{len(ids)}.")
    lines.append("")
    lines.append("Per question (1 = gold page in chunks):")
    lines.append("")
    names = list(results)
    lines.append("| ID | " + " | ".join(names) + " |")
    lines.append("|---|" + "---|" * len(names))
    for i in ids:
        cells = [str(int(results[n][i]["page"])) for n in names]
        if len(set(cells)) > 1:
            lines.append(f"| {i} | " + " | ".join(cells) + " |")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "search_test.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    (OUT / "search_test.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
