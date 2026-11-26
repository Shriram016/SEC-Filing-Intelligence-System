"""Reranker (Q111, docs/v3/engine.md §3.2): a cross-encoder sorts the search candidates again.

The vector search compares two embeddings made apart from each other: fast, but rough. A
cross-encoder reads the question and one chunk together and gives the pair a score: slower,
but more exact. So the filtered search returns `candidates` chunks per step and the reranker
keeps the best `k`.

`RerankingSearcher` wraps a `Searcher` and has the same interface (`search`, `table_parts`), so
the routed engine and the tests need no change. The heavy libraries (torch,
sentence-transformers) are imported only when `CrossEncoderReranker` loads (optional `embed`
group, not installed in CI).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from filing_rag.ingest.labels import collapse
from filing_rag.search.searcher import Hit


class Reranker(Protocol):
    def score(self, query: str, texts: Sequence[str]) -> list[float]: ...


class Search(Protocol):
    def search(
        self,
        query: str,
        company: str | None = None,
        k: int = 10,
        doc_names: Sequence[str] | None = None,
    ) -> list[Hit]: ...

    def table_parts(self, table_id: str) -> list[Hit]: ...


def rerank_text(payload: dict[str, Any]) -> str:
    """What the reranker reads: the context line (company, type, period, section path) and the
    chunk text with runs of spaces removed (a table keeps its title, unit and header)."""
    context = str(payload.get("context") or "")
    body = collapse(str(payload.get("text") or ""))
    return f"{context}\n{body}" if context else body


class CrossEncoderReranker:
    """A local cross-encoder, fp16 on the GPU when there is one."""

    def __init__(self, model_id: str, max_length: int = 512, batch_size: int = 32) -> None:
        import torch
        from sentence_transformers import CrossEncoder

        device = "cuda" if torch.cuda.is_available() else "cpu"
        kwargs: dict[str, Any] = {"torch_dtype": torch.float16} if device == "cuda" else {}
        self._model = CrossEncoder(
            model_id, device=device, max_length=max_length, model_kwargs=kwargs
        )
        self.model_id = model_id
        self.batch_size = batch_size
        self.device = device

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        pairs = [(query, t) for t in texts]
        scores = self._model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        return [float(s) for s in scores]


@dataclass
class RerankStats:
    """Time and counts, for the search test and the logs."""

    calls: int = 0
    candidates: int = 0
    seconds: list[float] = field(default_factory=list)


class RerankingSearcher:
    """Search `candidates` chunks, rerank them, keep the best `k`.

    The returned hits carry the reranker score as `score`; the vector score stays in the payload
    as `search_score`, and the vector rank as `search_rank` (1 = first).
    """

    def __init__(self, searcher: Search, reranker: Reranker, candidates: int = 50) -> None:
        if candidates < 1:
            raise ValueError("candidates must be at least 1")
        self.searcher = searcher
        self.reranker = reranker
        self.candidates = candidates
        self.stats = RerankStats()

    def search(
        self,
        query: str,
        company: str | None = None,
        k: int = 10,
        doc_names: Sequence[str] | None = None,
    ) -> list[Hit]:
        if k < 1:
            raise ValueError("k must be at least 1")
        pool = self.searcher.search(
            query, company=company, k=max(k, self.candidates), doc_names=doc_names
        )
        if not pool:
            return []
        start = time.perf_counter()
        scores = self.reranker.score(query, [rerank_text(h.payload) for h in pool])
        self.stats.calls += 1
        self.stats.candidates += len(pool)
        self.stats.seconds.append(time.perf_counter() - start)
        if len(scores) != len(pool):
            raise RuntimeError(f"reranker gave {len(scores)} scores for {len(pool)} chunks")
        ranked = sorted(range(len(pool)), key=lambda i: -scores[i])  # stable: ties keep order
        return [
            Hit(
                score=scores[i],
                payload=pool[i].payload | {"search_score": pool[i].score, "search_rank": i + 1},
            )
            for i in ranked[:k]
        ]

    def table_parts(self, table_id: str) -> list[Hit]:
        return self.searcher.table_parts(table_id)


def build_searcher(searcher: Search, model_id: str, candidates: int, **kw: Any) -> Search:
    """The searcher for the routed engine: plain when `model_id` is empty, else reranked."""
    if not model_id:
        return searcher
    return RerankingSearcher(searcher, CrossEncoderReranker(model_id, **kw), candidates)
