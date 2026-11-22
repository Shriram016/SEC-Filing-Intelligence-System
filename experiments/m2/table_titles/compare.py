"""Q105 search test: table title in the embedded text (free, no LLM).

Same 50 dev questions, k = 10, "perfect router" (company from the gold document, years read
from the question by code), as in experiments/m2/router_search.py. New in this test:

- value check: the gold number is in a top-k chunk on the evidence page (find-number
  questions; a question whose number is not printed on its page in this collection is left out
  and listed);
- split-table expansion: how many chunks and characters the expansion adds to the top 5
  (max 3 chunks per question).

Versions: gold_doc (exact gold document; works on a small test collection) and rule_a (the
production document choice; needs a collection with all documents).

Run (one collection per run, the output folder must not exist):
    uv run --group embed python experiments/m2/table_titles/compare.py \
        --collection chunks --out old_chunks
    FILING_RAG_INGEST_DIR_NAME=v3_t105 uv run --group embed python \
        experiments/m2/table_titles/compare.py --collection chunks_t105 --out small_titles \
        --versions gold_doc
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from filing_rag.config import get_settings
from filing_rag.engine.tables import expand_tables
from filing_rag.evaluation.dev_set import Route, validate_dev_set
from filing_rag.evaluation.retrieval import (
    TOP_SHOWN,
    QuestionResult,
    _summary,
    checkable,
    grouped,
    has_number,
    number_patterns,
    number_rank,
    page_rank,
    render_markdown,
)
from filing_rag.ingest.embed import BgeEmbedder
from filing_rag.router.catalog import DocCatalog
from filing_rag.search.searcher import Hit, Searcher

BASE = Path("experiments/m2/table_titles")
K = 10
TOP = 5
MAX_EXTRA = 3
YEAR4 = re.compile(r"\b(20[0-3]\d)\b")
FY2 = re.compile(r"\bFY\s?'?(\d{2})\b", re.IGNORECASE)


def years_in(text: str) -> list[int]:
    found = [int(y) for y in YEAR4.findall(text)]
    found += [2000 + int(y) for y in FY2.findall(text)]
    return sorted(set(found))


def page_texts(client: QdrantClient, collection: str, doc: str, page: int) -> list[str]:
    flt = models.Filter(
        must=[models.FieldCondition(key="doc_name", match=models.MatchValue(value=doc))]
    )
    points, _ = client.scroll(collection, scroll_filter=flt, limit=10_000, with_payload=True)
    out = []
    for p in points:
        pl = p.payload or {}
        if int(pl["page"]) <= page <= int(pl.get("page_end") or pl["page"]):
            out.append(str(pl.get("text", "")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True)
    ap.add_argument("--out", required=True, help="folder name under experiments/m2/table_titles")
    ap.add_argument("--versions", default="gold_doc,rule_a")
    args = ap.parse_args()
    versions = args.versions.split(",")

    s = get_settings()
    out_dir = BASE / args.out
    if out_dir.exists():
        print(f"{out_dir} exists; choose another --out (no overwrite)")
        return 1
    report = validate_dev_set(s.eval_dir / "dev_set.jsonl")
    if report.errors:
        print("dev set has errors:", *report.errors, sep="\n")
        return 1
    questions = [q for q in report.questions if q.expected_route == Route.ANSWER and q.evidence]
    catalog = DocCatalog.load(Path("data/v3/catalog.json"))  # full catalog: document choice only
    company_of = {d.doc_name: d.company for d in catalog.docs}

    client = QdrantClient(url=s.qdrant_url, timeout=s.qdrant_timeout_s)
    searcher = Searcher(
        client, args.collection, BgeEmbedder(s.embedding_model, s.embedding_query_prefix)
    )

    # Is the gold number printed on the evidence page in this collection?
    printed: dict[str, bool] = {}
    for q in questions:
        if checkable(q) and q.gold_value is not None:
            pats = number_patterns(q.gold_value)
            printed[q.id] = all(
                any(
                    has_number(t, pats)
                    for t in page_texts(client, args.collection, e.doc_name, e.page)
                )
                for e in q.evidence
            )
    out_dir.mkdir(parents=True)
    summary: dict[str, Any] = {
        "collection": args.collection,
        "number_not_printed": sorted(k for k, v in printed.items() if not v),
    }

    for name in versions:
        results: list[QuestionResult] = []
        rows: list[dict[str, Any]] = []
        for q in questions:
            query = q.turns[-1]
            years = years_in(query)
            check = printed.get(q.id, False)
            pats = number_patterns(q.gold_value) if check and q.gold_value is not None else None
            ranks: list[int | None] = []
            vranks: list[int | None] = []
            top: list[dict[str, Any]] = []
            added_n = added_chars = top_chars = 0
            cache: dict[tuple[str, ...], list[Hit]] = {}
            for e in q.evidence:
                if name == "gold_doc":
                    docs = [e.doc_name]
                else:
                    docs = catalog.select([company_of[e.doc_name]], years).doc_names or []
                key = tuple(docs)
                if key not in cache:
                    hits = searcher.search(query, k=K, doc_names=docs) if docs else []
                    cache[key] = hits
                    top += [_summary(h) for h in hits[:TOP_SHOWN]]
                    expanded, n = expand_tables(hits[:TOP], searcher, MAX_EXTRA)
                    added_n += n
                    top_chars += sum(len(str(h.payload.get("text", ""))) for h in hits[:TOP])
                    added_chars += sum(
                        len(str(h.payload.get("text", "")))
                        for h in expanded
                        if h.payload.get("added_table_part")
                    )
                hits = cache[key]
                ranks.append(page_rank(hits, e.doc_name, e.page))
                if pats is not None:
                    vranks.append(number_rank(hits, e.doc_name, e.page, pats))
            results.append(
                QuestionResult(
                    id=q.id,
                    category=str(q.category),
                    answer_source=str(q.answer_source) if q.answer_source else "",
                    question=query,
                    evidence=[e.model_dump() for e in q.evidence],
                    ranks=ranks,
                    top=top,
                    value_ranks=vranks if pats is not None else None,
                )
            )
            rows.append({"id": q.id, "added_parts": added_n, "added_chars": added_chars,
                         "top5_chars": top_chars})  # fmt: skip
        scores = grouped(results, K)
        expansion = {
            "questions_with_added_parts": sum(1 for r in rows if r["added_parts"]),
            "added_parts": sum(r["added_parts"] for r in rows),
            "added_chars": sum(r["added_chars"] for r in rows),
            "top5_chars": sum(r["top5_chars"] for r in rows),
        }
        summary[name] = {"scores": scores, "expansion": expansion}
        payload = {
            "version": name, "collection": args.collection, "k": K, "scores": scores,
            "expansion": expansion,
            "questions": [asdict(r) | {"rank": r.rank, "value_rank": r.value_rank} | row
                          for r, row in zip(results, rows, strict=True)],
        }  # fmt: skip
        (out_dir / f"{name}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        title = f"Q105 search test: {args.collection}, {name}"
        (out_dir / f"{name}.md").write_text(render_markdown(title, scores, results), "utf-8")
        a = scores["all"]
        src = scores["answer_source"]
        print(name, json.dumps(a))
        print("  table", json.dumps(src.get("table")), "\n  text", json.dumps(src.get("text")))
        print("  expansion", json.dumps(expansion))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("number not printed on page:", summary["number_not_printed"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
