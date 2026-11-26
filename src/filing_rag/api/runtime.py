"""Startup: build the engine and the readiness checks once (api.md, Q108).

The embedding model, the Qdrant client and the catalog load once, at server start.
Portfolio shortcut: the embedding model runs inside the API process (local GPU, needs
`--group embed`); in production a separate embedding service or a CPU model does this.

Paid guard: real LLM calls only when `FILING_RAG_ALLOW_PAID=true`. Otherwise demo mode: a
fake router replies "unclear" with a demo message, so no question reaches a paid model.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from filing_rag.api.service import Engine
from filing_rag.config import Settings

DEMO_MESSAGE = (
    "Demo mode: paid model calls are off on this server (set FILING_RAG_ALLOW_PAID=true)."
)
DEMO_ROUTER_REPLY = json.dumps({
    "route": "unclear", "standalone_question": "demo", "reason": DEMO_MESSAGE,
    "steps": [], "doc_type": None, "metric": None,
})  # fmt: skip


@dataclass
class Runtime:
    engine: Engine
    readiness: Callable[[], dict[str, bool]]
    mode: str  # "paid" or "demo"


def build_runtime(s: Settings) -> Runtime:
    from qdrant_client import QdrantClient

    from filing_rag.engine.checked import CheckedAnswerer
    from filing_rag.engine.routed import RoutedPipeline
    from filing_rag.ingest.embed import BgeEmbedder
    from filing_rag.llm.client import LLM, AnthropicLLM
    from filing_rag.llm.fake import FakeLLM
    from filing_rag.router.catalog import DocCatalog
    from filing_rag.router.router import Router
    from filing_rag.search.searcher import Searcher

    catalog = DocCatalog.from_settings(s)
    client = QdrantClient(url=s.qdrant_url, timeout=s.qdrant_timeout_s)
    embedder = BgeEmbedder(s.embedding_model, s.embedding_query_prefix)
    searcher = Searcher(client, s.qdrant_collection, embedder)
    router_llm: LLM
    answer_llm: LLM
    if s.allow_paid:
        router_llm = AnthropicLLM(s, allow_paid=True, role="router")
        answer_llm = AnthropicLLM(s, allow_paid=True)
    else:
        router_llm = FakeLLM([DEMO_ROUTER_REPLY], price_in=0.0, price_out=0.0)
        answer_llm = FakeLLM(["{}"], price_in=0.0, price_out=0.0)
    engine = RoutedPipeline(
        Router(router_llm, catalog, s.router_max_tokens, s.router_year_rule),
        searcher,
        CheckedAnswerer(answer_llm, s.checked_max_tokens),
        s.baseline_top_k,
        s.table_parts_max_extra,
    )

    def readiness() -> dict[str, bool]:
        # No call to the AI provider: a readiness probe that depends on an outside service
        # makes every replica "not ready" when that service is slow. Only the key is checked.
        checks = {"catalog": len(catalog.docs) > 0}
        try:
            checks["qdrant_collection"] = bool(client.collection_exists(s.qdrant_collection))
        except Exception:
            checks["qdrant_collection"] = False
        checks["ai_provider_key"] = (not s.allow_paid) or s.anthropic_api_key is not None
        return checks

    return Runtime(engine, readiness, "paid" if s.allow_paid else "demo")
