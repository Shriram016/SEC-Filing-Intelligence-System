"""Offline tests for evaluation/eval_helpers.py — pure logic, no API calls."""

import pytest

from evaluation.eval_helpers import (
    METRICS_BY_TYPE,
    REFUSAL_STRING,
    UsageTracker,
    build_summary,
    check_passed,
    classify_outcome,
    coverage_from_verdicts,
    numbered_context_passages,
    parse_usage,
    refusal_flags,
)


# ── Refusal detection ────────────────────────────────────────────────────────

def test_exact_refusal_sentence():
    flags = refusal_flags(REFUSAL_STRING)
    assert flags["exact"] and flags["tolerant"] and not flags["with_extra_text"]


@pytest.mark.parametrize("answer", [
    "The context does not provide sufficient information about Apple's 2019 risks.",
    "I cannot answer this from the provided excerpts.",
    "Unit sales are not mentioned in the provided filings.",
    "There is no information about CEO pay in the passages.",
])
def test_reworded_refusals_are_caught(answer):
    flags = refusal_flags(answer)
    assert flags["tolerant"] and not flags["exact"]


def test_normal_answer_is_not_a_refusal():
    assert not refusal_flags("Meta's 2023 revenue was $134.9 billion, up 16%.")["tolerant"]


def test_refusal_followed_by_long_guess_is_flagged_for_manual_review():
    answer = "The context does not contain enough information. " + "However, roughly speaking " * 15
    flags = refusal_flags(answer)
    assert flags["tolerant"] and flags["with_extra_text"]


# ── Outcome and pass rules ───────────────────────────────────────────────────

def test_outcomes():
    assert classify_outcome(True, "") == "rejected"
    assert classify_outcome(False, REFUSAL_STRING) == "refused"
    assert classify_outcome(False, "Revenue was $5B.") == "answered"


@pytest.mark.parametrize("qtype, outcome, expected", [
    ("should_refuse", "refused", True),
    ("should_refuse", "rejected", True),    # any decline passes; the outcome label records the path
    ("should_refuse", "answered", False),
    ("invalid", "rejected", True),
    ("invalid", "answered", False),
    ("single_factual", "answered", None),   # scored by metrics, not a yes/no check
])
def test_check_passed(qtype, outcome, expected):
    assert check_passed(qtype, outcome) is expected


# ── Metric plan ──────────────────────────────────────────────────────────────

def test_metric_plan_matches_agreed_table():
    assert METRICS_BY_TYPE["single_factual"] == [
        "faithfulness", "answer_relevance", "context_precision", "context_recall", "ground_truth_coverage"]
    for comparison in ("cross_year", "cross_company"):
        assert "context_precision" not in METRICS_BY_TYPE[comparison]
        assert "ground_truth_coverage" in METRICS_BY_TYPE[comparison]
    assert METRICS_BY_TYPE["vague"] == ["faithfulness", "answer_relevance"]
    assert "should_refuse" not in METRICS_BY_TYPE and "invalid" not in METRICS_BY_TYPE


# ── Token usage ──────────────────────────────────────────────────────────────

def test_parse_usage():
    body = {"model": "llama-3.3-70b-versatile", "usage": {"prompt_tokens": 120, "completion_tokens": 30}}
    assert parse_usage(body) == ("llama-3.3-70b-versatile", 120, 30)
    assert parse_usage({"model": "x"}) is None
    assert parse_usage("not a dict") is None


def test_usage_tracker_totals():
    t = UsageTracker()
    t.set_query("Q01")
    t.add("scout", 100, 20, stage="pipeline:synthesis")
    t.current_stage = "judge:faithfulness"
    t.add("llama-70b", 1000, 200)
    t.set_query("Q02")
    t.add("scout", 50, 10, stage="pipeline:synthesis")

    total = t.total()
    assert (total["calls"], total["prompt_tokens"], total["completion_tokens"]) == (3, 1150, 230)
    q1 = t.total("Q01")
    assert (q1["calls"], q1["prompt_tokens"], q1["completion_tokens"]) == (2, 1100, 220)
    data = t.to_dict()
    assert data["by_model"]["scout"]["prompt_tokens"] == 150
    assert data["by_stage"]["judge:faithfulness"]["completion_tokens"] == 200


def test_usage_tracker_cost_in_dollars():
    # model-a: $1 per 1M input, $2 per 1M output. model-b has no price.
    t = UsageTracker(prices={"model-a": (1.0, 2.0)})
    t.set_query("Q01")
    t.add("model-a", 1_000_000, 500_000, stage="s")   # $1.00 + $1.00
    t.add("model-b", 5_000, 5_000, stage="s")         # unpriced
    t.set_query("Q02")
    t.add("model-a", 100_000, 0, stage="s")           # $0.10

    assert t.total()["cost_usd"] == 2.10
    assert t.total()["unpriced_calls"] == 1
    assert t.total("Q02")["cost_usd"] == 0.10
    data = t.to_dict()
    assert data["by_model"]["model-a"]["cost_usd"] == 2.10
    assert data["prices_per_million_tokens"] == {"model-a": [1.0, 2.0]}


# ── Summary ──────────────────────────────────────────────────────────────────

def test_summary_means_counts_and_unexpected_rejections():
    records = [
        {"query_id": "Q01", "query_type": "single_factual", "status": "evaluated",
         "scores": {"faithfulness": 1.0, "ground_truth_coverage": 0.5}, "metric_errors": {}},
        {"query_id": "Q02", "query_type": "single_factual", "status": "evaluated",
         "scores": {"faithfulness": 0.5, "ground_truth_coverage": None}, "metric_errors": {"ground_truth_coverage": "boom"}},
        {"query_id": "Q03", "query_type": "cross_year", "status": "unexpected_rejection"},
        {"query_id": "Q04", "query_type": "cross_year", "status": "pipeline_error", "error": "TimeoutError"},
        {"query_id": "Q25", "query_type": "should_refuse", "status": "evaluated", "outcome": "refused", "passed": True},
        {"query_id": "Q26", "query_type": "should_refuse", "status": "evaluated", "outcome": "answered", "passed": False},
    ]
    s = build_summary(records)
    single = s["by_category"]["single_factual"]
    assert single["n"] == 2 and single["n_scored"] == 2
    assert single["metrics"]["faithfulness"]["mean"] == 0.75
    assert single["metrics"]["ground_truth_coverage"]["n"] == 1      # the None is not counted
    assert single["metric_errors"] == ["Q02:ground_truth_coverage"]
    assert s["by_category"]["cross_year"]["unexpected_rejections"] == ["Q03"]
    assert s["by_category"]["cross_year"]["pipeline_errors"] == ["Q04"]
    assert s["by_category"]["cross_year"]["n"] == 2 and s["by_category"]["cross_year"]["n_scored"] == 0
    refuse = s["by_category"]["should_refuse"]
    assert refuse["checked"] == 2 and refuse["passed"] == 1
    assert refuse["outcomes"] == {"refused": 1, "answered": 1}
    assert s["overall_answer_categories"]["faithfulness"]["mean"] == 0.75


# ── Numbered passages shown to the judge ─────────────────────────────────────

def _chunk(text, company="Meta", year=2023, section_name="MD&A", group=None):
    return {"text": text, "company": company, "year": year, "section_name": section_name, "group": group}


def test_numbered_passages_labels_and_numbers():
    passages = numbered_context_passages([_chunk(" Revenue $134,902 ", section_name="MD&A"),
                                          _chunk("Net income $39,098", year=2022)])
    assert passages[0] == '[1] Meta | 2023 | MD&A\n"Revenue $134,902"'
    assert passages[1].startswith("[2] Meta | 2022 | MD&A")


def test_numbered_passages_follow_synthesizer_numbering_exactly():
    """The judge's "[N]" must be the answering model's "[N]", with and without sub-query groups."""
    import re
    from synthesis.synthesizer import Synthesizer

    flat = [_chunk("a"), _chunk("b", company="Apple"), _chunk("c", year=2021)]
    grouped = [_chunk("a", group="Apple 2022"), _chunk("b", group="Apple 2022"),
               _chunk("c", company="Microsoft", group="Microsoft 2022"),
               _chunk("d", company="Microsoft", group="Microsoft 2022")]
    for chunks in (flat, grouped):
        shown_to_answerer = re.findall(r"(?m)^\[(\d+)\] (.+)$", Synthesizer._build_context(chunks))
        shown_to_judge = [re.match(r"\[(\d+)\] (.+)", p).groups() for p in numbered_context_passages(chunks)]
        assert shown_to_judge == shown_to_answerer


# ── Ground-truth coverage arithmetic ─────────────────────────────────────────

@pytest.mark.parametrize("verdicts, expected", [
    ([True, True], 1.0),
    ([True, False], 0.5),
    ([False, False, False], 0.0),
    ([True, True, False], 0.6667),
    ([], None),
])
def test_coverage_from_verdicts(verdicts, expected):
    assert coverage_from_verdicts(verdicts) == expected


# ── Synthesizer answer style switch ──────────────────────────────────────────

def test_answer_style_switch_keeps_original_prompt_and_refusal_sentence():
    from synthesis.synthesizer import CONCISE_STYLE_RULES, SYSTEM_PROMPT, build_system_prompt

    assert build_system_prompt("free") == SYSTEM_PROMPT                      # old behaviour unchanged
    concise = build_system_prompt("concise")
    assert concise == SYSTEM_PROMPT + CONCISE_STYLE_RULES
    assert REFUSAL_STRING in concise and REFUSAL_STRING in SYSTEM_PROMPT      # refusal wording is in both
