"""Router check (Q109): route, steps, documents, gold page. Fake router LLM, no cost."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from filing_rag.evaluation.dev_set import DevQuestion
from filing_rag.evaluation.router_check import check_one, run_check, summary, write_check
from filing_rag.llm.fake import FakeLLM
from filing_rag.router.catalog import CatalogDoc, DocCatalog
from filing_rag.router.router import RouteDecision, Router
from filing_rag.search.searcher import Hit

CATALOG = DocCatalog(
    [
        CatalogDoc("APPLE_2018_10K", "Apple", "10-K", 2018),
        CatalogDoc("APPLE_2019_10K", "Apple", "10-K", 2019),
        CatalogDoc("COSTCO_2019_10K", "Costco", "10-K", 2019),
    ]
)


def question(
    qid: str = "dev_0037",
    gold: list[tuple[str | None, int | None]] | None = None,
    evidence: str = "APPLE_2019_10K",
    page: int = 40,
) -> DevQuestion:
    gold = gold if gold is not None else [("Apple", 2019), ("Apple", 2018)]
    return DevQuestion.model_validate({
        "id": qid, "category": "calculate", "turns": ["Apple cash from operations 2019 vs 2018?"],
        "expected_route": "answer", "gold_answer": "-10.4%", "answer_source": "table",
        "evidence": [{"doc_name": evidence, "page": page}],
        "gold_steps": [{"company": c, "year": y} for c, y in gold],
    })  # fmt: skip


def reply(steps: list[tuple[str | None, int | None]], **kw: Any) -> str:
    return json.dumps({
        "route": "answer", "standalone_question": "Apple operating cash flow FY2019 vs FY2018?",
        "reason": "factual", "doc_type": None, "metric": "cash",
        "steps": [{"company": c, "year": y, "search": f"{c} cash {y}"} for c, y in steps],
    } | kw)  # fmt: skip


def decide(text: str) -> RouteDecision:
    return Router(FakeLLM([text], price_in=0.10, price_out=0.50), CATALOG).decide("q")


def hit(doc: str, page: int) -> Hit:
    return Hit(0.9, {"doc_name": doc, "page": page, "text": "x"})


def test_correct_plan_documents_and_page() -> None:
    d = decide(reply([("Apple", 2018), ("Apple", 2019)]))  # order does not matter
    row = check_one(question(), d, [[hit("APPLE_2018_10K", 3)], [hit("APPLE_2019_10K", 40)]])
    assert row["route_ok"] and row["steps_ok"] and row["docs_ok"] and row["page_found"]
    assert row["missing_pairs"] == [] and row["extra_pairs"] == []
    assert row["step_pages"] == [["APPLE_2018_10K p3"], ["APPLE_2019_10K p40"]]
    assert row["cost_usd"] > 0 and row["llm_calls"] == 1
    assert row["doc_type"] is None and row["router_reason"] == "factual"


def test_row_saves_the_router_doc_type_and_reason() -> None:
    d = decide(reply([("Apple", 2019)], doc_type="10-K", reason="named the 10-K"))
    row = check_one(question(), d, [[hit("APPLE_2019_10K", 7)]])
    assert row["doc_type"] == "10-K" and row["router_reason"] == "named the 10-K"
    assert "named the 10-K" in summary([row], {"started": "t"})


def test_a_missing_step_is_a_wrong_plan_but_documents_can_still_be_covered() -> None:
    d = decide(reply([("Apple", 2019)]))
    row = check_one(question(), d, [[hit("APPLE_2019_10K", 7)]])
    assert row["steps_ok"] is False and row["missing_pairs"] == ["Apple 2018"]
    assert row["docs_ok"] is True and row["page_found"] is False


def test_wrong_company_misses_the_gold_document() -> None:
    d = decide(reply([("Costco", 2019)]))
    row = check_one(question(gold=[("Apple", 2019)]), d, [[hit("COSTCO_2019_10K", 40)]])
    assert row["steps_ok"] is False and row["extra_pairs"] == ["Costco 2019"]
    assert row["docs_ok"] is False and row["missing_docs"] == ["APPLE_2019_10K"]
    assert row["page_found"] is False


def test_wrong_route_fails_every_check() -> None:
    d = decide(reply([], route="unclear", reason="Which year?"))
    row = check_one(question(), d, [])
    assert not row["route_ok"] and row["steps_ok"] is False
    assert row["docs_ok"] is False and row["page_found"] is False


def test_no_company_step_means_no_filter_and_counts_as_covered() -> None:
    d = decide(reply([(None, 2019)]))
    row = check_one(question(gold=[(None, 2019)]), d, [[hit("APPLE_2019_10K", 40)]])
    assert row["steps_ok"] and row["docs_ok"] and row["page_found"]


def test_run_stops_at_the_cost_limit_and_writes_a_summary(tmp_path: Path) -> None:
    router = Router(FakeLLM([reply([("Apple", 2019), ("Apple", 2018)])] * 3,
                            price_in=0.10, price_out=0.50), CATALOG)  # fmt: skip
    seen: list[RouteDecision] = []

    def retrieve(d: RouteDecision) -> list[list[Hit]]:
        seen.append(d)
        return [[hit("APPLE_2019_10K", 40)], [hit("APPLE_2018_10K", 1)]]

    qs = [question("dev_0001"), question("dev_0002"), question("dev_0003")]
    rows, stopped = run_check(qs, router, retrieve, max_cost_usd=1.0)
    assert not stopped and len(rows) == 3 and len(seen) == 3
    rows2, stopped2 = run_check(qs, router, retrieve, max_cost_usd=0.0)
    assert stopped2 and rows2 == []
    meta = {"started": "20261123-120000", "router_model": "fake", "collection": "c", "top_k": 5,
            "stopped_by_cost_limit": False}  # fmt: skip
    text = summary(rows, meta)
    assert "| Steps = gold steps | 3/3 (100%) | - | 3/3 (100%) |" in text
    assert "None." in text  # no wrong plans
    folder = write_check(tmp_path, rows, meta)
    assert (folder / "results.json").exists() and (folder / "summary.md").exists()
    with pytest.raises(FileExistsError):
        write_check(tmp_path, rows, meta)  # never overwrites a run


def test_dev_set_gold_steps_rules() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        question(gold=[("Apple", 2019), ("Apple", 2019)])
    with pytest.raises(ValidationError, match="non-empty"):
        question(gold=[])
    with pytest.raises(ValidationError, match="only answerable"):
        DevQuestion.model_validate({
            "id": "dev_0099", "category": "advice", "turns": ["Buy?"], "expected_route": "advice",
            "gold_steps": [{"company": "Apple", "year": 2019}],
        })  # fmt: skip
