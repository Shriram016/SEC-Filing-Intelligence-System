"""Run the plain-RAG baseline on the dev set and score it (docs/v3/evaluation.md §3).

    # free: build the real prompts and show tokens + cost; no LLM call
    uv run --group embed python -m filing_rag.evaluation.baseline
    # paid (needs approval): a 3-question test, then the full run
    uv run --group embed python -m filing_rag.evaluation.baseline --allow-paid --limit 3
    uv run --group embed python -m filing_rag.evaluation.baseline --allow-paid

Each paid run writes a new folder `experiments/m1/baseline/<time>/` (never overwrites):
results.json, scorecard.md, text_answers_to_mark.md. The run stops when its cost goes above
`baseline_max_cost_usd` (default $2).

`--router` runs the routed pipeline (M2: router → document list → filtered search → checked
answer, Q107);
its runs go to `experiments/m2/smoke/`. `--ids dev_0001,dev_0041` picks questions by ID.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from filing_rag.baseline.pipeline import (
    ANSWER_SCHEMA,
    SYSTEM,
    BaselinePipeline,
    BaselineResult,
    build_prompt,
)
from filing_rag.engine.answer import SYSTEM as WRITER_SYSTEM
from filing_rag.engine.answer import WRITER_SCHEMA
from filing_rag.engine.answer import build_prompt as writer_prompt
from filing_rag.engine.checked import CheckedAnswerer
from filing_rag.engine.routed import RoutedResult
from filing_rag.evaluation.dev_set import DevQuestion, Route
from filing_rag.evaluation.scoring import Mark, score
from filing_rag.llm.client import cost_usd
from filing_rag.router.router import step_rows

EST_OUTPUT_TOKENS = 300  # per question, for the estimate only
EST_CHECKED_OUTPUT_TOKENS = 700  # claims with quotes + calculations (Q107), estimate only
EST_ROUTER_OUTPUT_TOKENS = 400  # JSON + low-effort thinking, for the estimate only
TokenCounter = Callable[[str, str], int]


class AnswerPipeline(Protocol):
    def answer(self, question: str) -> BaselineResult: ...


def answerable(
    questions: Sequence[DevQuestion], limit: int | None = None, ids: Sequence[str] | None = None
) -> list[DevQuestion]:
    qs = [q for q in questions if q.expected_route == Route.ANSWER]
    if ids:
        wanted = set(ids)
        qs = [q for q in qs if q.id in wanted]
    return qs[:limit] if limit else qs


def estimate_router(
    questions: Sequence[DevQuestion],
    build_user: Callable[[str], str],
    system: str,
    count: TokenCounter,
    price_in: float,
    price_out: float,
) -> dict[str, Any]:
    """Router call estimate: real prompt tokens, a fixed output guess."""
    tokens = [count(system, build_user(q.turns[-1])) for q in questions]
    tin, tout = sum(tokens), len(tokens) * EST_ROUTER_OUTPUT_TOKENS
    expected = cost_usd(tin, tout, price_in, price_out)
    return {
        "router_input_tokens_total": tin,
        "router_output_tokens_total_est": tout,
        "router_cost_usd_expected": round(expected, 5),
        "router_cost_usd_worst_case": round(2 * expected, 5),
    }


def rough_tokens(system: str, user: str) -> int:
    """About 4 characters per token, plus the JSON schema. Used when no API key is set."""
    return (len(system) + len(user) + len(json.dumps(ANSWER_SCHEMA))) // 4


def estimate(
    questions: Sequence[DevQuestion],
    pipeline: BaselinePipeline,
    count: TokenCounter,
    price_in: float,
    price_out: float,
    system: str = SYSTEM,
    prompt: Callable[[str, list[Any]], str] = build_prompt,
    out_tokens: int = EST_OUTPUT_TOKENS,
) -> dict[str, Any]:
    """Build the real prompts (search runs, no LLM call) and estimate tokens and cost."""
    tokens = [count(system, prompt(q.turns[-1], pipeline.retrieve(q.turns[-1]))) for q in questions]
    n = len(tokens)
    tin, tout = sum(tokens), n * out_tokens
    expected = cost_usd(tin, tout, price_in, price_out)
    return {
        "questions": n,
        "input_tokens_total": tin,
        "input_tokens_per_question_max": max(tokens, default=0),
        "output_tokens_total_est": tout,
        "cost_usd_expected": round(expected, 4),
        "cost_usd_worst_case": round(2 * expected, 4),  # every question retried once
    }


def _hit_row(h: Any) -> dict[str, Any]:
    return {"doc_name": h.doc_name, "page": h.page, "page_end": h.page_end,
            "score": round(h.score, 4), "is_table": h.payload.get("is_table")}  # fmt: skip


def _routed_fields(r: BaselineResult) -> dict[str, Any]:
    if not isinstance(r, RoutedResult) or r.decision is None:
        return {}
    d = r.decision
    return {
        "route": str(d.route) if d.route else None,
        "router_output": d.output.model_dump(mode="json") if d.output else None,
        "router_error": d.error,
        "doc_names": d.doc_names,
        "steps": step_rows(d),
        "too_many_steps": d.too_many_steps,
        "missing": d.selection.missing if d.selection else [],
        "reply": r.reply,
        "router_llm_calls": len(r.router_calls),
        "router_cost_usd": round(r.router_cost_usd, 6),
        "answer_cost_usd": round(r.answer_cost_usd, 6),
        "router_latency_s": round(r.router_latency_s, 3),
        "added_table_parts": r.added_table_parts,
    } | _checked_fields(r.checked)


def _checked_fields(c: Any) -> dict[str, Any]:
    """Q107: status, claim checks and failure reasons of a checked answer."""
    if c is None:
        return {}
    return {
        "status": str(c.status),
        "claims_total": c.claims_total,
        "claims_passed": c.claims_passed,
        "check_failures": c.failures,
        "model_sentence": c.model_sentence,
        "sentence_used": c.sentence_used,
        "items": [{"id": i.id, "kind": i.kind, "label": i.label, "value": i.value,
                   "unit": i.unit, "failure": str(i.failure) if i.failure else None,
                   "detail": i.detail} for i in c.items],
    }  # fmt: skip


def run(
    questions: Sequence[DevQuestion], pipeline: AnswerPipeline, max_cost_usd: float
) -> tuple[list[dict[str, Any]], bool]:
    """Answer and score each question. Returns (rows, stopped_by_cost_limit)."""
    rows: list[dict[str, Any]] = []
    total = 0.0
    for q in questions:
        if total > max_cost_usd:
            return rows, True
        r = pipeline.answer(q.turns[-1])
        total += r.cost_usd
        s = score(q, r.answer, r.error, r.hits)
        rows.append({
            "id": q.id, "category": str(q.category), "answer_source": str(q.answer_source),
            "question": q.turns[-1], "gold_answer": q.gold_answer,
            "gold_value": q.gold_value, "gold_unit": q.gold_unit,
            "evidence": [e.model_dump() for e in q.evidence],
            "answer": r.answer.model_dump() if r.answer else None, "error": r.error,
            "mark": str(s.mark), "failure_tag": str(s.tag) if s.tag else None,
            "evidence_seen": s.evidence_seen, "sources_ok": s.sources_ok,
            "hits": [_hit_row(h) for h in r.hits],
            "llm_calls": len(r.calls), "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens, "cost_usd": round(r.cost_usd, 6),
            "latency_s": round(r.latency_s, 3),
        } | _routed_fields(r))  # fmt: skip
    return rows, total > max_cost_usd and len(rows) < len(questions)


def _acc(rows: list[dict[str, Any]]) -> str:
    coded = [r for r in rows if r["mark"] != Mark.HAND]
    if not coded:
        return "-"
    ok = sum(1 for r in coded if r["mark"] == Mark.CORRECT)
    return f"{ok}/{len(coded)} ({ok / len(coded):.0%})"


def _retried(row: dict[str, Any]) -> bool:
    """One call per step is normal; more than one in a step is a retry."""
    router_calls = int(row.get("router_llm_calls", 0))
    answer_calls = int(row["llm_calls"]) - router_calls
    return router_calls > 1 or answer_calls > 1


def _rate(rows: list[dict[str, Any]], key: str) -> str:
    if not rows:
        return "-"
    n = sum(1 for r in rows if r[key])
    return f"{n}/{len(rows)} ({n / len(rows):.0%})"


def scorecard(rows: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    router = meta.get("router_model")
    setup = (
        f"router `{router}` + document filter (rule {meta.get('year_rule')})"
        if router
        else "no company filter"
    )
    if meta.get("reranker"):
        setup += f", reranker `{meta['reranker']}` over {meta.get('reranker_candidates')}"
    title = "Routed scorecard" if router else "Baseline scorecard"
    lines = [f"# {title} ({meta['started']})", "",
             f"Model `{meta['model']}`, top-k {meta['top_k']}, collection `{meta['collection']}`, "
             f"{setup}, JSON answers.", "",
             "| Group | Number answers correct (code) | Page in chunks | Correct source cited |",
             "|---|---|---|---|"]  # fmt: skip

    def line(name: str, sub: list[dict[str, Any]]) -> str:
        return (
            f"| {name} | {_acc(sub)} | {_rate(sub, 'evidence_seen')} | {_rate(sub, 'sources_ok')} |"
        )

    lines.append(line("all", rows))
    for key in ("answer_source", "category"):
        for val in sorted({r[key] for r in rows}):
            lines.append(line(f"{key}={val}", [r for r in rows if r[key] == val]))
    tags = Counter(r["failure_tag"] for r in rows if r["failure_tag"])
    hand = sum(1 for r in rows if r["mark"] == Mark.HAND)
    lat = [r["latency_s"] for r in rows] or [0.0]
    lines += ["", "## Failure tags (code-marked wrong answers)", ""]
    lines += [f"- {t}: {n}" for t, n in sorted(tags.items())] or ["- none"]
    lines += ["", f"Hand-marked (see text_answers_to_mark.md): {hand}", "",
              "## Cost and speed", "",
              f"- Total cost: ${sum(r['cost_usd'] for r in rows):.4f}",
              f"- Tokens: {sum(r['input_tokens'] for r in rows)} in, "
              f"{sum(r['output_tokens'] for r in rows)} out",
              f"- Time per question: median {statistics.median(lat):.2f} s, max {max(lat):.2f} s",
              f"- Questions with a JSON retry: {sum(1 for r in rows if _retried(r))}",
              f"- Stopped by the cost limit: {meta['stopped_by_cost_limit']}"]  # fmt: skip
    if router:
        routes = Counter(str(r.get("route")) for r in rows)
        rcost = sum(r.get("router_cost_usd", 0.0) for r in rows)
        rlat = [r.get("router_latency_s", 0.0) for r in rows] or [0.0]
        lines += [f"- Router cost: ${rcost:.5f}; answer cost: "
                  f"${sum(r.get('answer_cost_usd', 0.0) for r in rows):.4f}",
                  f"- Router time: median {statistics.median(rlat):.2f} s",
                  "", "## Routes", ""]  # fmt: skip
        lines += [f"- {k}: {n}" for k, n in sorted(routes.items())]
        lines += ["", "| ID | Route | Steps (company year) | Doc type | Documents searched |",
                  "|---|---|---|---|---|"]  # fmt: skip
        for r in rows:
            o = r.get("router_output") or {}
            docs = r.get("doc_names")
            shown = "all (no filter)" if docs is None else ", ".join(docs) or "-"
            steps = "; ".join(f"{s.get('company') or '-'} {s.get('year') or '-'}"
                              for s in r.get("steps") or [])  # fmt: skip
            doc_type = o.get("doc_type") or ""
            lines.append(f"| {r['id']} | {r.get('route')} | {steps} | {doc_type} | {shown} |")
    checked = [r for r in rows if "status" in r]
    if checked:
        status = Counter(r["status"] for r in checked)
        total = sum(r["claims_total"] for r in checked)
        ok = sum(r["claims_passed"] for r in checked)
        reasons: Counter[str] = Counter()
        for r in checked:
            reasons.update(r["check_failures"])
        why = ", ".join(f"{k} {n}" for k, n in sorted(reasons.items())) or "none"
        lines += ["", "## Checked answers (Q107)", "",
                  "- Status: " + ", ".join(f"{k} {n}" for k, n in sorted(status.items())),
                  f"- Claims passed the quote check: {ok}/{total}"
                  + (f" ({ok / total:.0%})" if total else ""),
                  f"- Failure reasons: {why}"]  # fmt: skip
    lines += ["", "## Per question", "", "| ID | Mark | Tag | Page seen | Value | Gold |",
              "|---|---|---|---|---|---|"]  # fmt: skip
    for r in rows:
        a = r["answer"] or {}
        got = f"{a.get('value')} {a.get('unit') or ''}".strip() if a else "-"
        gold = f"{r['gold_value']} {r['gold_unit']}" if r["gold_value"] is not None else "(hand)"
        lines.append(f"| {r['id']} | {r['mark']} | {r['failure_tag'] or ''} | "
                     f"{'yes' if r['evidence_seen'] else 'no'} | {got} | {gold} |")  # fmt: skip
    return "\n".join(lines) + "\n"


def hand_marking(rows: list[dict[str, Any]]) -> str:
    lines = ["# Answers to mark by hand", "",
             "For each one write: correct / partly correct / wrong.", ""]  # fmt: skip
    for r in rows:
        if r["mark"] != Mark.HAND:
            continue
        a = r["answer"] or {}
        lines += [f"## {r['id']} ({r['category']})", "", f"**Question:** {r['question']}", "",
                  f"**Gold:** {r['gold_answer']}", "",
                  f"**Model:** {a.get('answer', '(no answer: ' + str(r['error']) + ')')}", "",
                  f"Page seen: {'yes' if r['evidence_seen'] else 'no'}. Mark: ______",
                  ""]  # fmt: skip
    return "\n".join(lines)


def write_run(out_root: Path, rows: list[dict[str, Any]], meta: dict[str, Any]) -> Path:
    folder = out_root / str(meta["started"])
    folder.mkdir(parents=True, exist_ok=False)  # never overwrite an earlier run
    (folder / "results.json").write_text(json.dumps({"meta": meta, "questions": rows}, indent=1),
                                         encoding="utf-8")  # fmt: skip
    (folder / "scorecard.md").write_text(scorecard(rows, meta), encoding="utf-8")
    (folder / "text_answers_to_mark.md").write_text(hand_marking(rows), encoding="utf-8")
    return folder


def main(argv: list[str] | None = None) -> int:
    from qdrant_client import QdrantClient

    from filing_rag.config import get_settings
    from filing_rag.evaluation.dev_set import validate_dev_set
    from filing_rag.ingest.embed import BgeEmbedder
    from filing_rag.llm.client import AnthropicLLM
    from filing_rag.llm.fake import FakeLLM
    from filing_rag.search.searcher import Searcher

    ap = argparse.ArgumentParser(prog="filing_rag.evaluation.baseline")
    ap.add_argument("--allow-paid", action="store_true", help="make real (paid) LLM calls")
    ap.add_argument("--limit", type=int, help="only the first N answerable questions")
    ap.add_argument("--max-cost", type=float, help="stop above this cost in USD")
    ap.add_argument("--out-dir", type=Path, help="default: m1/baseline, or m2/smoke with router")
    ap.add_argument("--router", action="store_true", help="routed pipeline (M2)")
    ap.add_argument("--ids", help="comma-separated question IDs, for example dev_0001,dev_0041")
    ap.add_argument(
        "--dev-set",
        choices=["claude", "fb"],
        default="claude",
        help="claude = eval/dev_set.jsonl; fb = the 50 FB-dev questions (Q112)",
    )
    args = ap.parse_args(argv)
    default_out = "experiments/m2/smoke" if args.router else "experiments/m1/baseline"
    if args.dev_set == "fb":
        default_out = "experiments/m3/fb_dev/runs"
    out_dir: Path = args.out_dir or Path(default_out)

    s = get_settings()
    if args.dev_set == "fb":
        from filing_rag.evaluation.fb_dev import load_fb_dev_questions

        pool = load_fb_dev_questions(s)
    else:
        report = validate_dev_set(s.eval_dir / "dev_set.jsonl")
        if report.errors:
            print("dev set has errors:", *report.errors, sep="\n")
            return 1
        pool = report.questions
    ids = [i.strip() for i in args.ids.split(",")] if args.ids else None
    questions = answerable(pool, args.limit, ids)
    if ids and len(questions) != len(ids):
        print(f"some IDs are not answerable dev questions: {ids}")
        return 1
    catalog = None
    if args.router:
        from filing_rag.router.catalog import DocCatalog

        catalog = DocCatalog.from_settings(s)
    embedder = BgeEmbedder(s.embedding_model, s.embedding_query_prefix)
    client = QdrantClient(url=s.qdrant_url, timeout=s.qdrant_timeout_s)
    searcher = Searcher(client, s.qdrant_collection, embedder)

    if not args.allow_paid:
        dry = BaselinePipeline(searcher, FakeLLM(["{}"]), s.baseline_top_k, s.answer_max_tokens)
        count: TokenCounter = rough_tokens
        router_count: TokenCounter = rough_tokens
        how = "rough estimate (4 characters per token; no API key)"
        if s.anthropic_api_key is not None:
            from anthropic import Anthropic

            api = Anthropic(api_key=s.anthropic_api_key.get_secret_value())
            schema = WRITER_SCHEMA if catalog is not None else ANSWER_SCHEMA
            schema_tokens = len(json.dumps(schema)) // 4

            def counter(model: str, extra: int) -> TokenCounter:
                def api_count(system: str, user: str) -> int:
                    msgs: Any = [{"role": "user", "content": user}]
                    n = api.messages.count_tokens(model=model, system=system, messages=msgs)
                    return int(n.input_tokens) + extra

                return api_count

            count = counter(s.answer_model, schema_tokens)
            if catalog is not None:
                from filing_rag.router.router import build_schema

                rschema = len(json.dumps(build_schema(catalog.companies()))) // 4
                router_count = counter(s.router_model, rschema)
            how = "Anthropic token counting endpoint (no answer is generated)"
        # with --router the answer prompt is estimated from unfiltered chunks (same size: top-k);
        # the split-table expansion (up to 3 more chunks) is not in the estimate
        if catalog is not None:
            est = estimate(
                questions, dry, count, s.answer_price_in_per_mtok, s.answer_price_out_per_mtok,
                WRITER_SYSTEM, writer_prompt, EST_CHECKED_OUTPUT_TOKENS,
            )  # fmt: skip
        else:
            est = estimate(
                questions, dry, count, s.answer_price_in_per_mtok, s.answer_price_out_per_mtok
            )
        if catalog is not None:
            from filing_rag.router.router import SYSTEM as ROUTER_SYSTEM
            from filing_rag.router.router import build_user

            names = catalog.companies()
            est |= estimate_router(
                questions,
                lambda q: build_user(q, names),
                ROUTER_SYSTEM,
                router_count,
                s.router_price_in_per_mtok,
                s.router_price_out_per_mtok,
            )
            est["total_cost_usd_expected"] = round(
                est["cost_usd_expected"] + est["router_cost_usd_expected"], 4
            )
            est["total_cost_usd_worst_case"] = round(
                est["cost_usd_worst_case"] + est["router_cost_usd_worst_case"], 4
            )
        print(f"DRY RUN - no LLM call made. Token count: {how}.")
        print(json.dumps(est, indent=1))
        print("To run for real (paid), add --allow-paid (after approval).")
        return 0

    llm = AnthropicLLM(s, allow_paid=True)
    base_pipeline = BaselinePipeline(searcher, llm, s.baseline_top_k, s.answer_max_tokens)
    pipeline: AnswerPipeline = base_pipeline
    if catalog is not None:
        from filing_rag.engine.routed import RoutedPipeline
        from filing_rag.router.router import Router
        from filing_rag.search.reranker import build_searcher

        router_llm = AnthropicLLM(s, allow_paid=True, role="router")
        router = Router(router_llm, catalog, s.router_max_tokens, s.router_year_rule)
        checked = CheckedAnswerer(llm, s.checked_max_tokens)
        routed_searcher = build_searcher(searcher, s.reranker_model, s.reranker_candidates,
                                         max_length=s.reranker_max_length,
                                         batch_size=s.reranker_batch_size)  # fmt: skip
        pipeline = RoutedPipeline(
            router, routed_searcher, checked, s.baseline_top_k, s.table_parts_max_extra
        )
    max_cost = args.max_cost if args.max_cost is not None else s.baseline_max_cost_usd
    started = datetime.now().strftime("%Y%m%d-%H%M%S")
    rows, stopped = run(questions, pipeline, max_cost)
    meta = {"started": started, "dev_set": args.dev_set, "model": s.answer_model,
            "top_k": s.baseline_top_k,
            "collection": s.qdrant_collection, "thinking": s.answer_thinking,
            "max_cost_usd": max_cost, "stopped_by_cost_limit": stopped,
            "questions_run": len(rows), "questions_planned": len(questions)}  # fmt: skip
    if catalog is not None:
        meta |= {"router_model": s.router_model, "router_effort": s.router_effort,
                 "year_rule": s.router_year_rule, "reranker": s.reranker_model or None,
                 "reranker_candidates": s.reranker_candidates}  # fmt: skip
    folder = write_run(out_dir, rows, meta)
    print(f"results: {folder}")
    print(f"number answers correct: {_acc(rows)}; cost ${sum(r['cost_usd'] for r in rows):.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
