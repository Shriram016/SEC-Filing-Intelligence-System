from collections.abc import Sequence

import pytest

from filing_rag.engine.routed import RoutedPipeline
from filing_rag.engine.tables import expand_tables
from filing_rag.search.reranker import RerankingSearcher, build_searcher, rerank_text
from filing_rag.search.searcher import Hit


def hit(name: str, score: float, **kw: object) -> Hit:
    payload = {"doc_name": "APPLE_2022_10K", "page": 1, "text": name, "context": "Apple 10-K"}
    return Hit(score, payload | kw)


class PoolSearcher:
    """Gives back the first k of a fixed pool; records the calls."""

    def __init__(self, pool: list[Hit]) -> None:
        self.pool = pool
        self.calls: list[dict[str, object]] = []

    def search(
        self,
        query: str,
        company: str | None = None,
        k: int = 10,
        doc_names: Sequence[str] | None = None,
    ) -> list[Hit]:
        self.calls.append({"query": query, "company": company, "k": k, "doc_names": doc_names})
        return self.pool[:k]

    def table_parts(self, table_id: str) -> list[Hit]:
        return [h for h in self.pool if h.payload.get("table_id") == table_id]


class WordReranker:
    """Score = how many times the word "income" is in the text (a fake cross-encoder)."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, list[str]]] = []

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        self.seen.append((query, list(texts)))
        return [float(t.count("income")) for t in texts]


POOL = [hit("revenue", 0.9), hit("cost", 0.8), hit("net income income", 0.7),
        hit("income", 0.6), hit("tax", 0.5)]  # fmt: skip


def test_rerank_text_has_the_context_line_and_the_collapsed_text() -> None:
    payload = {"context": "Apple 10-K FY2022 › Item 8", "text": "Net income    99,803\n\n  x"}
    assert rerank_text(payload) == "Apple 10-K FY2022 › Item 8\nNet income 99,803\nx"
    assert rerank_text({"text": "only text"}) == "only text"


def test_it_searches_the_candidates_and_keeps_the_best_k() -> None:
    inner, rr = PoolSearcher(POOL), WordReranker()
    s = RerankingSearcher(inner, rr, candidates=4)
    out = s.search("net income?", k=2, doc_names=["APPLE_2022_10K"])
    assert inner.calls == [{"query": "net income?", "company": None, "k": 4,
                            "doc_names": ["APPLE_2022_10K"]}]  # fmt: skip
    assert [h.payload["text"] for h in out] == ["net income income", "income"]
    assert [h.score for h in out] == [2.0, 1.0]
    assert out[0].payload["search_rank"] == 3 and out[0].payload["search_score"] == 0.7
    assert rr.seen[0][0] == "net income?" and len(rr.seen[0][1]) == 4


def test_ties_keep_the_vector_order_and_k_above_candidates_is_honoured() -> None:
    s = RerankingSearcher(PoolSearcher(POOL), WordReranker(), candidates=2)
    out = s.search("q", k=5)  # k > candidates → search k
    assert [h.payload["text"] for h in out] == ["net income income", "income", "revenue",
                                                 "cost", "tax"]  # fmt: skip


def test_no_candidates_means_no_reranker_call() -> None:
    rr = WordReranker()
    assert RerankingSearcher(PoolSearcher([]), rr).search("q", k=5) == []
    assert rr.seen == []


def test_the_stored_payload_is_not_changed() -> None:
    pool = [hit("income", 0.5)]
    RerankingSearcher(PoolSearcher(pool), WordReranker()).search("q", k=1)
    assert "search_rank" not in pool[0].payload


def test_bad_settings_and_a_wrong_score_count_fail() -> None:
    with pytest.raises(ValueError, match="candidates"):
        RerankingSearcher(PoolSearcher(POOL), WordReranker(), candidates=0)
    with pytest.raises(ValueError, match="k must"):
        RerankingSearcher(PoolSearcher(POOL), WordReranker()).search("q", k=0)

    class Short:
        def score(self, query: str, texts: Sequence[str]) -> list[float]:
            return [1.0]

    with pytest.raises(RuntimeError, match="1 scores for 5"):
        RerankingSearcher(PoolSearcher(POOL), Short()).search("q", k=2)


def test_split_table_parts_come_after_the_rerank() -> None:
    parts = [hit(f"income part {i}", 0.1, table_id="t1", table_part=i, table_parts=2,
                 is_table=True, page=5 + i) for i in (1, 2)]  # fmt: skip
    pool = [hit("revenue", 0.9), parts[0], parts[1]]
    s = RerankingSearcher(PoolSearcher(pool), WordReranker(), candidates=3)
    top = s.search("q", k=1)
    assert top[0].payload["table_part"] == 1
    chunks, added = expand_tables(top, s, 3)
    assert added == 1 and [c.payload.get("table_part") for c in chunks] == [1, 2]


def test_build_searcher_off_gives_the_plain_searcher() -> None:
    inner = PoolSearcher(POOL)
    assert build_searcher(inner, "", 50) is inner


def test_the_routed_engine_accepts_the_reranking_searcher() -> None:
    s = RerankingSearcher(PoolSearcher(POOL), WordReranker(), candidates=5)
    pipe = RoutedPipeline(None, s, None, 2, 3)  # type: ignore[arg-type]
    chunks, added = pipe.retrieve("income", ["APPLE_2022_10K"])
    assert [c.payload["text"] for c in chunks] == ["net income income", "income"]
    assert added == 0
