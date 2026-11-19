import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from filing_rag.evaluation.dev_set import DevQuestion, validate_dev_set


def _q(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "dev_0001",
        "category": "find_number",
        "turns": ["What was the FY2019 revenue of 3M?"],
        "expected_route": "answer",
        "gold_answer": "$32,136 million",
        "evidence": [{"doc_name": "3M_2019_10K", "page": 40}],
    }
    base.update(over)
    return base


def test_valid_answerable_question() -> None:
    q = DevQuestion.model_validate(_q())
    assert q.status == "draft"
    assert not q.held_out


@pytest.mark.parametrize(
    "over",
    [
        {"id": "q1"},
        {"gold_answer": None},
        {"evidence": []},
        {"expected_route": "unrelated"},
        {"category": "advice", "expected_route": "answer"},
        {"category": "multi_turn", "turns": ["only one"]},
        {"turns": []},
    ],
)
def test_invalid_questions(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DevQuestion.model_validate(_q(**over))


def test_refusal_question_needs_no_answer() -> None:
    q = DevQuestion.model_validate(
        _q(category="injection", expected_route="unrelated", gold_answer=None, evidence=[])
    )
    assert q.expected_route == "unrelated"


def test_validate_file_reports_errors_duplicates_and_overlaps(tmp_path: Path) -> None:
    p = tmp_path / "dev.jsonl"
    lines = [json.dumps(_q()), json.dumps(_q()), "{bad json", json.dumps(_q(id="dev_0002"))]
    p.write_text("\n".join(lines))
    r = validate_dev_set(p, locked_pages={("3M_2019_10K", 40)})
    assert len(r.questions) == 2
    assert len(r.errors) == 2
    assert len(r.locked_page_overlaps) == 2


def test_missing_file_is_empty(tmp_path: Path) -> None:
    r = validate_dev_set(tmp_path / "none.jsonl")
    assert r.questions == []
    assert r.errors == []
