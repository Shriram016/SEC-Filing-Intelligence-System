import json
from typing import Any

import pytest

from filing_rag.llm.client import LLMResult
from filing_rag.llm.fake import FakeLLM
from filing_rag.router.catalog import CatalogDoc, DocCatalog
from filing_rag.router.router import (
    ADVICE_REPLY,
    UNRELATED_REPLY,
    LLMRoute,
    Route,
    Router,
    Turn,
    build_schema,
    build_user,
    parse_output,
    reply_text,
)

CATALOG = DocCatalog(
    [
        CatalogDoc("APPLE_2021_10K", "Apple", "10-K", 2021),
        CatalogDoc("APPLE_2022_10K", "Apple", "10-K", 2022),
        CatalogDoc("APPLE_2023_10Q", "Apple", "10-Q", 2023),
        CatalogDoc("COSTCO_2024_10K", "Costco", "10-K", 2024),
        CatalogDoc("JNJ_2022_10K", "Johnson & Johnson", "10-K", 2022),
    ]
)


def reply(**kw: Any) -> str:
    base: dict[str, Any] = {
        "route": "answer",
        "standalone_question": "What was Apple's revenue in FY2022?",
        "reason": "Factual question about a filing.",
        "companies": ["Apple"],
        "other_companies": [],
        "years": [2022],
        "doc_type": None,
        "metric": "revenue",
    }
    base.update(kw)
    return json.dumps(base)


def router(*replies: Any) -> tuple[Router, FakeLLM]:
    fake = FakeLLM(list(replies), price_in=0.10, price_out=0.50)
    return Router(fake, CATALOG), fake


def result(text: str, stop: str = "end_turn") -> LLMResult:
    return LLMResult(text, 10, 10, 0.0, 0.0, "fake", stop)


# ---------- schema and prompt ----------


def test_schema_holds_exactly_the_catalog_companies() -> None:
    schema = build_schema(CATALOG.companies())
    enum = schema["properties"]["companies"]["items"]["enum"]
    assert enum == ["Apple", "Costco", "Johnson & Johnson"]
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    assert "not_covered" not in schema["properties"]["route"]["enum"]  # set by code only


def test_prompt_lists_companies_and_question() -> None:
    user = build_user("Apple revenue 2022?", ["Apple", "Costco"])
    assert "Companies in the collection: Apple; Costco" in user
    assert user.endswith("Question: Apple revenue 2022?")
    assert "Chat history" not in user


def test_prompt_keeps_only_recent_history() -> None:
    history = [Turn("user", f"q{i}") for i in range(10)]
    user = build_user("And 2021?", ["Apple"], history, max_turns=3)
    assert "user: q9" in user and "user: q7" in user and "user: q6" not in user
    assert build_user("x", ["Apple"], history, max_turns=0).count("Chat history") == 0


def test_history_goes_to_the_llm() -> None:
    r, fake = router(reply(years=[2021]))
    r.decide("And 2021?", [Turn("user", "Apple revenue 2022?"), Turn("assistant", "$394B")])
    assert "assistant: $394B" in fake.calls[0]["user"]
    assert fake.calls[0]["schema"] == r.schema


# ---------- routes ----------


def test_answer_route_selects_documents() -> None:
    r, _ = router(reply())
    d = r.decide("Apple revenue 2022?")
    assert d.route == Route.ANSWER
    assert d.doc_names == ["APPLE_2022_10K"]
    assert d.search_question == "What was Apple's revenue in FY2022?"
    assert reply_text(d) is None


def test_missing_year_uses_next_year() -> None:
    r, _ = router(reply(companies=["Costco"], years=[2023]))
    d = r.decide("Costco revenue 2023?")
    assert d.route == Route.ANSWER and d.doc_names == ["COSTCO_2024_10K"]


def test_year_rule_b() -> None:
    fake = FakeLLM([reply(years=[2021])])
    d = Router(fake, CATALOG, year_rule="B").decide("Apple revenue 2021?")
    assert d.doc_names == ["APPLE_2021_10K", "APPLE_2022_10K"]


@pytest.mark.parametrize(
    ("route", "text"),
    [("unrelated", UNRELATED_REPLY), ("advice", ADVICE_REPLY)],
)
def test_stop_routes_ignore_companies(route: str, text: str) -> None:
    r, _ = router(reply(route=route))
    d = r.decide("x")
    assert d.route == Route(route)
    assert d.selection is None and d.doc_names is None
    assert reply_text(d) == text


def test_unclear_route_asks_back() -> None:
    r, _ = router(reply(route="unclear", reason="Which company do you mean?", companies=[]))
    d = r.decide("What was revenue?")
    assert d.route == Route.UNCLEAR
    assert reply_text(d) == "Which company do you mean?"


def test_company_outside_collection_not_covered() -> None:
    r, _ = router(reply(companies=[], other_companies=["Tesla"]))
    d = r.decide("Tesla revenue 2022?")
    assert d.route == Route.NOT_COVERED
    assert reply_text(d) == "No filing for Tesla (not in the collection) in the collection."


def test_year_outside_catalog_not_covered() -> None:
    r, _ = router(reply(years=[2030]))
    d = r.decide("Apple revenue 2030?")
    assert d.route == Route.NOT_COVERED
    assert reply_text(d) == "No filing for Apple FY2030 in the collection."


def test_doc_type_named_is_a_filter() -> None:
    r, _ = router(reply(years=[2023], doc_type="10-Q"))
    d = r.decide("Apple 10-Q 2023 revenue?")
    assert d.doc_names == ["APPLE_2023_10Q"]
    r2, _ = router(reply(companies=["Costco"], years=[], doc_type="8-K"))
    d2 = r2.decide("Costco 8-K?")
    assert d2.route == Route.NOT_COVERED
    assert reply_text(d2) == "No filing for Costco (8-K) in the collection."


def test_no_company_means_no_filter() -> None:
    r, _ = router(reply(companies=[], years=[2022]))
    d = r.decide("Which company had the highest revenue in 2022?")
    assert d.route == Route.ANSWER and d.doc_names is None


# ---------- validation and retry ----------


def test_bad_json_retried_once_then_ok() -> None:
    r, fake = router("not json", reply())
    d = r.decide("Apple revenue 2022?")
    assert d.route == Route.ANSWER and d.error is None
    assert len(fake.calls) == 2 and len(d.calls) == 2


def test_bad_json_twice_gives_error() -> None:
    r, fake = router("not json")
    d = r.decide("Apple revenue 2022?")
    assert d.route is None and d.error and "invalid router JSON" in d.error
    assert len(fake.calls) == 2
    assert reply_text(d) is not None and "could not be processed" in reply_text(d)  # type: ignore[operator]


def test_parse_rejects_unknown_company() -> None:
    with pytest.raises(ValueError, match="not in the collection list"):
        parse_output(result(reply(companies=["Tesla"])), CATALOG.companies())


def test_parse_rejects_year_out_of_range_and_bad_doc_type() -> None:
    with pytest.raises(ValueError, match="years out of range"):
        parse_output(result(reply(years=[1999])), CATALOG.companies())
    with pytest.raises(ValueError, match="doc_type"):
        parse_output(result(reply(doc_type="proxy")), CATALOG.companies())


def test_parse_rejects_unclear_without_question() -> None:
    with pytest.raises(ValueError, match="clarifying"):
        parse_output(result(reply(route="unclear", reason=" ")), CATALOG.companies())


def test_parse_rejects_cut_off_and_refusal() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        parse_output(result(reply(), stop="max_tokens"), CATALOG.companies())
    with pytest.raises(ValueError, match="refused"):
        parse_output(result(reply(), stop="refusal"), CATALOG.companies())


def test_parse_removes_duplicates() -> None:
    out = parse_output(
        result(reply(companies=["Apple", "Apple"], years=[2022, 2022])), CATALOG.companies()
    )
    assert out.companies == ["Apple"] and out.years == [2022]
    assert out.route == LLMRoute.ANSWER


def test_cost_adds_up_over_retries() -> None:
    r, _ = router("bad", reply())
    d = r.decide("Apple revenue 2022?")
    assert d.cost_usd == pytest.approx(sum(c.cost_usd for c in d.calls))
    assert d.cost_usd > 0
