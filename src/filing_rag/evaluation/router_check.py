"""Router check (Q109): route, plan steps, document coverage and gold page per question.

Only the router makes an LLM call (Haiku). The search per step is local and free. No writer call.

For each answerable dev question with `gold_steps`:
- route_ok: the route is `expected_route`;
- steps_ok: the set of (company, year) pairs of the router steps = the gold pairs (order and
  search text are not compared: many phrasings are correct);
- docs_ok: every gold evidence document is in the documents of the steps (no filter = ok);
- page_found: a gold evidence page is in the chunks of a step (top k + split-table parts).

Run (dry, free): uv run --group embed python -m filing_rag.evaluation.router_check
Paid (only after approval): add --allow-paid
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from filing_rag.evaluation.dev_set import DevQuestion, Route
from filing_rag.router.router import RouteDecision, Router, Turn, step_rows
from filing_rag.search.searcher import Hit

Retrieve = Callable[[RouteDecision], list[list[Hit]]]  # chunks per step


def history(q: DevQuestion) -> list[Turn]:
    """Earlier turns of a dev question (user turns only)."""
    return [Turn("user", t) for t in q.turns[:-1]]


def _pair_text(p: tuple[str | None, int | None]) -> str:
    return f"{p[0] or '-'} {p[1] if p[1] is not None else '-'}"


def check_one(
    q: DevQuestion, d: RouteDecision, step_hits: Sequence[Sequence[Hit]], latency_s: float = 0.0
) -> dict[str, Any]:
    route = str(d.route) if d.route else None
    answer = d.route is not None and route == Route.ANSWER.value
    got = {(s.company, s.year) for s in d.steps}
    gold = {s.pair for s in q.gold_steps or []}
    row: dict[str, Any] = {
        "id": q.id,
        "category": str(q.category),
        "question": q.turns[-1],
        "expected_route": str(q.expected_route),
        "route": route,
        "route_ok": route == str(q.expected_route),
        "router_error": d.error,
        "router_reason": d.output.reason if d.output else None,
        "doc_type": d.output.doc_type if d.output else None,
        "too_many_steps": d.too_many_steps,
        "steps": step_rows(d),
        "gold_steps": [{"company": c, "year": y} for c, y in sorted(gold, key=_pair_text)],
        "steps_ok": (got == gold) if q.gold_steps is not None else None,
        "missing_pairs": sorted(_pair_text(p) for p in gold - got),
        "extra_pairs": sorted(_pair_text(p) for p in got - gold),
        "docs_ok": None,
        "missing_docs": [],
        "page_found": None,
        "step_pages": [[f"{h.doc_name} p{h.page}" for h in hits] for hits in step_hits],
        "cost_usd": round(d.cost_usd, 6),
        "llm_calls": len(d.calls),
        "latency_s": round(latency_s, 3),
    }
    if answer and q.evidence:
        names = d.doc_names
        missing = [] if names is None else [e.doc_name for e in q.evidence
                                            if e.doc_name not in names]  # fmt: skip
        row["missing_docs"] = sorted(set(missing))
        row["docs_ok"] = not missing
        found = [h for hits in step_hits for h in hits]
        row["page_found"] = any(h.covers(e.doc_name, e.page) for h in found for e in q.evidence)
    elif q.evidence:
        row["docs_ok"] = row["page_found"] = False
    return row


def run_check(
    questions: Sequence[DevQuestion],
    router: Router,
    retrieve: Retrieve,
    max_cost_usd: float,
) -> tuple[list[dict[str, Any]], bool]:
    """Router + search for each question. Stops before a question when the cost limit is hit."""
    rows: list[dict[str, Any]] = []
    spent = 0.0
    for q in questions:
        if spent >= max_cost_usd:
            return rows, True
        t0 = time.monotonic()
        d = router.decide(q.turns[-1], history(q))
        latency = time.monotonic() - t0
        hits = retrieve(d) if d.route is not None and str(d.route) == Route.ANSWER.value else []
        rows.append(check_one(q, d, hits, latency))
        spent += d.cost_usd
    return rows, False


def _rate(rows: Sequence[dict[str, Any]], key: str) -> str:
    vals = [r[key] for r in rows if r[key] is not None]
    if not vals:
        return "-"
    ok = sum(1 for v in vals if v)
    return f"{ok}/{len(vals)} ({ok / len(vals):.0%})"


def summary(rows: Sequence[dict[str, Any]], meta: dict[str, Any]) -> str:
    keys = ["route_ok", "steps_ok", "docs_ok", "page_found"]
    names = {"route_ok": "Route correct", "steps_ok": "Steps = gold steps",
             "docs_ok": "Gold documents in the step documents",
             "page_found": "Gold page in the chunks of a step"}  # fmt: skip
    cost = sum(r["cost_usd"] for r in rows)
    lat = sorted(r["latency_s"] for r in rows) or [0.0]
    lines = [
        "# Router check (Q109)", "",
        f"- Run: {meta.get('started')}; router model: {meta.get('router_model')}; "
        f"collection: {meta.get('collection')}; top k per step: {meta.get('top_k')}",
        f"- Questions: {len(rows)}; cost ${cost:.4f}; "
        f"router time median {lat[len(lat) // 2]:.2f} s",
        f"- Router JSON retries: {sum(1 for r in rows if r['llm_calls'] > 1)}; "
        f"router failures: {sum(1 for r in rows if r['route'] is None)}",
        f"- Stopped by the cost limit: {meta.get('stopped_by_cost_limit')}", "",
        "| Check | All | One gold step | Two or more gold steps |", "|---|---|---|---|",
    ]  # fmt: skip
    one = [r for r in rows if len(r["gold_steps"]) == 1]
    many = [r for r in rows if len(r["gold_steps"]) > 1]
    for k in keys:
        lines.append(f"| {names[k]} | {_rate(rows, k)} | {_rate(one, k)} | {_rate(many, k)} |")
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    lines += ["", "## By category", "", "| Category | Route | Steps | Documents | Page |",
              "|---|---|---|---|---|"]  # fmt: skip
    for cat, rs in sorted(by_cat.items()):
        lines.append(f"| {cat} | " + " | ".join(_rate(rs, k) for k in keys) + " |")
    bad = [r for r in rows if not (r["route_ok"] and r["steps_ok"] is not False
                                   and r["docs_ok"] is not False)]  # fmt: skip
    lines += ["", "## Questions with a wrong route, steps or documents", ""]
    if not bad:
        lines.append("None.")
    else:
        lines += ["| ID | Route | Missing pairs | Extra pairs | Missing documents | Doc type "
                  "| Router reason |", "|---|---|---|---|---|---|---|"]  # fmt: skip
        for r in bad:
            cells = [r["id"], str(r["route"])] + [
                ", ".join(r[k]) for k in ("missing_pairs", "extra_pairs", "missing_docs")
            ] + [str(r.get("doc_type") or ""),
                 str(r.get("router_reason") or "").replace("|", "/")]  # fmt: skip
            lines.append("| " + " | ".join(cells) + " |")
    misses = [r for r in rows if r["page_found"] is False]
    reasons = Counter("route" if not r["route_ok"] else "documents" if r["docs_ok"] is False
                      else "search" for r in misses)  # fmt: skip
    lines += ["", "## Gold page not found", "",
              "- Cause: " + (", ".join(f"{k} {n}" for k, n in sorted(reasons.items())) or "none"),
              "- IDs: " + (", ".join(r["id"] for r in misses) or "none")]  # fmt: skip
    return "\n".join(lines) + "\n"


def write_check(out_root: Path, rows: list[dict[str, Any]], meta: dict[str, Any]) -> Path:
    folder = out_root / str(meta["started"])
    folder.mkdir(parents=True, exist_ok=False)  # never overwrite an earlier run
    (folder / "results.json").write_text(json.dumps({"meta": meta, "questions": rows}, indent=1),
                                         encoding="utf-8")  # fmt: skip
    (folder / "summary.md").write_text(summary(rows, meta), encoding="utf-8")
    return folder


def main(argv: list[str] | None = None) -> int:
    from qdrant_client import QdrantClient

    from filing_rag.config import get_settings
    from filing_rag.engine.routed import RoutedPipeline
    from filing_rag.evaluation.baseline import (
        EST_ROUTER_OUTPUT_TOKENS,
        answerable,
        estimate_router,
        rough_tokens,
    )
    from filing_rag.evaluation.dev_set import validate_dev_set
    from filing_rag.ingest.embed import BgeEmbedder
    from filing_rag.llm.client import AnthropicLLM
    from filing_rag.router.catalog import DocCatalog
    from filing_rag.router.router import SYSTEM, build_schema, build_user
    from filing_rag.search.reranker import build_searcher
    from filing_rag.search.searcher import Searcher

    ap = argparse.ArgumentParser(prog="filing_rag.evaluation.router_check")
    ap.add_argument("--allow-paid", action="store_true", help="make real (paid) router calls")
    ap.add_argument("--ids", help="comma-separated question IDs")
    ap.add_argument("--max-cost", type=float, default=0.10, help="stop above this cost in USD")
    ap.add_argument("--out-dir", type=Path, default=Path("experiments/m3/router_check"))
    args = ap.parse_args(argv)

    s = get_settings()
    report = validate_dev_set(s.eval_dir / "dev_set.jsonl")
    if report.errors:
        print("dev set has errors:", *report.errors, sep="\n")
        return 1
    ids = [i.strip() for i in args.ids.split(",")] if args.ids else None
    questions = [q for q in answerable(report.questions, ids=ids) if q.gold_steps is not None]
    catalog = DocCatalog.from_settings(s)
    names = catalog.companies()

    if not args.allow_paid:
        count = rough_tokens
        how = "rough estimate (4 characters per token; no API key)"
        if s.anthropic_api_key is not None:
            from anthropic import Anthropic

            api = Anthropic(api_key=s.anthropic_api_key.get_secret_value())
            extra = len(json.dumps(build_schema(names))) // 4

            def api_count(system: str, user: str) -> int:
                msgs: Any = [{"role": "user", "content": user}]
                n = api.messages.count_tokens(model=s.router_model, system=system, messages=msgs)
                return int(n.input_tokens) + extra

            count = api_count
            how = "Anthropic token counting endpoint (no answer is generated)"
        est = estimate_router(questions, lambda q: build_user(q, names), SYSTEM, count,
                              s.router_price_in_per_mtok, s.router_price_out_per_mtok)  # fmt: skip
        est |= {"questions": len(questions), "output_tokens_guess_per_question":
                EST_ROUTER_OUTPUT_TOKENS, "max_cost_usd": args.max_cost}  # fmt: skip
        print(f"DRY RUN - no LLM call made. Token count: {how}.")
        print(json.dumps(est, indent=1))
        print("To run for real (paid), add --allow-paid (after approval).")
        return 0

    embedder = BgeEmbedder(s.embedding_model, s.embedding_query_prefix)
    client = QdrantClient(url=s.qdrant_url, timeout=s.qdrant_timeout_s)
    searcher = build_searcher(Searcher(client, s.qdrant_collection, embedder),
                              s.reranker_model, s.reranker_candidates,
                              max_length=s.reranker_max_length,
                              batch_size=s.reranker_batch_size)  # fmt: skip
    router = Router(AnthropicLLM(s, allow_paid=True, role="router"), catalog,
                    s.router_max_tokens, s.router_year_rule)  # fmt: skip
    pipe = RoutedPipeline(router, searcher, _NoAnswer(), s.baseline_top_k,
                          s.table_parts_max_extra)  # fmt: skip
    started = datetime.now().strftime("%Y%m%d-%H%M%S")
    rows, stopped = run_check(questions, router, lambda d: pipe.retrieve_steps(d)[2],
                              args.max_cost)  # fmt: skip
    meta = {"started": started, "router_model": s.router_model, "router_effort": s.router_effort,
            "year_rule": s.router_year_rule, "collection": s.qdrant_collection,
            "top_k": s.baseline_top_k, "reranker": s.reranker_model or None,
            "reranker_candidates": s.reranker_candidates, "max_cost_usd": args.max_cost,
            "stopped_by_cost_limit": stopped, "questions_run": len(rows),
            "questions_planned": len(questions)}  # fmt: skip
    folder = write_check(args.out_dir, rows, meta)
    print(f"results: {folder}")
    print(summary(rows, meta))
    return 0


class _NoAnswer:
    """The router check never calls the writer."""

    def answer(self, question: str, hits: list[Hit], on_progress: Any = None) -> Any:
        raise RuntimeError("the router check makes no answer call")


if __name__ == "__main__":
    sys.exit(main())
