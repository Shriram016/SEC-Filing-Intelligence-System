"""Routed RAG: router (Haiku) → coverage + document list (code) → filtered search → answer.

The M2 engine (router.md, engine.md §3.2, Q104). The answer step is the checked answer
(Q107: claims + quote check + calculator + final rule), or the frozen baseline answer. A route
other than `answer` stops before the search: no search and no answer call, so no extra cost.
If the router fails (broken JSON twice), the result is a clear error, never an unfiltered guess.

Split tables (Q105): after the search, code adds the missing parts of a retrieved split table
(`engine/tables.py`, at most `max_extra_parts` chunks), so the answer step reads the whole table.

Steps (Q109): the router gives one step per company + year pair. Code runs one filtered search
per step (top `top_k` each, split-table parts per step), then merges the chunks in step order
without duplicates. The answer step runs once on the merged chunks.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from filing_rag.baseline.pipeline import BaselineResult
from filing_rag.engine.tables import chunk_key, expand_tables
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


Progress = Callable[[str], None]  # called with a stage name (Q108 API progress events)


class AnswerStep(Protocol):
    """The baseline answer (frozen) or the checked answer (Q107)."""

    def answer(
        self, question: str, hits: list[Hit], on_progress: Progress | None = None
    ) -> BaselineResult: ...


@dataclass
class RoutedResult(BaselineResult):
    decision: RouteDecision | None = None
    reply: str | None = None  # the reply for a route that stops before search
    router_calls: list[LLMResult] = field(default_factory=list)
    added_table_parts: int = 0  # chunks added by the split-table expansion (not searched)
    checked: Any = None  # CheckedAnswer from the checked answer step (Q107), else None
    writer: Any = None  # WriterOutput of the checked answer step (for the logs), else None
    step_hits: list[list[Hit]] = field(default_factory=list)  # Q109: chunks found per step

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

    def retrieve_steps(self, decision: RouteDecision) -> tuple[list[Hit], int, list[list[Hit]]]:
        """One search per step, merged in step order without duplicates.

        Returns (merged chunks, added table parts, chunks per step)."""
        merged: list[Hit] = []
        seen: set[str] = set()
        added_total = 0
        per_step: list[list[Hit]] = []
        for query, doc_names in decision.searches():
            hits, added = self.retrieve(query, doc_names)
            per_step.append(hits)
            added_total += added
            for h in hits:
                key = chunk_key(h)
                if key not in seen:
                    seen.add(key)
                    merged.append(h)
        return merged, added_total, per_step

    def answer(
        self,
        question: str,
        history: Sequence[Turn] = (),
        on_progress: Progress | None = None,
    ) -> RoutedResult:
        """Stages sent to `on_progress`: routing, searching, answering, checking (checked
        answers only). A route that stops early sends only `routing`."""

        def stage(name: str) -> None:
            if on_progress is not None:
                on_progress(name)

        stage("routing")
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
        stage("searching")
        hits, added, per_step = self.retrieve_steps(decision)
        stage("answering")
        base = self.answerer.answer(query, hits, on_progress=on_progress)
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
            writer=getattr(base, "writer", None),
            step_hits=per_step,
        )
