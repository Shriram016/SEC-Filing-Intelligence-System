from typing import Any

import pytest

from filing_rag.evaluation.dev_set import Category, DevQuestion, Route
from filing_rag.evaluation.retrieval import (
    checkable,
    evaluate,
    grouped,
    has_number,
    metrics,
    number_patterns,
    number_rank,
    page_rank,
    render_markdown,
)
from filing_rag.search.searcher import Hit

COMPANY = {"A_10K": "A", "B_10K": "B"}


def hit(doc: str, page: int, page_end: int | None = None, text: str = "t") -> Hit:
    return Hit(0.5, {"doc_name": doc, "page": page, "page_end": page_end or page, "text": text})


class FakeSearcher:
    """Returns fixed results per (query, company) and records the calls."""

    def __init__(self, table: dict[tuple[str, str | None], list[Hit]]) -> None:
        self.table = table
        self.calls: list[tuple[str, str | None, int]] = []

    def search(self, query: str, company: str | None = None, k: int = 10) -> list[Hit]:
        self.calls.append((query, company, k))
        return self.table.get((query, company), [])[:k]


def question(qid: str, text: str, evidence: list[tuple[str, int]], **kw: Any) -> DevQuestion:
    data: dict[str, Any] = {
        "id": qid,
        "category": "find_number",
        "turns": [text],
        "expected_route": "answer",
        "gold_answer": "1",
        "evidence": [{"doc_name": d, "page": p} for d, p in evidence],
        "answer_source": "table",
    }
    return DevQuestion(**(data | kw))


def test_page_rank_finds_first_covering_chunk() -> None:
    hits = [hit("A_10K", 1), hit("B_10K", 4, 6), hit("A_10K", 5)]
    assert page_rank(hits, "B_10K", 5) == 2
    assert page_rank(hits, "A_10K", 5) == 3
    assert page_rank(hits, "A_10K", 9) is None


def test_filtered_run_searches_per_company() -> None:
    q = question("dev_0001", "rev?", [("A_10K", 5), ("B_10K", 7)], category="compare_companies")
    s = FakeSearcher(
        {("rev?", "A"): [hit("A_10K", 5)], ("rev?", "B"): [hit("A_10K", 1), hit("B_10K", 7)]}
    )
    [r] = evaluate([q], s, COMPANY.__getitem__, use_filter=True, k=10)
    assert r.ranks == [1, 2] and r.rank == 2
    assert [c[1] for c in s.calls] == ["A", "B"]


def test_same_company_is_searched_once() -> None:
    q = question("dev_0001", "rev?", [("A_10K", 5), ("A_10K", 9)])
    s = FakeSearcher({("rev?", "A"): [hit("A_10K", 9), hit("A_10K", 5)]})
    [r] = evaluate([q], s, COMPANY.__getitem__)
    assert r.ranks == [2, 1] and len(s.calls) == 1


def test_question_misses_when_one_evidence_page_is_missing() -> None:
    q = question("dev_0001", "rev?", [("A_10K", 5), ("B_10K", 7)], category="compare_companies")
    s = FakeSearcher({("rev?", "A"): [hit("A_10K", 5)]})
    [r] = evaluate([q], s, COMPANY.__getitem__)
    assert r.ranks == [1, None] and r.rank is None


def test_unfiltered_run_makes_one_search() -> None:
    q = question("dev_0001", "rev?", [("A_10K", 5), ("B_10K", 7)], category="compare_companies")
    s = FakeSearcher({("rev?", None): [hit("B_10K", 7), hit("A_10K", 5)]})
    [r] = evaluate([q], s, COMPANY.__getitem__, use_filter=False)
    assert r.ranks == [2, 1] and s.calls == [("rev?", None, 10)]


def test_non_answer_questions_are_skipped() -> None:
    q = DevQuestion(
        id="dev_0002",
        category=Category.UNRELATED,
        turns=["weather?"],
        expected_route=Route.UNRELATED,
    )
    assert evaluate([q], FakeSearcher({}), COMPANY.__getitem__) == []


def test_last_turn_is_the_query() -> None:
    q = question("dev_0001", "x", [("A_10K", 5)], category="multi_turn", turns=["first", "second"])
    s = FakeSearcher({})
    evaluate([q], s, COMPANY.__getitem__)
    assert s.calls[0][0] == "second"


def test_metrics_hit_at_k_and_mrr() -> None:
    qs = [question(f"dev_000{i}", f"q{i}", [("A_10K", 5)]) for i in range(1, 5)]
    table: dict[tuple[str, str | None], list[Hit]] = {
        ("q1", "A"): [hit("A_10K", 5)],  # rank 1
        ("q2", "A"): [hit("A_10K", 1), hit("A_10K", 5)],  # rank 2
        ("q3", "A"): [hit("A_10K", 1)] * 5 + [hit("A_10K", 5)],  # rank 6
        ("q4", "A"): [],  # miss
    }
    results = evaluate(qs, FakeSearcher(table), COMPANY.__getitem__)
    m = metrics(results)
    assert m["n"] == 4
    assert m["hit@1"] == 0.25 and m["hit@5"] == 0.5 and m["hit@10"] == 0.75
    assert m["mrr@10"] == round((1 + 0.5 + 1 / 6) / 4, 3)


def test_metrics_of_empty_list() -> None:
    assert metrics([]) == {"n": 0}


def test_grouped_splits_by_source_and_category() -> None:
    qs = [
        question("dev_0001", "q1", [("A_10K", 5)]),
        question("dev_0002", "q2", [("A_10K", 5)], answer_source="text", category="explain_why"),
    ]
    results = evaluate(qs, FakeSearcher({("q1", "A"): [hit("A_10K", 5)]}), COMPANY.__getitem__)
    g = grouped(results)
    assert g["all"]["n"] == 2
    assert g["answer_source"]["table"]["hit@1"] == 1.0
    assert g["answer_source"]["text"]["hit@1"] == 0.0
    assert set(g["category"]) == {"find_number", "explain_why"}
    md = render_markdown("T", g, results)
    assert "| answer_source=table | 1 | 1.0 |" in md
    assert "| dev_0002 | explain_why | text | - | n/a | A_10K p5 |" in md


# ---------- chunk-level check: gold number in the chunk (Q105) ----------


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (1788, "Pension liability   $  1,788   $ 1,650"),
        (1788, "liability of 1788 million"),
        (1499995, "Cash and cash equivalents  $ 1,499,995  $ 1,446,581"),
        (15.48, "Diluted earnings per share  $ 15.48"),
        (112.5, "a spread of 112.5 basis points"),
        (82, "about 82% of revenue"),
        (3000000000, "3,000,000,000 shares authorized"),
        (3000000000, "authorized 3 billion shares"),
        (850000000, "a $850 million settlement"),
        (1.7, "backlog of $1.7 billion"),
        (-10.4, "decreased (10.4)%"),
        (76, "costs of $76.0 million"),
    ],
)
def test_number_patterns_find_printed_forms(value: float, text: str) -> None:
    assert has_number(text, number_patterns(value))


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (1788, "Total 11,788 and 1,7880"),  # part of a longer number
        (82, "page 182 and 8.2"),
        (15.48, "15.480 and 115.48"),
        (76, "7.6 and 760"),
        (1499995, "1,499,99"),
    ],
)
def test_number_patterns_do_not_match_parts_of_other_numbers(value: float, text: str) -> None:
    assert not has_number(text, number_patterns(value))


def test_number_rank_needs_the_evidence_page_and_the_number() -> None:
    hits = [
        hit("A_10K", 4, text="Revenue 1,788"),  # number, wrong page
        hit("A_10K", 5, text="Revenue grew because of iPhone"),  # right page, no number
        hit("A_10K", 5, text="Revenues  1,788  1,650"),  # right page + number
    ]
    assert number_rank(hits, "A_10K", 5, number_patterns(1788)) == 3
    assert page_rank(hits, "A_10K", 5) == 2  # the page check passes earlier
    assert number_rank(hits[:2], "A_10K", 5, number_patterns(1788)) is None


def test_only_find_number_questions_are_value_checked() -> None:
    fn = question("dev_0001", "q1", [("A_10K", 5)], gold_value=1788, gold_unit="USD million")
    calc = question(
        "dev_0002", "q2", [("A_10K", 5)], category="calculate",
        gold_value=42.9, gold_unit="%",
    )  # fmt: skip
    no_gold = question("dev_0003", "q3", [("A_10K", 5)])
    assert checkable(fn) and not checkable(calc) and not checkable(no_gold)


def test_value_metrics_show_right_page_wrong_chunk() -> None:
    """The page is found at rank 1, but the chunk with the number is at rank 6."""
    q = question("dev_0001", "q1", [("A_10K", 5)], gold_value=1788, gold_unit="USD million")
    other = question("dev_0002", "q2", [("A_10K", 5)], answer_source="text", category="explain_why")
    hits = [hit("A_10K", 5, text="Narrative")] * 5 + [hit("A_10K", 5, text="Revenues 1,788")]
    s = FakeSearcher({("q1", "A"): hits, ("q2", "A"): hits})
    results = evaluate([q, other], s, COMPANY.__getitem__)
    assert results[0].rank == 1 and results[0].value_rank == 6
    assert results[1].value_ranks is None  # explain-why: not checked
    m = metrics(results)
    assert m["hit@5"] == 1.0
    assert m["value_n"] == 1 and m["value_hit@5"] == 0.0 and m["value_hit@10"] == 1.0
    md = render_markdown("T", grouped(results), results)
    assert "| dev_0001 | find_number | table | 1 | 6 | A_10K p5 |" in md


def test_value_check_in_unfiltered_run() -> None:
    q = question("dev_0001", "q1", [("A_10K", 5)], gold_value=15.48, gold_unit="USD")
    s = FakeSearcher({("q1", None): [hit("A_10K", 5, text="EPS $15.48")]})
    [r] = evaluate([q], s, COMPANY.__getitem__, use_filter=False)
    assert r.value_ranks == [1]
