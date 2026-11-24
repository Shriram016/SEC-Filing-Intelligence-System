"""API service (Q108): SSE format, event order, guards, health. Fake engine parts, no cost."""

import json
import threading
import time
from collections.abc import Sequence
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from filing_rag.api.app import create_app
from filing_rag.api.runtime import DEMO_MESSAGE, DEMO_ROUTER_REPLY, Runtime
from filing_rag.api.service import CostMeter
from filing_rag.api.sse import parse_sse, sse_event
from filing_rag.config import Settings
from filing_rag.engine.checked import CheckedAnswerer
from filing_rag.engine.routed import Progress, RoutedPipeline, RoutedResult
from filing_rag.llm.fake import FakeLLM
from filing_rag.router.catalog import CatalogDoc, DocCatalog
from filing_rag.router.router import Router, Turn
from filing_rag.search.searcher import Hit

CATALOG = DocCatalog([CatalogDoc("APPLE_2022_10K", "Apple", "10-K", 2022)])
TEXT = "Total net sales 394,328 for the year"


class Searcher:
    def search(self, query: str, company: str | None = None, k: int = 10,
               doc_names: Sequence[str] | None = None) -> list[Hit]:  # fmt: skip
        return [Hit(0.9, {"doc_name": "APPLE_2022_10K", "page": 25, "page_end": 25,
                          "text": TEXT, "company": "Apple", "doc_type": "10-K",
                          "period_end": "2022-09-24"})]  # fmt: skip

    def table_parts(self, table_id: str) -> list[Hit]:
        return []


STEP = {"company": "Apple", "year": 2022, "search": "Apple net sales 2022"}


def route_reply(**kw: Any) -> str:
    base = {"route": "answer", "standalone_question": "What were Apple's net sales in FY2022?",
            "reason": "factual", "other_companies": [], "doc_type": None, "metric": "net sales",
            "steps": [STEP]}  # fmt: skip
    return json.dumps(base | kw)


def writer_reply(quote: str = "Total net sales 394,328", value: float = 394328) -> str:
    return json.dumps({
        "found": True,
        "claims": [{"id": "c1", "label": "Apple net sales, FY2022", "extract": 1, "quote": quote,
                    "value": value, "unit": "USD million", "period": "FY2022"}],
        "calculations": [], "main": "c1", "answer": "Apple's net sales were {c1} in FY2022.",
    })  # fmt: skip


def pipeline(route: str = route_reply(), writer: str = writer_reply()) -> RoutedPipeline:
    router_llm = FakeLLM([route], price_in=0.10, price_out=0.50)
    return RoutedPipeline(Router(router_llm, CATALOG), Searcher(),
                          CheckedAnswerer(FakeLLM([writer])))  # fmt: skip


def settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def client(engine: Any, cost: CostMeter | None = None, **kw: Any) -> TestClient:
    ready = kw.pop("ready", {"catalog": True, "qdrant_collection": True})
    app = create_app(settings(**kw), lambda s: Runtime(engine, lambda: ready, "demo"), cost)
    return TestClient(app)


def ask(c: TestClient, question: str = "Apple net sales 2022?", **body: Any) -> Any:
    return c.post("/v1/ask", json={"question": question} | body)


def events(resp: Any) -> list[tuple[str, dict[str, Any]]]:
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")
    return parse_sse(resp.text)


# ---------- SSE format ----------


def test_sse_event_is_one_data_line() -> None:
    text = sse_event("answer", {"text": "line one\nline two", "q": "“quoted”"})
    assert text.startswith("event: answer\ndata: {") and text.endswith("}\n\n")
    assert text.count("\n") == 3  # the newline inside the text is escaped
    assert parse_sse(text) == [("answer", {"text": "line one\nline two", "q": "“quoted”"})]


# ---------- event order ----------


def test_answer_stream_progress_then_checked_answer_then_done() -> None:
    with client(pipeline()) as c:
        resp = ask(c)
        ev = events(resp)
    names = [n for n, _ in ev]
    assert names == ["progress"] * 4 + ["answer", "done"]
    assert [d["stage"] for n, d in ev if n == "progress"] == [
        "routing", "searching", "answering", "checking"]  # fmt: skip
    ans = ev[4][1]
    assert ans["status"] == "answer" and ans["route"] == "answer"
    assert ans["text"].startswith("Apple's net sales were $394,328 million in FY2022.")
    assert ans["value"] == 394328 and ans["unit"] == "USD million"
    assert ans["citations"] == [{"doc_name": "APPLE_2022_10K", "company": "Apple",
                                 "doc_type": "10-K", "period_end": "2022-09-24", "page": 25,
                                 "quote": "Total net sales 394,328"}]  # fmt: skip
    done = ev[5][1]
    assert done["request_id"] == resp.headers["x-request-id"] and done["cost_usd"] > 0


def test_a_failed_quote_check_is_a_refused_answer_without_citations() -> None:
    with client(pipeline(writer=writer_reply("Total net sales 999,999", 999999))) as c:
        ev = events(ask(c))
    ans = dict(ev)["answer"]
    assert ans["status"] == "refused" and ans["citations"] == [] and "999" not in ans["text"]


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        (route_reply(route="advice"), "advice"),
        (route_reply(steps=[], other_companies=["Tesla"]), "not_covered"),
        (route_reply(route="unclear", reason="Which company?"), "unclear"),
    ],
)
def test_a_stop_route_sends_its_reply_as_a_refused_answer(route: str, expected: str) -> None:
    with client(pipeline(route=route)) as c:
        ev = events(ask(c))
    assert [n for n, _ in ev] == ["progress", "answer", "done"]
    ans = ev[1][1]
    assert ans["status"] == "refused" and ans["route"] == expected and ans["text"]


def test_router_failure_is_an_error_event_only() -> None:
    with client(pipeline(route="not json")) as c:
        ev = events(ask(c))
    assert [n for n, _ in ev] == ["progress", "error"]
    err = ev[1][1]
    assert err["code"] == "router_failed" and "JSON" not in err["message"]


def test_broken_writer_json_is_answer_failed() -> None:
    with client(pipeline(writer="{")) as c:
        ev = events(ask(c))
    assert ev[-1] == ("error", ev[-1][1]) and ev[-1][1]["code"] == "answer_failed"


class Recording:
    def __init__(self) -> None:
        self.history: Sequence[Turn] = ()

    def answer(self, question: str, history: Sequence[Turn] = (),
               on_progress: Progress | None = None) -> RoutedResult:  # fmt: skip
        self.history = history
        return pipeline().answer(question, history, on_progress)


def test_history_turns_reach_the_engine() -> None:
    eng = Recording()
    with client(eng) as c:
        events(
            ask(
                c,
                "And 2021?",
                history=[
                    {"role": "user", "text": "Apple sales 2022?"},
                    {"role": "assistant", "text": "$394,328 million"},
                ],
            )
        )
    assert eng.history == [Turn("user", "Apple sales 2022?"), Turn("assistant", "$394,328 million")]


class Crashing:
    def answer(self, question: str, history: Sequence[Turn] = (),
               on_progress: Progress | None = None) -> RoutedResult:  # fmt: skip
        raise RuntimeError("secret detail sk-ant-123")


def test_an_engine_crash_is_an_internal_error_without_details() -> None:
    with client(Crashing()) as c:
        ev = events(ask(c))
    assert [n for n, _ in ev] == ["error"]
    assert ev[0][1]["code"] == "internal" and "secret" not in ev[0][1]["message"]


# ---------- guards ----------


@pytest.mark.parametrize(
    "body",
    [
        {"question": ""},
        {"question": "x" * 1001},
        {"question": "x", "history": [{"role": "user", "text": "t"}] * 7},
        {"question": "x", "history": [{"role": "user", "text": "t" * 2001}]},
        {"question": "x", "history": [{"role": "system", "text": "t"}]},
    ],
)
def test_bad_requests_are_422_before_the_stream(body: dict[str, Any]) -> None:
    with client(pipeline()) as c:
        assert c.post("/v1/ask", json=body).status_code == 422


class Slow:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.release = threading.Event()

    def answer(self, question: str, history: Sequence[Turn] = (),
               on_progress: Progress | None = None) -> RoutedResult:  # fmt: skip
        if on_progress:
            on_progress("routing")
        self.release.wait(self.seconds)
        return pipeline().answer(question, history)


def test_timeout_is_an_error_and_the_slot_stays_taken_until_the_thread_ends() -> None:
    eng = Slow(5.0)
    with client(eng, api_timeout_s=0.2, api_max_concurrent=1) as c:
        ev = events(ask(c))
        assert [n for n, _ in ev] == ["progress", "error"] and ev[1][1]["code"] == "timeout"
        busy = ask(c)  # the slow thread still runs
        assert busy.status_code == 503 and busy.headers["retry-after"] == "5"
        eng.release.set()
        for _ in range(50):
            if c.app.state.service.active == 0:  # type: ignore[attr-defined]
                break
            time.sleep(0.02)
        assert ask(c).status_code == 200


def test_cost_counts_and_the_daily_cap_stops_new_questions() -> None:
    day = [date(2026, 11, 22)]
    meter = CostMeter(0.000001, today=lambda: day[0])
    with client(pipeline(), meter) as c:
        assert [n for n, _ in events(ask(c))][-1] == "done"
        assert meter.spent > 0
        ev = events(ask(c))
        assert [n for n, _ in ev] == ["error"] and ev[0][1]["code"] == "cost_cap"
        day[0] = date(2026, 11, 23)  # a new day resets the meter
        assert [n for n, _ in events(ask(c))][-1] == "done"


# ---------- health ----------


def test_one_json_log_line_per_question(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="filing_rag.api"), client(pipeline()) as c:
        resp = ask(c)
        events(resp)
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.name == "filing_rag.api"]
    assert len(lines) == 1
    assert lines[0]["request_id"] == resp.headers["x-request-id"]
    assert lines[0]["route"] == "answer" and lines[0]["doc_names"] == ["APPLE_2022_10K"]
    assert lines[0]["status"] == "answer" and lines[0]["cost_usd"] > 0
    assert lines[0]["search_question"] == "What were Apple's net sales in FY2022?"
    assert lines[0]["pages"] == [25] and lines[0]["writer_found"] is True
    assert lines[0]["steps"] == [STEP | {"doc_names": ["APPLE_2022_10K"]}]
    assert lines[0]["claims_passed"] == 1 and lines[0]["check_failures"] == {}


def test_health_and_ready() -> None:
    with client(pipeline()) as c:
        assert c.get("/health").json() == {"status": "ok"}
        r = c.get("/ready")
        assert r.status_code == 200 and r.json()["ready"] and r.json()["mode"] == "demo"
    with client(pipeline(), ready={"catalog": True, "qdrant_collection": False}) as c:
        r = c.get("/ready")
        assert r.status_code == 503 and r.json()["checks"]["qdrant_collection"] is False


def test_demo_mode_never_reaches_a_paid_model() -> None:
    eng = pipeline(route=DEMO_ROUTER_REPLY)
    with client(eng) as c:
        ev = events(ask(c))
    ans = dict(ev)["answer"]
    assert ans["status"] == "refused" and ans["text"] == DEMO_MESSAGE
