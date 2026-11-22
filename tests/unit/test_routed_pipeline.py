import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from filing_rag.baseline.pipeline import BaselinePipeline
from filing_rag.engine.routed import RoutedPipeline
from filing_rag.evaluation.baseline import (
    answerable,
    estimate_router,
    rough_tokens,
    run,
    scorecard,
    write_run,
)
from filing_rag.evaluation.dev_set import DevQuestion
from filing_rag.llm.fake import FakeLLM
from filing_rag.router.catalog import CatalogDoc, DocCatalog
from filing_rag.router.router import Route, Router, Turn
from filing_rag.search.searcher import Hit

CATALOG = DocCatalog(
    [
        CatalogDoc("APPLE_2021_10K", "Apple", "10-K", 2021),
        CatalogDoc("APPLE_2022_10K", "Apple", "10-K", 2022),
    ]
)


class RecordingSearcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        query: str,
        company: str | None = None,
        k: int = 10,
        doc_names: Sequence[str] | None = None,
    ) -> list[Hit]:
        self.calls.append({"query": query, "k": k, "doc_names": doc_names})
        payload = {"doc_name": "APPLE_2022_10K", "page": 3, "page_end": 3, "text": "Revenue 100"}
        return [Hit(0.9, payload)]

    def table_parts(self, table_id: str) -> list[Hit]:
        return []


def route_reply(**kw: Any) -> str:
    base: dict[str, Any] = {
        "route": "answer",
        "standalone_question": "What was Apple's revenue in FY2022?",
        "reason": "factual",
        "companies": ["Apple"],
        "other_companies": [],
        "years": [2022],
        "doc_type": None,
        "metric": "revenue",
    }
    return json.dumps(base | kw)


ANSWER = json.dumps(
    {
        "found": True,
        "answer": "Revenue was $100 million in FY2022.",
        "value": 100,
        "unit": "USD million",
        "sources": [{"doc_name": "APPLE_2022_10K", "page": 3}],
    }
)


def make(route_text: str) -> tuple[RoutedPipeline, FakeLLM, FakeLLM, RecordingSearcher]:
    router_llm = FakeLLM([route_text], price_in=0.10, price_out=0.50)
    answer_llm = FakeLLM([ANSWER])
    searcher = RecordingSearcher()
    pipe = RoutedPipeline(
        Router(router_llm, CATALOG), searcher, BaselinePipeline(searcher, answer_llm), top_k=5
    )
    return pipe, router_llm, answer_llm, searcher


def test_answer_route_searches_chosen_documents_with_standalone_question() -> None:
    pipe, rllm, allm, searcher = make(route_reply())
    r = pipe.answer("Apple revenue 2022?")
    assert r.decision is not None and r.decision.route == Route.ANSWER
    assert searcher.calls == [
        {"query": "What was Apple's revenue in FY2022?", "k": 5, "doc_names": ["APPLE_2022_10K"]}
    ]
    assert r.answer is not None and r.answer.value == 100
    assert len(rllm.calls) == 1 and len(allm.calls) == 1
    assert "Question: What was Apple's revenue in FY2022?" in allm.calls[0]["user"]
    assert r.reply is None


@pytest.mark.parametrize(
    "text",
    [
        route_reply(route="unrelated"),
        route_reply(route="advice"),
        route_reply(route="unclear", reason="Which company?"),
        route_reply(years=[2019]),  # not covered
        route_reply(companies=[], other_companies=["Tesla"]),  # not covered
    ],
)
def test_stop_routes_make_no_search_and_no_answer_call(text: str) -> None:
    pipe, _, allm, searcher = make(text)
    r = pipe.answer("x")
    assert searcher.calls == [] and allm.calls == []
    assert r.hits == [] and r.answer is None and r.reply
    assert r.cost_usd == pytest.approx(r.router_cost_usd)
    assert r.answer_cost_usd == pytest.approx(0.0)


def test_router_failure_gives_clear_error_and_no_search() -> None:
    pipe, rllm, allm, searcher = make("not json")
    r = pipe.answer("x")
    assert r.decision is not None and r.decision.route is None
    assert r.error and "invalid router JSON" in r.error
    assert len(rllm.calls) == 2 and searcher.calls == [] and allm.calls == []
    assert r.reply and "could not be processed" in r.reply


def test_step_costs_add_up() -> None:
    pipe, rllm, allm, _ = make(route_reply())
    r = pipe.answer("Apple revenue 2022?")
    assert r.router_cost_usd > 0 and r.answer_cost_usd > 0
    assert r.cost_usd == pytest.approx(r.router_cost_usd + r.answer_cost_usd)
    assert len(r.calls) == 2 and len(r.router_calls) == 1


def test_history_reaches_router() -> None:
    pipe, rllm, _, _ = make(route_reply(years=[2021]))
    pipe.answer("And 2021?", [Turn("user", "Apple revenue 2022?")])
    assert "user: Apple revenue 2022?" in rllm.calls[0]["user"]


# ---------- runner ----------


def question(qid: str) -> DevQuestion:
    return DevQuestion(
        id=qid,
        category="find_number",  # type: ignore[arg-type]
        turns=["Apple revenue 2022?"],
        expected_route="answer",  # type: ignore[arg-type]
        gold_answer="$100 million",
        evidence=[{"doc_name": "APPLE_2022_10K", "page": 3}],  # type: ignore[list-item]
        answer_source="table",  # type: ignore[arg-type]
        gold_value=100,
        gold_unit="USD million",
    )


def test_answerable_picks_ids() -> None:
    qs = [question("dev_0001"), question("dev_0002"), question("dev_0003")]
    assert [q.id for q in answerable(qs, ids=["dev_0003", "dev_0001"])] == ["dev_0001", "dev_0003"]


def test_runner_records_route_documents_and_step_costs(tmp_path: Path) -> None:
    pipe, _, _, _ = make(route_reply())
    rows, stopped = run([question("dev_0001")], pipe, max_cost_usd=1.0)
    assert not stopped
    row = rows[0]
    assert row["mark"] == "correct" and row["evidence_seen"]
    assert row["route"] == "answer" and row["doc_names"] == ["APPLE_2022_10K"]
    assert row["router_output"]["years"] == [2022]
    assert row["router_cost_usd"] > 0 and row["answer_cost_usd"] > 0
    meta = {
        "started": "20261121-150000",
        "model": "fake",
        "top_k": 5,
        "collection": "chunks",
        "stopped_by_cost_limit": False,
        "router_model": "fake-haiku",
        "year_rule": "A",
    }
    card = scorecard(rows, meta)
    assert "Routed scorecard" in card and "## Routes" in card and "APPLE_2022_10K" in card
    assert "Questions with a JSON retry: 0" in card  # router + answer = 2 calls, no retry
    folder = write_run(tmp_path, rows, meta)
    assert (folder / "results.json").exists()


def test_router_estimate_makes_no_call() -> None:
    est = estimate_router(
        [question("dev_0001")], lambda q: "rules " + q, "system", rough_tokens, 0.10, 0.50
    )
    assert est["router_input_tokens_total"] > 0
    assert est["router_cost_usd_worst_case"] == pytest.approx(
        2 * est["router_cost_usd_expected"], abs=1e-5
    )


class SplitTableSearcher(RecordingSearcher):
    """The search returns part 1 of a 2-part table; part 2 holds the needed row."""

    def search(
        self,
        query: str,
        company: str | None = None,
        k: int = 10,
        doc_names: Sequence[str] | None = None,
    ) -> list[Hit]:
        self.calls.append({"query": query, "k": k, "doc_names": doc_names})
        return [self._part(1)]

    def table_parts(self, table_id: str) -> list[Hit]:
        return [self._part(1), self._part(2)]

    @staticmethod
    def _part(n: int) -> Hit:
        return Hit(0.5, {
            "chunk_id": f"t{n}", "doc_name": "APPLE_2022_10K", "page": 3, "page_end": 3,
            "is_table": True, "table_id": "T", "table_part": n, "table_parts": 2,
            "text": "Net sales by segment " + ("Americas 100" if n == 1 else "Services 200"),
        })  # fmt: skip


@pytest.mark.parametrize(("cap", "expected_parts"), [(3, 2), (0, 1)])
def test_split_table_parts_reach_the_answer_prompt(cap: int, expected_parts: int) -> None:
    answer_llm = FakeLLM([ANSWER])
    searcher = SplitTableSearcher()
    pipe = RoutedPipeline(
        Router(FakeLLM([route_reply()], price_in=0.10, price_out=0.50), CATALOG),
        searcher, BaselinePipeline(searcher, answer_llm), top_k=5, max_extra_parts=cap,
    )  # fmt: skip
    result = pipe.answer("What were Apple's services sales in FY2022?")
    assert len(result.hits) == expected_parts
    assert result.added_table_parts == expected_parts - 1
    prompt = answer_llm.calls[-1]["user"]
    assert "Americas 100" in prompt
    assert ("Services 200" in prompt) == (cap > 0)
