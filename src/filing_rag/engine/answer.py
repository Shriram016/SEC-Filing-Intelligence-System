"""Answer writer (engine.md §3.4, Q107): one Sonnet call → claims with exact quotes.

The model never writes a number in the answer sentence. It returns claims (each with an exact
quote from one numbered extract), optional calculations (op + input IDs; code computes them),
the ID of the item that answers the question (`main`), and a sentence with placeholders
(`{c1}`, `{k1}`). Code checks the claims (`checks.py`), computes (`calculator.py`) and writes
the final text (`final.py`).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from filing_rag.llm.client import LLMResult
from filing_rag.search.searcher import Hit

Op = Literal["add", "subtract", "multiply", "divide", "ratio_pct", "pct_change"]
OPS: tuple[str, ...] = ("add", "subtract", "multiply", "divide", "ratio_pct", "pct_change")


class CalcInput(BaseModel):
    """Q113: a reference to a claim / earlier calculation, or a fixed number. Code checks that
    exactly one is set (a wrong input fails that calculation, not the whole answer)."""

    ref: str | None = None
    const: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_id(cls, v: Any) -> Any:
        return {"ref": v, "const": None} if isinstance(v, str) else v


class Claim(BaseModel):
    id: str
    label: str
    extract: int
    quote: str
    value: float | None = None
    unit: str | None = None
    period: str | None = None


class Calculation(BaseModel):
    id: str
    op: Op
    inputs: list[CalcInput]

    @property
    def refs(self) -> list[str]:
        return [i.ref for i in self.inputs if i.ref is not None]

    label: str
    unit: str | None = None


class WriterOutput(BaseModel):
    found: bool
    claims: list[Claim] = Field(default_factory=list)
    calculations: list[Calculation] = Field(default_factory=list)
    main: str | None = None
    answer: str = ""


_NULLABLE_STR: dict[str, Any] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_NULLABLE_NUM: dict[str, Any] = {"anyOf": [{"type": "number"}, {"type": "null"}]}

WRITER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "extract": {"type": "integer"},
                    "quote": {"type": "string"},
                    "value": _NULLABLE_NUM,
                    "unit": _NULLABLE_STR,
                    "period": _NULLABLE_STR,
                },
                "required": ["id", "label", "extract", "quote", "value", "unit", "period"],
                "additionalProperties": False,
            },
        },
        "calculations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "op": {"type": "string", "enum": list(OPS)},
                    "inputs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"ref": _NULLABLE_STR, "const": _NULLABLE_NUM},
                            "required": ["ref", "const"],
                            "additionalProperties": False,
                        },
                    },
                    "label": {"type": "string"},
                    "unit": _NULLABLE_STR,
                },
                "required": ["id", "op", "inputs", "label", "unit"],
                "additionalProperties": False,
            },
        },
        "main": _NULLABLE_STR,
        "answer": {"type": "string"},
    },
    "required": ["found", "claims", "calculations", "main", "answer"],
    "additionalProperties": False,
}

SYSTEM = (
    "You answer questions about company filings (10-K, 10-Q, 8-K, earnings releases). "
    "Use only the numbered extracts in the message. Do not use outside knowledge. "
    "Every fact must be backed by an exact quote, and code checks every quote."
)

RULES = """Answer from the extracts only, as JSON:
- found: false if the extracts do not contain what the question needs. Then claims may be empty.
- claims: the facts you use, one per number or statement. For each claim:
  - id: "c1", "c2", ...
  - label: a short name of the fact with company and period, e.g. "Apple net sales, FY2023".
  - extract: the number in [ ] of the extract that holds the quote.
  - quote: text copied exactly from that extract, at least 3 words. For a table, copy one row:
    the row name and its numbers, as they appear. Do not join text from different places.
  - value: the number exactly as printed in the quote (no commas, no symbols, do not change
    the scale); negative if printed in parentheses; null for a statement without a number.
  - unit: the unit with the scale from the table header or text, e.g. "USD million", "USD",
    "%", "shares"; null when value is null.
  - period: the period of the value, e.g. "nine months ended July 1, 2023".
- calculations: only when the answer must be computed. Code does the arithmetic. For each:
  - id: "k1", "k2", ...
  - op, with its inputs in order:
    "add" (2 or more), "subtract" (first minus second), "multiply" (2 or more),
    "divide" (first / second), "ratio_pct" (first / second x 100, e.g. a margin),
    "pct_change" (from first to second, in %).
  - inputs: each is {"ref": "c1", "const": null} for a claim or an earlier calculation, or
    {"ref": null, "const": 3} for a fixed number. Use a fixed number only when it is written in
    the question (e.g. 365 in a formula) or for a count or factor such as 1, 2, 3, 4, 12, 100
    (e.g. an average = add the values, then divide by the count). Every value from the
    filings must be a claim, never a fixed number.
  - label: what the result is, e.g. "free cash flow, nine months FY2023"; unit: the unit you
    expect, or null.
- main: the id of the claim or calculation that answers the question; null for an answer
  without a single number.
- answer: one or two short sentences. Never write a number yourself: use the placeholders
  {c1}, {k1}, ... for every value. Years in words such as "fiscal 2023" are allowed. Code
  writes each value with its unit and scale ("$152,703 million", "12.5%"), so write no unit,
  scale or currency sign next to a placeholder: "revenue was {c1}", not "{c1} million USD"."""


def build_prompt(question: str, hits: list[Hit]) -> str:
    parts = ["Extracts:"]
    for i, h in enumerate(hits, start=1):
        pages = f"page {h.page}" if h.page == h.page_end else f"pages {h.page}-{h.page_end}"
        text = str(h.payload.get("text", "")).strip()
        parts.append(f"[{i}] {h.doc_name}, {pages}\n{text}")
    parts += [RULES, f"Question: {question}"]
    return "\n\n".join(parts)


def parse_output(result: LLMResult) -> WriterOutput:
    """Raise ValueError when the reply is not a complete, valid writer output."""
    if result.stop_reason == "max_tokens":
        raise ValueError("reply cut off at max_tokens")
    if result.stop_reason == "refusal":
        raise ValueError("model refused")
    try:
        out = WriterOutput.model_validate(json.loads(result.text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid JSON answer: {exc}") from exc
    ids = [c.id for c in out.claims] + [k.id for k in out.calculations]
    if len(ids) != len(set(ids)):
        raise ValueError("invalid JSON answer: duplicate claim or calculation IDs")
    return out
