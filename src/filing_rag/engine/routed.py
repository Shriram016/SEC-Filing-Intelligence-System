"""Routed RAG: router (Haiku) → coverage + document list (code) → filtered search → answer.

The M2 engine (router.md, engine.md §3.2, Q104). The answer step is the checked answer
(Q107: claims + quote check + calculator + final rule), or the frozen baseline answer. A route
other than `answer` stops before the search: no search and no answer call, so no extra cost.
If the router fails (broken JSON twice), the result is a clear error, never an unfiltered guess.

Split tables (Q105): after the search, code adds the missing parts of a retrieved split table
(`engine/tables.py`, at most `max_extra_parts` chunks), so the answer step reads the whole table.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from filing_rag.baseline.pipeline import BaselineResult
from filing_rag.engine.tables import expand_tables
from filing_rag.llm.client import LLMResult
from filing_rag.router.router import Route, RouteDecision, Router, Turn, reply_text
from filing_rag.search.searcher import Hit


class FilteredSearch(Protocol):
    def search(
        self,
        query: str,
        company: str | None = None,
        k: int = 10,
        doc_names: Sequence[str] | None = None,
    ) -> list[Hit]: ...

    def table_parts(self, table_id: str) -> list[Hit]: ...


class AnswerStep(Protocol):
    """The baseline answer (frozen) or the checked answer (Q107)."""

    def answer(self, question: str, hits: list[Hit]) -> BaselineResult: ...


@dataclass
class RoutedResult(BaselineResult):
    decision: RouteDecision | None = None
    reply: str | None = None  # the reply for a route that stops before search
    router_calls: list[LLMResult] = field(default_factory=list)
    added_table_parts: int = 0  # chunks added by the split-table expansion (not searched)
    checked: Any = None  # CheckedAnswer from the checked answer step (Q107), else None

    @property
    def router_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.router_calls)

    @property
    def answer_cost_usd(self) -> float:
        return self.cost_usd - self.router_cost_usd

    @property
    def router_latency_s(self) -> float:
        return sum(c.latency_s for c in self.router_calls)


class RoutedPipeline:
    def __init__(
        self,
        router: Router,
        searcher: FilteredSearch,
        answerer: AnswerStep,
        top_k: int = 5,
        max_extra_parts: int = 3,
    ) -> None:
        self.router = router
        self.searcher = searcher
        self.answerer = answerer
        self.top_k = top_k
        self.max_extra_parts = max_extra_parts

    def retrieve(self, query: str, doc_names: Sequence[str] | None) -> tuple[list[Hit], int]:
        """Filtered search, then the split-table expansion. Returns (chunks, added count)."""
        hits = self.searcher.search(query, k=self.top_k, doc_names=doc_names)
        return expand_tables(hits, self.searcher, self.max_extra_parts)

    def answer(self, question: str, history: Sequence[Turn] = ()) -> RoutedResult:
        decision = self.router.decide(question, history)
        router_calls = list(decision.calls)
        if decision.route != Route.ANSWER:
            return RoutedResult(
                question=question,
                hits=[],
                answer=None,
                error=decision.error,
                calls=list(router_calls),
                decision=decision,
                reply=reply_text(decision),
                router_calls=router_calls,
            )
        query = decision.search_question
        hits, added = self.retrieve(query, decision.doc_names)
        base = self.answerer.answer(query, hits)
        return RoutedResult(
            question=question,
            hits=hits,
            answer=base.answer,
            error=base.error,
            calls=router_calls + base.calls,
            decision=decision,
            router_calls=router_calls,
            added_table_parts=added,
            checked=getattr(base, "checked", None),
        )
