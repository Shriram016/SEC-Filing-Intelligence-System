"""Semantic search with metadata filters (docs/v3/engine.md §3.2).

Filter rule (Q104): the router + catalog choose the documents (company, year Y else Y+1, named
doc type); the search keeps only chunks whose `doc_name` is in that list (hard filter). The
`company` filter stays for the M1d search test. BM25 and a reranker are added only on measured
need (Q26, Q27).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from qdrant_client import QdrantClient, models


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class Hit:
    """One search result. `payload` holds every stored chunk field (text, section, ...)."""

    score: float
    payload: dict[str, Any]

    @property
    def doc_name(self) -> str:
        return str(self.payload["doc_name"])

    @property
    def page(self) -> int:
        return int(self.payload["page"])

    @property
    def page_end(self) -> int:
        return int(self.payload.get("page_end") or self.payload["page"])

    def covers(self, doc_name: str, page: int) -> bool:
        """True when this chunk comes from `doc_name` and spans `page`."""
        return self.doc_name == doc_name and self.page <= page <= self.page_end


class Searcher:
    def __init__(self, client: QdrantClient, collection: str, embedder: QueryEmbedder) -> None:
        self.client = client
        self.collection = collection
        self.embedder = embedder

    @staticmethod
    def build_filter(
        company: str | None = None, doc_names: Sequence[str] | None = None
    ) -> models.Filter | None:
        """`doc_names=None` or empty = no document filter."""
        must: list[models.Condition] = []
        if company:
            must.append(
                models.FieldCondition(key="company", match=models.MatchValue(value=company))
            )
        if doc_names:
            must.append(
                models.FieldCondition(key="doc_name", match=models.MatchAny(any=list(doc_names)))
            )
        return models.Filter(must=must) if must else None

    def search(
        self,
        query: str,
        company: str | None = None,
        k: int = 10,
        doc_names: Sequence[str] | None = None,
    ) -> list[Hit]:
        if k < 1:
            raise ValueError("k must be at least 1")
        vector = self.embedder.embed_query(query)
        result = self.client.query_points(
            self.collection,
            query=vector,
            query_filter=self.build_filter(company, doc_names),
            limit=k,
            with_payload=True,
        )
        return [Hit(score=float(p.score), payload=dict(p.payload or {})) for p in result.points]

    def table_parts(self, table_id: str, limit: int = 256) -> list[Hit]:
        """All stored parts of one split table, in part order (Q105). `table_id` is indexed."""
        flt = models.Filter(
            must=[models.FieldCondition(key="table_id", match=models.MatchValue(value=table_id))]
        )
        points, _ = self.client.scroll(
            self.collection, scroll_filter=flt, limit=limit, with_payload=True
        )
        hits = [Hit(score=0.0, payload=dict(p.payload or {})) for p in points]
        return sorted(hits, key=lambda h: int(h.payload.get("table_part") or 1))
