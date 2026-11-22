"""Ask service (api.md §3, Q108): runs the engine in a worker thread and streams SSE events.

- The engine is synchronous (model calls, GPU embedding). It runs in a thread; its progress
  stages come back through a queue and go out as `progress` events at once.
- The answer goes out once, after the checks (Q67). An error replaces `answer` and `done`.
- Guards (M2): at most `max_concurrent` questions at a time (the route answers 503 when full),
  a total time limit, and a daily cost cap. A question that times out still holds its slot
  until its thread ends (a thread cannot be stopped), and its cost still counts.
- One JSON log line per question.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import date
from functools import partial
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel

from filing_rag.api.schemas import (
    AnswerEvent,
    Citation,
    DoneEvent,
    ErrorEvent,
)
from filing_rag.api.sse import sse_event
from filing_rag.engine.final import CheckedAnswer
from filing_rag.engine.routed import Progress, RoutedResult
from filing_rag.router.router import Turn

log = logging.getLogger("filing_rag.api")
AnswerStatus = Literal["answer", "partial", "refused"]

MSG_ROUTER = "The question could not be processed. Please try again."
MSG_ANSWER = "The answer could not be produced. Please try again."
MSG_TIMEOUT = "The question took too long. Please try again."
MSG_COST = "The daily cost limit of this server is reached. Please try again tomorrow."
MSG_INTERNAL = "Internal error. Please try again."


class Engine(Protocol):
    def answer(
        self,
        question: str,
        history: Sequence[Turn] = (),
        on_progress: Progress | None = None,
    ) -> RoutedResult: ...


class CostMeter:
    """Spend per day, in memory (one process). M5: a shared store (for example Redis)."""

    def __init__(self, cap_usd: float, today: Callable[[], date] = date.today) -> None:
        self.cap_usd = cap_usd
        self.today = today
        self._day = today()
        self._spent = 0.0

    def _roll(self) -> None:
        if self.today() != self._day:
            self._day, self._spent = self.today(), 0.0

    @property
    def spent(self) -> float:
        self._roll()
        return self._spent

    def add(self, usd: float) -> None:
        self._roll()
        self._spent += usd

    def over_cap(self) -> bool:
        return self.spent >= self.cap_usd


def citations(c: CheckedAnswer) -> list[Citation]:
    """Quotes of the passed claims behind the answer (the answer's sources)."""
    keep = {(s.doc_name, s.page) for s in c.sources}
    out: list[Citation] = []
    for it in c.items:
        if it.kind != "claim" or not it.ok or it.hit is None or not it.quote:
            continue
        if (it.hit.doc_name, it.hit.page) not in keep:
            continue
        p = it.hit.payload
        out.append(Citation(doc_name=it.hit.doc_name, company=p.get("company"),
                            doc_type=p.get("doc_type"), period_end=p.get("period_end"),
                            page=it.hit.page, quote=it.quote))  # fmt: skip
    return out


def result_events(r: RoutedResult, request_id: str) -> list[tuple[str, BaseModel]]:
    """The final event of a finished engine run: `answer`, or `error`."""
    d = r.decision
    if d is None or d.route is None:
        return [("error", ErrorEvent(code="router_failed", message=MSG_ROUTER,
                                     request_id=request_id))]  # fmt: skip
    if r.reply is not None:  # a route that stops before the search
        return [("answer", AnswerEvent(status="refused", route=str(d.route), text=r.reply))]
    c = r.checked
    if not isinstance(c, CheckedAnswer):
        return [("error", ErrorEvent(code="answer_failed", message=MSG_ANSWER,
                                     request_id=request_id))]  # fmt: skip
    return [("answer", AnswerEvent(
        status=cast(AnswerStatus, str(c.status)), route=str(d.route), text=c.text,
        value=c.main_value, unit=c.main_unit, period=c.period, citations=citations(c),
    ))]  # fmt: skip


class AskService:
    def __init__(
        self,
        engine: Engine,
        max_concurrent: int,
        timeout_s: float,
        cost: CostMeter,
    ) -> None:
        self.engine = engine
        self.max_concurrent = max_concurrent
        self.timeout_s = timeout_s
        self.cost = cost
        self.active = 0  # touched only on the event loop

    def try_acquire(self) -> bool:
        if self.active >= self.max_concurrent:
            return False
        self.active += 1
        return True

    def _release(self) -> None:
        self.active = max(0, self.active - 1)

    def _finish(self, request_id: str, task: asyncio.Future[RoutedResult]) -> None:
        """When the engine thread ends (also after a timeout): free the slot, count the cost."""
        self._release()
        if task.cancelled() or task.exception() is not None:
            return
        self.cost.add(task.result().cost_usd)

    async def stream(
        self, question: str, history: Sequence[Turn], request_id: str
    ) -> AsyncIterator[str]:
        """SSE events for one question. The caller has taken a slot with `try_acquire`."""
        t0 = time.monotonic()
        task: asyncio.Future[RoutedResult] | None = None
        entry: dict[str, Any] = {"request_id": request_id}
        try:
            if self.cost.over_cap():
                entry["error"] = "cost_cap"
                yield sse_event("error", ErrorEvent(code="cost_cap", message=MSG_COST,
                                                    request_id=request_id))  # fmt: skip
                return
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[str] = asyncio.Queue()

            def on_progress(stage: str) -> None:  # called in the engine thread
                loop.call_soon_threadsafe(queue.put_nowait, stage)

            task = asyncio.ensure_future(
                asyncio.to_thread(self.engine.answer, question, history, on_progress)
            )
            task.add_done_callback(partial(self._finish, request_id))
            getter = asyncio.ensure_future(queue.get())
            try:
                while True:
                    remaining = t0 + self.timeout_s - time.monotonic()
                    if remaining <= 0:
                        break
                    done, _ = await asyncio.wait(
                        {getter, task}, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
                    )
                    if getter in done:
                        yield sse_event("progress", {"stage": getter.result()})
                        getter = asyncio.ensure_future(queue.get())
                    elif task in done or not done:
                        break
            finally:
                getter.cancel()
            if not task.done():
                entry["error"] = "timeout"
                yield sse_event("error", ErrorEvent(code="timeout", message=MSG_TIMEOUT,
                                                    request_id=request_id))  # fmt: skip
                return
            while not queue.empty():  # stages sent just before the end
                yield sse_event("progress", {"stage": queue.get_nowait()})
            exc = task.exception()
            if exc is not None:
                log.error("engine failed (request %s)", request_id, exc_info=exc)
                entry["error"] = "internal"
                yield sse_event("error", ErrorEvent(code="internal", message=MSG_INTERNAL,
                                                    request_id=request_id))  # fmt: skip
                return
            r = task.result()
            entry |= _summary(r)
            events = result_events(r, request_id)
            for name, ev in events:
                yield sse_event(name, ev)
            if events[-1][0] == "error":
                entry["error"] = events[-1][1].model_dump()["code"]
                return
            finished = DoneEvent(request_id=request_id, cost_usd=round(r.cost_usd, 6),
                                 latency_s=round(time.monotonic() - t0, 3))  # fmt: skip
            yield sse_event("done", finished)
        finally:
            if task is None:
                self._release()
            entry["latency_s"] = round(time.monotonic() - t0, 3)
            log.info(json.dumps(entry))


def _summary(r: RoutedResult) -> dict[str, Any]:
    d = r.decision
    c = r.checked
    checked = isinstance(c, CheckedAnswer)
    writer = r.writer
    return {
        "route": str(d.route) if d and d.route else None,
        "search_question": d.search_question if d and d.route else None,
        "doc_names": list(d.doc_names or []) if d else [],
        "pages": [h.page for h in r.hits],
        "status": str(c.status) if checked else None,
        "writer_found": writer.found if writer is not None else None,
        "claims_total": c.claims_total if checked else 0,
        "claims_passed": c.claims_passed if checked else 0,
        "check_failures": c.failures if checked else {},
        "cost_usd": round(r.cost_usd, 6),
    }
