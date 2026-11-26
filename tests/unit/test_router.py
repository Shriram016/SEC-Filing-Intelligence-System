import json
from typing import Any

import pytest

from filing_rag.llm.client import LLMResult
from filing_rag.llm.fake import FakeLLM
from filing_rag.router.catalog import CatalogDoc, DocCatalog, Selection
from filing_rag.router.router import (
    ADVICE_REPLY,
    NO_COMPANY_REPLY,
    TOO_MANY_STEPS_REPLY,
    UNRELATED_REPLY,
    LLMRoute,
    Route,
    Router,
    Turn,
    build_schema,
    build_user,
    combine,
    parse_output,
    reply_text,
    step_rows,
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


def step(
    company: str | None = "Apple", year: int | None = 2022, search: str = ""
) -> dict[str, Any]:
    return {"company": company, "year": year,
            "search": search or f"{company} revenue {year}"}  # fmt: skip


def reply(**kw: Any) -> str:
    base: dict[str, Any] = {
        "route": "answer",
        "standalone_question": "What was Apple's revenue in FY2022?",
        "reason": "Factual question about a filing.",
        "steps": [step()],
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
    item = schema["properties"]["steps"]["items"]
    enum = item["properties"]["company"]["anyOf"][0]["enum"]
    assert enum == ["Apple", "Costco", "Johnson & Johnson"]
    assert set(schema["required"]) == set(schema["properties"])
    assert set(item["required"]) == set(item["properties"]) == {"company", "year", "search"}
    assert schema["additionalProperties"] is False and item["additionalProperties"] is False
    assert "other_companies" not in schema["properties"]  # removed: the list is the scope
    assert "not_covered" in schema["properties"]["route"]["enum"]  # company outside the list


def test_prompt_lists_companies_and_question() -> None:
    user = build_user("Apple revenue 2022?", ["Apple", "Costco"])
    assert "Companies in the collection: Apple; Costco" in user
    assert "one step for each company + year pair" in user
    assert user.endswith("Question: Apple revenue 2022?")
    assert "Chat history" not in user


def test_prompt_keeps_only_recent_history() -> None:
    history = [Turn("user", f"q{i}") for i in range(10)]
    user = build_user("And 2021?", ["Apple"], history, max_turns=3)
    assert "user: q9" in user and "user: q7" in user and "user: q6" not in user
    assert build_user("x", ["Apple"], history, max_turns=0).count("Chat history") == 0


def test_history_goes_to_the_llm() -> None:
    r, fake = router(reply(steps=[step(year=2021)]))
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
    r, _ = router(reply(steps=[step("Costco", 2023)]))
    d = r.decide("Costco revenue 2023?")
    assert d.route == Route.ANSWER and d.doc_names == ["COSTCO_2024_10K"]


def test_year_rule_b() -> None:
    fake = FakeLLM([reply(steps=[step(year=2021)])])
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
    assert d.selection is None and d.doc_names is None and d.steps == []
    assert reply_text(d) == text


def test_unclear_route_asks_back() -> None:
    r, _ = router(reply(route="unclear", reason="Which company do you mean?", steps=[]))
    d = r.decide("What was revenue?")
    assert d.route == Route.UNCLEAR
    assert reply_text(d) == "Which company do you mean?"


def test_company_outside_collection_not_covered() -> None:
    r, fake = router(reply(route="not_covered", steps=[]))
    d = r.decide("Tesla revenue 2022?")
    assert d.route == Route.NOT_COVERED and d.selection is None
    assert reply_text(d) == NO_COMPANY_REPLY
    assert "regulator, partner, bank, fund or union" in fake.calls[0]["user"]


def test_year_outside_catalog_not_covered() -> None:
    r, _ = router(reply(steps=[step(year=2030)]))
    d = r.decide("Apple revenue 2030?")
    assert d.route == Route.NOT_COVERED
    assert reply_text(d) == "No filing for Apple FY2030 in the collection."


def test_doc_type_named_is_a_filter() -> None:
    r, _ = router(reply(steps=[step(year=2023)], doc_type="10-Q"))
    d = r.decide("Apple 10-Q 2023 revenue?")
    assert d.doc_names == ["APPLE_2023_10Q"]
    # no Costco 8-K → all Costco documents (the named type is a preference, not a refusal)
    r2, _ = router(reply(steps=[step("Costco", None)], doc_type="8-K"))
    d2 = r2.decide("Costco 8-K?")
    assert d2.route == Route.ANSWER
    assert d2.doc_names == ["COSTCO_2024_10K"]


def test_no_company_means_no_filter() -> None:
    r, _ = router(reply(steps=[step(None, 2022)]))
    d = r.decide("Which company had the highest revenue in 2022?")
    assert d.route == Route.ANSWER and d.doc_names is None


# ---------- steps (Q109) ----------


def test_two_years_give_two_steps_with_their_own_documents() -> None:
    r, _ = router(reply(steps=[step(year=2021), step(year=2022)]))
    d = r.decide("Apple revenue 2021 vs 2022?")
    assert d.route == Route.ANSWER
    assert [(s.company, s.year, s.doc_names) for s in d.steps] == [
        ("Apple", 2021, ["APPLE_2021_10K"]), ("Apple", 2022, ["APPLE_2022_10K"])]  # fmt: skip
    assert d.doc_names == ["APPLE_2021_10K", "APPLE_2022_10K"]  # union, for the logs
    assert d.searches() == [("Apple revenue 2021", ["APPLE_2021_10K"]),
                            ("Apple revenue 2022", ["APPLE_2022_10K"])]  # fmt: skip


def test_one_step_searches_with_the_standalone_question() -> None:
    r, _ = router(reply(steps=[step(search="Apple net sales FY2022")]))
    d = r.decide("Apple revenue 2022?")
    assert d.searches() == [("What was Apple's revenue in FY2022?", ["APPLE_2022_10K"])]


def test_two_companies_give_steps_per_company() -> None:
    r, _ = router(reply(steps=[step("Apple", 2022), step("Johnson & Johnson", 2022)]))
    d = r.decide("Apple vs JNJ revenue 2022?")
    assert [s.doc_names for s in d.steps] == [["APPLE_2022_10K"], ["JNJ_2022_10K"]]
    assert step_rows(d)[1] == {"company": "Johnson & Johnson", "year": 2022,
                               "search": "Johnson & Johnson revenue 2022",
                               "doc_names": ["JNJ_2022_10K"]}  # fmt: skip


def test_one_uncovered_step_makes_the_question_not_covered() -> None:
    r, _ = router(reply(steps=[step(year=2022), step(year=2030)]))
    d = r.decide("Apple revenue 2022 vs 2030?")
    assert d.route == Route.NOT_COVERED
    assert reply_text(d) == "No filing for Apple FY2030 in the collection."


def test_more_than_four_steps_asks_to_narrow_and_drops_nothing() -> None:
    steps = [step(c, y) for c in ("Apple", "Costco", "Johnson & Johnson") for y in (2021, 2022)]
    r, fake = router(reply(steps=steps))
    d = r.decide("Revenue of three companies in 2021 and 2022?")
    assert d.route == Route.UNCLEAR and d.too_many_steps
    assert reply_text(d) == TOO_MANY_STEPS_REPLY and "4" in TOO_MANY_STEPS_REPLY
    assert d.steps == [] and len(fake.calls) == 1  # no retry, no search


def test_answer_without_steps_is_invalid_and_retried() -> None:
    r, fake = router(reply(steps=[]), reply())
    d = r.decide("Apple revenue 2022?")
    assert d.route == Route.ANSWER and len(fake.calls) == 2


def test_combine_without_filter_and_missing() -> None:
    a = Selection(["A"], [])
    b = Selection(None, [("X", 2020)])
    assert combine([a, b]) == Selection(None, [("X", 2020)])
    assert combine([a, Selection(["B", "A"])]).doc_names == ["A", "B"]
    assert combine([]).doc_names is None


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
        parse_output(result(reply(steps=[step("Tesla")])), CATALOG.companies())


def test_parse_rejects_year_out_of_range_and_bad_doc_type() -> None:
    with pytest.raises(ValueError, match="year out of range"):
        parse_output(result(reply(steps=[step(year=1999)])), CATALOG.companies())
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


def test_parse_removes_duplicate_steps() -> None:
    out = parse_output(
        result(reply(steps=[step(), step(search="other text"), step(year=2021)])),
        CATALOG.companies(),
    )
    assert [s.pair for s in out.steps] == [("Apple", 2022), ("Apple", 2021)]
    assert out.companies == ["Apple"] and out.years == [2022, 2021]
    assert out.route == LLMRoute.ANSWER


def test_cost_adds_up_over_retries() -> None:
    r, _ = router("bad", reply())
    d = r.decide("Apple revenue 2022?")
    assert d.cost_usd == pytest.approx(sum(c.cost_usd for c in d.calls))
    assert d.cost_usd > 0
