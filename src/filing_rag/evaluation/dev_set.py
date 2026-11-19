"""Dev eval set: questions drafted by Claude and confirmed by the user (docs/v3/evaluation.md).

One JSON object per line in `eval/dev_set.jsonl`. `validate_dev_set()` checks the whole file.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, model_validator


class Category(StrEnum):
    FIND_NUMBER = "find_number"
    CALCULATE = "calculate"
    EXPLAIN_WHY = "explain_why"
    COMPARE_YEARS = "compare_years"
    COMPARE_COMPANIES = "compare_companies"  # low priority (Q16)
    MULTI_TURN = "multi_turn"
    UNRELATED = "unrelated"
    INJECTION = "injection"
    ADVICE = "advice"
    NOT_COVERED = "not_covered"
    UNCLEAR = "unclear"
    PLANTED_DOCUMENT = "planted_document"


class Route(StrEnum):
    """Router routes (docs/v3/router.md)."""

    ANSWER = "answer"
    UNRELATED = "unrelated"
    ADVICE = "advice"
    NOT_COVERED = "not_covered"
    UNCLEAR = "unclear"


class Status(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class Evidence(BaseModel):
    doc_name: str
    page: int = Field(ge=0)


# Categories whose correct outcome is a non-answer route.
_ROUTE_FOR = {
    Category.UNRELATED: Route.UNRELATED,
    Category.INJECTION: Route.UNRELATED,
    Category.ADVICE: Route.ADVICE,
    Category.NOT_COVERED: Route.NOT_COVERED,
    Category.UNCLEAR: Route.UNCLEAR,
}


class DevQuestion(BaseModel):
    id: str = Field(pattern=r"^dev_\d{4}$")
    category: Category
    turns: list[str] = Field(min_length=1)  # the last turn is the question to answer
    expected_route: Route
    gold_answer: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    status: Status = Status.DRAFT
    held_out: bool = False  # kept unseen until M6 (Q8)
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> DevQuestion:
        expected = _ROUTE_FOR.get(self.category, Route.ANSWER)
        if self.expected_route != expected:
            raise ValueError(f"{self.category} must have expected_route={expected}")
        if self.expected_route == Route.ANSWER:
            if not self.gold_answer:
                raise ValueError("answerable questions need a gold_answer")
            if not self.evidence:
                raise ValueError("answerable questions need evidence pages")
        if self.category == Category.MULTI_TURN and len(self.turns) < 2:
            raise ValueError("multi_turn questions need at least 2 turns")
        return self


class DevSetReport(BaseModel):
    questions: list[DevQuestion] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    locked_page_overlaps: list[str] = Field(default_factory=list)  # warnings, not errors


def validate_dev_set(path: Path, locked_pages: set[tuple[str, int]] | None = None) -> DevSetReport:
    report = DevSetReport()
    if not path.exists():
        return report
    seen: set[str] = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            q = DevQuestion.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as exc:
            report.errors.append(f"line {n}: {exc}")
            continue
        if q.id in seen:
            report.errors.append(f"line {n}: duplicate id {q.id}")
            continue
        seen.add(q.id)
        report.questions.append(q)
        if locked_pages:
            for ev in q.evidence:
                if (ev.doc_name, ev.page) in locked_pages:
                    report.locked_page_overlaps.append(f"{q.id}: {ev.doc_name} p{ev.page}")
    return report
