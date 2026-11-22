"""M1d search test (docs/v3/evaluation.md): does the search find the evidence page? Free.

For each answerable dev question, the search returns the top-k chunks. A chunk is a hit when
it comes from the evidence document and spans the evidence page. Scores: Hit@1/5/10, MRR@k,
for all questions and split by answer_source (table / text) and by category.

Company filter (Q100): with `use_filter`, the company is a hard filter and the question is
searched once per evidence company (a compare-companies question needs both pages). Without
it, one search over the whole store.

Shortcut (flagged): the router is not built yet, so the company comes from the evidence
document. This is the score with a perfect router (best case for this step).

Run:
    uv run --group embed python -m filing_rag.evaluation.retrieval --collection chunks
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from filing_rag.evaluation.dev_set import Category, DevQuestion, Route
from filing_rag.search.searcher import Hit

KS = (1, 5, 10)
TOP_SHOWN = 5


class SearchFn(Protocol):
    def search(self, query: str, company: str | None = None, k: int = 10) -> list[Hit]: ...


@dataclass
class QuestionResult:
    id: str
    category: str
    answer_source: str
    question: str
    evidence: list[dict[str, Any]]
    ranks: list[int | None]  # rank of each evidence page (1 = top), None = not found
    top: list[dict[str, Any]] = field(default_factory=list)
    # Chunk-level check (Q105): rank of the first chunk on the evidence page whose text holds
    # the gold number. None = the question is not checked (see `number_patterns`).
    value_ranks: list[int | None] | None = None

    @property
    def rank(self) -> int | None:
        """All evidence pages must be found; the question's rank is the worst one."""
        return _worst(self.ranks)

    @property
    def value_rank(self) -> int | None:
        return _worst(self.value_ranks or [])


def _worst(ranks: list[int | None]) -> int | None:
    if not ranks or any(r is None for r in ranks):
        return None
    return max(r for r in ranks if r is not None)


def page_rank(hits: list[Hit], doc_name: str, page: int) -> int | None:
    for i, h in enumerate(hits, start=1):
        if h.covers(doc_name, page):
            return i
    return None


# ---------- chunk-level check: is the gold number in the retrieved chunk? (Q105) ----------

_SCALES = ((1e9, "billion"), (1e6, "million"))


def _num_forms(x: float) -> set[str]:
    """How a number can be printed: 1788 -> {"1,788", "1788"}; 15.48 -> {"15.48"}."""
    x = abs(x)
    if float(x).is_integer():
        n = int(x)
        return {f"{n:,}", str(n)} | ({f"{n}.0"} if n < 1000 else set())
    text = f"{x:.6f}".rstrip("0").rstrip(".")
    whole, _, frac = text.partition(".")
    return {text, f"{int(whole):,}.{frac}"}


def number_patterns(value: float) -> list[re.Pattern[str]]:
    """Patterns that find `value` as printed in a filing.

    The plain forms ("1,788", "15.48") must not be part of a longer number. Large values also
    match the short forms ("850 million", "3 billion"). A negative value matches its absolute
    value, because tables print a decrease as "(1,234)"."""
    edge_l, edge_r = r"(?<![\d.,])", r"(?![\d]|[.,]\d)"
    forms = _num_forms(value)
    out = [re.compile(edge_l + re.escape(f) + edge_r) for f in sorted(forms)]
    for scale, word in _SCALES:
        if abs(value) >= scale:
            for f in sorted(_num_forms(abs(value) / scale)):
                out.append(re.compile(edge_l + re.escape(f) + r"\s*" + word, re.IGNORECASE))
    return out


def checkable(q: DevQuestion) -> bool:
    """Only find-number questions: their gold number is printed on the evidence page. For
    calculate / compare questions the gold value is computed, so it is not in the text."""
    return q.category == Category.FIND_NUMBER and q.gold_value is not None


def number_rank(
    hits: list[Hit], doc_name: str, page: int, patterns: list[re.Pattern[str]]
) -> int | None:
    """Rank of the first chunk that spans the evidence page and holds the gold number."""
    for i, h in enumerate(hits, start=1):
        if h.covers(doc_name, page) and has_number(str(h.payload.get("text", "")), patterns):
            return i
    return None


def has_number(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def _summary(h: Hit) -> dict[str, Any]:
    p = h.payload
    return {
        "score": round(h.score, 4),
        "doc_name": h.doc_name,
        "page": h.page,
        "page_end": h.page_end,
        "is_table": p.get("is_table"),
        "section": p.get("section"),
        "text": str(p.get("text", ""))[:200],
    }


def evaluate(
    questions: Iterable[DevQuestion],
    searcher: SearchFn,
    company_of: Callable[[str], str],
    use_filter: bool = True,
    k: int = 10,
) -> list[QuestionResult]:
    results: list[QuestionResult] = []
    for q in questions:
        if q.expected_route != Route.ANSWER or not q.evidence:
            continue
        query = q.turns[-1]
        ranks: list[int | None] = []
        top: list[dict[str, Any]] = []
        gold = q.gold_value
        patterns = number_patterns(gold) if checkable(q) and gold is not None else None
        value_ranks: list[int | None] | None = None if patterns is None else []
        if use_filter:
            cache: dict[str, list[Hit]] = {}
            for e in q.evidence:
                company = company_of(e.doc_name)
                if company not in cache:
                    cache[company] = searcher.search(query, company=company, k=k)
                    top += [_summary(h) for h in cache[company][:TOP_SHOWN]]
                ranks.append(page_rank(cache[company], e.doc_name, e.page))
                if patterns is not None and value_ranks is not None:
                    value_ranks.append(number_rank(cache[company], e.doc_name, e.page, patterns))
        else:
            hits = searcher.search(query, company=None, k=k)
            top = [_summary(h) for h in hits[:TOP_SHOWN]]
            ranks = [page_rank(hits, e.doc_name, e.page) for e in q.evidence]
            if patterns is not None:
                value_ranks = [number_rank(hits, e.doc_name, e.page, patterns) for e in q.evidence]
        results.append(
            QuestionResult(
                id=q.id,
                category=str(q.category),
                answer_source=str(q.answer_source) if q.answer_source else "",
                question=query,
                evidence=[e.model_dump() for e in q.evidence],
                ranks=ranks,
                top=top,
                value_ranks=value_ranks,
            )
        )
    return results


def metrics(results: list[QuestionResult], k: int = 10) -> dict[str, float | int]:
    """Page scores for all questions; `value_*` = the chunk-level check, only over the
    questions it applies to (`value_n`)."""
    n = len(results)
    out: dict[str, float | int] = {"n": n}
    if n == 0:
        return out
    ranks = [r.rank for r in results]
    for kk in KS:
        if kk <= k:
            out[f"hit@{kk}"] = round(sum(1 for r in ranks if r is not None and r <= kk) / n, 3)
    out[f"mrr@{k}"] = round(sum(1 / r for r in ranks if r is not None and r <= k) / n, 3)
    checked = [r.value_rank for r in results if r.value_ranks is not None]
    if checked:
        out["value_n"] = len(checked)
        for kk in KS:
            if kk <= k:
                hits = sum(1 for r in checked if r is not None and r <= kk)
                out[f"value_hit@{kk}"] = round(hits / len(checked), 3)
    return out


def grouped(results: list[QuestionResult], k: int = 10) -> dict[str, dict[str, Any]]:
    """Scores for all questions, per answer_source and per category."""
    out: dict[str, dict[str, Any]] = {"all": metrics(results, k)}
    for attr in ("answer_source", "category"):
        keys = sorted({getattr(r, attr) for r in results})
        out[attr] = {
            key: metrics([r for r in results if getattr(r, attr) == key], k) for key in keys
        }
    return out


def render_markdown(title: str, scores: Mapping[str, Any], results: list[QuestionResult]) -> str:
    def row(name: str, m: Mapping[str, Any]) -> str:
        cols = [str(m.get(c, "")) for c in ("n", "hit@1", "hit@5", "hit@10")]
        mrr = next((v for key, v in m.items() if key.startswith("mrr@")), "")
        value = [str(m.get(c, "")) for c in ("value_n", "value_hit@5", "value_hit@10")]
        return f"| {name} | " + " | ".join([*cols, str(mrr), *value]) + " |"

    lines = [
        f"# {title}",
        "",
        "Value columns: the gold number is in a top-k chunk on the evidence page "
        "(find-number questions only).",
        "",
        "| Group | n | Hit@1 | Hit@5 | Hit@10 | MRR | Value n | Value@5 | Value@10 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    lines.append(row("all", scores["all"]))
    for attr in ("answer_source", "category"):
        for key, m in scores[attr].items():
            lines.append(row(f"{attr}={key}", m))
    lines += [
        "",
        "| ID | Category | Source | Rank | Value rank | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        ev = "; ".join(f"{e['doc_name']} p{e['page']}" for e in r.evidence)
        rank = "-" if r.rank is None else str(r.rank)
        if r.value_ranks is None:
            vrank = "n/a"
        else:
            vrank = "-" if r.value_rank is None else str(r.value_rank)
        lines.append(f"| {r.id} | {r.category} | {r.answer_source} | {rank} | {vrank} | {ev} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from qdrant_client import QdrantClient

    from filing_rag.config import get_settings
    from filing_rag.evaluation.dev_set import validate_dev_set
    from filing_rag.ingest.catalog import load_document_list
    from filing_rag.ingest.embed import BgeEmbedder
    from filing_rag.search.searcher import Searcher

    ap = argparse.ArgumentParser(prog="filing_rag.evaluation.retrieval")
    ap.add_argument("--collection", help="Qdrant collection (default: from settings)")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--out-dir", type=Path, default=Path("experiments/m1d"))
    ap.add_argument("--overwrite", action="store_true", help="replace earlier result files")
    args = ap.parse_args(argv)

    s = get_settings()
    collection = args.collection or s.qdrant_collection
    report = validate_dev_set(s.eval_dir / "dev_set.jsonl")
    if report.errors:
        print("dev set has errors:", *report.errors, sep="\n")
        return 1
    docs = load_document_list(s)
    embedder = BgeEmbedder(s.embedding_model, s.embedding_query_prefix)
    searcher = Searcher(
        QdrantClient(url=s.qdrant_url, timeout=s.qdrant_timeout_s), collection, embedder
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    runs = (("filter", True), ("nofilter", False))
    paths = {mode: args.out_dir / f"search_{collection}_{mode}" for mode, _ in runs}
    existing = [
        p for base in paths.values() for p in (base.with_suffix(".json"), base.with_suffix(".md"))
    ]
    if not args.overwrite and any(p.exists() for p in existing):
        print("result files exist; use --overwrite to replace them")
        return 1

    for mode, use_filter in runs:
        results = evaluate(
            report.questions, searcher, lambda d: docs[d].company, use_filter, args.k
        )
        scores = grouped(results, args.k)
        title = (
            f"M1d search: collection {collection}, company filter {'on' if use_filter else 'off'}"
        )
        payload = {"collection": collection, "mode": mode, "k": args.k, "scores": scores,
                   "questions": [asdict(r) | {"rank": r.rank} for r in results]}  # fmt: skip
        base = paths[mode]
        base.with_suffix(".json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        base.with_suffix(".md").write_text(
            render_markdown(title, scores, results), encoding="utf-8"
        )
        print(mode, json.dumps(scores["all"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
