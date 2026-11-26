import json

import pytest

from filing_rag.config import Settings
from filing_rag.evaluation.dev_set import Category, DevQuestion, Evidence, Route
from filing_rag.evaluation.fb_dev import fb_id, load_fb_dev_questions, parse_gold, to_dev_question
from filing_rag.evaluation.locked import SPLIT_NAME


def row(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "financebench_id": "financebench_id_03029",
        "company": "3M",
        "doc_name": "3M_2018_10K",
        "question_type": "metrics-generated",
        "question_reasoning": "Information extraction",
        "question": "What is the FY2018 capital expenditure amount (in USD millions) for 3M?",
        "answer": "$1577.00",
        "justification": "Purchases of PP&E.",
        "evidence": [{"doc_name": "3M_2018_10K", "evidence_page_num": "59",
                      "evidence_text": "x"}],
    }  # fmt: skip
    return base | kw


@pytest.mark.parametrize(
    ("answer", "question", "expected"),
    [
        ("$1577.00", "amount (in USD millions)?", (1577.0, "USD million")),
        ("$59268.00", "Answer in USD thousands.", (59268.0, "USD thousand")),
        ("$1,616", "net AR?", (1616.0, "USD")),
        ("2.8%", "growth?", (2.8, "%")),
        ("-14.76%", "rate?", (-14.76, "%")),
        ("0.83", "ratio?", (0.83, "ratio")),
        ("$-473.00", "in USD millions", (-473.0, "USD million")),
        ("Yes. It grew.", "x", (None, None)),
        ("The quick ratio improved from 0.67 to 0.69", "x", (None, None)),
    ],
)
def test_parse_gold(answer: str, question: str, expected: tuple[float | None, str | None]) -> None:
    assert parse_gold(answer, question) == expected


def test_metrics_row_becomes_a_code_marked_question_with_viewer_pages() -> None:
    q = to_dev_question(row())
    assert q.id == "fb_03029" and q.source == "financebench"
    assert q.category == Category.FB_METRICS and q.expected_route == Route.ANSWER
    assert q.evidence[0].page == 60  # 0-based 59 → viewer page 60
    assert (q.gold_value, q.gold_unit) == (1577.0, "USD million")
    assert q.answer_source is None and q.status == "confirmed"
    assert "Purchases of PP&E" in q.notes


def test_judgement_rows_are_not_code_marked_and_duplicate_pages_merge() -> None:
    ev = {"doc_name": "D", "evidence_page_num": 3, "evidence_text": "x"}
    q = to_dev_question(row(question_type="domain-relevant", answer="0", evidence=[ev, ev]))
    assert q.category == Category.FB_DOMAIN
    assert q.gold_value is None and len(q.evidence) == 1


def test_ids_and_the_model_rules() -> None:
    assert fb_id("financebench_id_00941") == "fb_00941"
    with pytest.raises(ValueError):
        DevQuestion(id="fb_1", category=Category.FB_NOVEL, turns=["q"],
                    expected_route=Route.ANSWER)  # fmt: skip
    with pytest.raises(ValueError, match="answer_source"):  # Claude questions still need it
        DevQuestion(id="dev_0001", category=Category.FIND_NUMBER, turns=["q"],
                    expected_route=Route.ANSWER, gold_answer="a",
                    evidence=[Evidence(doc_name="D", page=1)])  # fmt: skip


def test_load_reads_only_the_fb_dev_file(settings: Settings) -> None:
    rows = [row(financebench_id=f"financebench_id_{i:05d}") for i in (1, 2)]
    settings.fb_dev_file.parent.mkdir(parents=True)
    settings.fb_dev_file.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    settings.eval_dir.mkdir(parents=True, exist_ok=True)
    split = {"dev_ids": [r["financebench_id"] for r in rows], "closed_ids": []}
    (settings.eval_dir / SPLIT_NAME).write_text(json.dumps(split), encoding="utf-8")
    qs = load_fb_dev_questions(settings)
    assert [q.id for q in qs] == ["fb_00001", "fb_00002"]
