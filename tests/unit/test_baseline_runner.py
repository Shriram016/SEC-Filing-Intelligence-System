import json
from pathlib import Path
from typing import Any

import pytest

from filing_rag.baseline.pipeline import BaselinePipeline
from filing_rag.evaluation.baseline import answerable, estimate, rough_tokens, run, write_run
from filing_rag.evaluation.dev_set import Category, DevQuestion, Route
from filing_rag.llm.fake import FakeLLM
from filing_rag.search.searcher import Hit


def question(qid: str, value: float | None, category: str = "find_number") -> DevQuestion:
    data: dict[str, Any] = {
        "id": qid, "category": category, "turns": [f"question {qid}"], "expected_route": "answer",
        "gold_answer": "gold", "evidence": [{"doc_name": "A_10K", "page": 3}],
        "answer_source": "table", "gold_value": value,
        "gold_unit": "USD million" if value is not None else None,
    }  # fmt: skip
    return DevQuestion(**data)


class FakeSearcher:
    def search(self, query: str, company: str | None = None, k: int = 10) -> list[Hit]:
        return [Hit(0.9, {"doc_name": "A_10K", "page": 3, "page_end": 3, "text": "Revenue 100"})]


def reply(value: float | None) -> str:
    src = [{"doc_name": "A_10K", "page": 3}]
    data = {"found": True, "answer": "because of x", "value": value, "unit": "USD million"}
    return json.dumps(data | {"sources": src})


def meta(started: str = "20261121-120000") -> dict[str, Any]:
    return {"started": started, "model": "fake", "top_k": 5, "collection": "chunks",
            "stopped_by_cost_limit": False}  # fmt: skip


def test_answerable_skips_other_routes_and_applies_limit() -> None:
    other = DevQuestion(
        id="dev_0009", category=Category.UNRELATED, turns=["x"], expected_route=Route.UNRELATED
    )
    qs = [question("dev_0001", 1), other, question("dev_0002", 2)]
    assert [q.id for q in answerable(qs)] == ["dev_0001", "dev_0002"]
    assert [q.id for q in answerable(qs, limit=1)] == ["dev_0001"]


def test_estimate_builds_real_prompts_without_llm_calls() -> None:
    fake = FakeLLM(["{}"])
    pipe = BaselinePipeline(FakeSearcher(), fake)
    est = estimate(
        [question("dev_0001", 1), question("dev_0002", 2)], pipe, rough_tokens, 2.0, 10.0
    )
    assert fake.calls == []
    assert est["questions"] == 2 and est["input_tokens_total"] > 0
    assert est["cost_usd_worst_case"] == pytest.approx(2 * est["cost_usd_expected"], abs=1e-4)


def test_run_scores_and_writes_three_files(tmp_path: Path) -> None:
    qs = [
        question("dev_0001", 100),
        question("dev_0002", 5),
        question("dev_0003", None, "explain_why"),
    ]
    pipe = BaselinePipeline(FakeSearcher(), FakeLLM([reply(100)]))
    rows, stopped = run(qs, pipe, max_cost_usd=2.0)
    assert not stopped
    assert [r["mark"] for r in rows] == ["correct", "wrong", "hand"]
    assert rows[1]["failure_tag"] == "answer_error" and rows[0]["sources_ok"]
    folder = write_run(tmp_path, rows, meta())
    assert {p.name for p in folder.iterdir()} == {
        "results.json",
        "scorecard.md",
        "text_answers_to_mark.md",
    }
    card = (folder / "scorecard.md").read_text(encoding="utf-8")
    assert "| all | 1/2 (50%) |" in card and "answer_error: 1" in card
    marks = (folder / "text_answers_to_mark.md").read_text(encoding="utf-8")
    assert "dev_0003" in marks and "dev_0001" not in marks


def test_cost_limit_stops_the_run() -> None:
    qs = [question(f"dev_000{i}", 100) for i in range(1, 6)]
    pipe = BaselinePipeline(FakeSearcher(), FakeLLM([reply(100)], price_in=1e6))  # $1 per token
    rows, stopped = run(qs, pipe, max_cost_usd=0.5)
    assert stopped and len(rows) == 1


def test_a_run_never_overwrites_an_earlier_run(tmp_path: Path) -> None:
    rows, _ = run(
        [question("dev_0001", 100)], BaselinePipeline(FakeSearcher(), FakeLLM([reply(100)])), 2.0
    )
    write_run(tmp_path, rows, meta())
    with pytest.raises(FileExistsError):
        write_run(tmp_path, rows, meta())
