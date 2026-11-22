from typing import Any

import pytest

from filing_rag.baseline.pipeline import BaselineAnswer, Source
from filing_rag.evaluation.dev_set import DevQuestion
from filing_rag.evaluation.scoring import (
    FailureTag,
    Mark,
    evidence_seen,
    mark_number,
    normalise,
    score,
    sources_ok,
)
from filing_rag.search.searcher import Hit


def q(value: float | None = 1788, unit: str | None = "USD million", **kw: Any) -> DevQuestion:
    data: dict[str, Any] = {
        "id": "dev_0001", "category": "find_number", "turns": ["q?"], "expected_route": "answer",
        "gold_answer": "x", "evidence": [{"doc_name": "A_10K", "page": 91}],
        "answer_source": "table", "gold_value": value, "gold_unit": unit,
    }  # fmt: skip
    return DevQuestion(**(data | kw))


def ans(value: float | None, unit: str | None, text: str = "", found: bool = True,
        sources: list[tuple[str, int]] | None = None) -> BaselineAnswer:  # fmt: skip
    src = [Source(doc_name=d, page=p) for d, p in (sources or [])]
    return BaselineAnswer(found=found, answer=text, value=value, unit=unit, sources=src)


def hit(doc: str, page: int, page_end: int | None = None) -> Hit:
    return Hit(0.5, {"doc_name": doc, "page": page, "page_end": page_end or page})


@pytest.mark.parametrize(
    ("unit", "expected"),
    [("USD million", ("usd", 1e6)), ("$ billions", ("usd", 1e9)), ("USD thousand", ("usd", 1e3)),
     ("%", ("pct", 1.0)), ("percent", ("pct", 1.0)), ("basis points", ("pct", 0.01)),
     ("shares", ("count", 1.0)), ("million shares", ("count", 1e6)), (None, ("count", 1.0))],
)  # fmt: skip
def test_normalise_units(unit: str | None, expected: tuple[str, float]) -> None:
    assert normalise(1.0, unit) == expected


def test_same_amount_in_other_scale_is_correct() -> None:
    assert mark_number(q(), ans(1.79, "USD billion")) == Mark.CORRECT  # 0.1% off
    assert mark_number(q(), ans(1_788_000_000, "USD")) == Mark.CORRECT


def test_rounding_within_one_percent_only() -> None:
    assert mark_number(q(22.2, "%"), ans(22.18, "%")) == Mark.CORRECT
    assert mark_number(q(3.2, "%"), ans(3.3, "%")) == Mark.WRONG


def test_percent_never_matches_an_amount() -> None:
    assert mark_number(q(42.9, "%"), ans(42.9, "USD million")) == Mark.WRONG


def test_decrease_as_negative_or_in_words() -> None:
    assert mark_number(q(-4.7, "%"), ans(-4.7, "%")) == Mark.CORRECT
    assert mark_number(q(-4.7, "%"), ans(4.7, "%", "a decrease of 4.7%")) == Mark.CORRECT
    assert mark_number(q(-4.7, "%"), ans(4.7, "%", "an increase of 4.7%")) == Mark.WRONG


def test_wrong_number_not_found_and_missing_value_are_wrong() -> None:
    assert mark_number(q(), ans(1700, "USD million")) == Mark.WRONG
    assert mark_number(q(), ans(1788, "USD million", found=False)) == Mark.WRONG
    assert mark_number(q(), ans(None, None)) == Mark.WRONG
    assert mark_number(q(), None) == Mark.WRONG


def test_no_gold_value_means_hand_marking() -> None:
    assert mark_number(q(None, None), ans(1, "%")) == Mark.HAND


def test_evidence_seen_needs_every_page() -> None:
    two = q(evidence=[{"doc_name": "A_10K", "page": 91}, {"doc_name": "B_10K", "page": 5}])
    assert evidence_seen(two, [hit("A_10K", 90, 91), hit("B_10K", 5)])
    assert not evidence_seen(two, [hit("A_10K", 91)])


def test_source_check() -> None:
    hits = [hit("A_10K", 90, 91)]
    assert sources_ok(q(), ans(1, "x", sources=[("A_10K", 91)]), hits)
    assert sources_ok(q(), ans(1, "x", sources=[("A_10K", 90)]), hits)  # chunk start page
    assert not sources_ok(q(), ans(1, "x", sources=[("A_10K", 12)]), hits)
    assert not sources_ok(q(), ans(1, "x", sources=[("B_10K", 91)]), hits)
    assert not sources_ok(q(), None, hits)


def test_failure_tags() -> None:
    right = ans(1788, "USD million")
    wrong = ans(1, "USD million")
    assert score(q(), right, None, [hit("A_10K", 91)]).tag is None
    assert score(q(), wrong, None, [hit("A_10K", 91)]).tag == FailureTag.ANSWER_ERROR
    assert score(q(), wrong, None, [hit("A_10K", 5)]).tag == FailureTag.SEARCH_MISS
    broken = score(q(), None, "invalid JSON", [hit("A_10K", 91)])
    assert broken.tag == FailureTag.BROKEN_JSON and broken.mark == Mark.WRONG


def test_hand_marked_answer_has_no_tag_yet() -> None:
    s = score(q(None, None), ans(None, None, "because ..."), None, [hit("A_10K", 5)])
    assert s.mark == Mark.HAND and s.tag is None and not s.evidence_seen
