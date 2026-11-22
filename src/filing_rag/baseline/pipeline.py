"""Plain-RAG baseline: question -> top-k chunks (no filter) -> one LLM call -> JSON answer.

The answer is always JSON (Q31 rule, also for the baseline): the format is enforced by the
API and checked again by code. A broken reply gets one retry, then a clear error (Q32).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from filing_rag.llm.client import LLM, LLMResult
from filing_rag.search.searcher import Hit


class Source(BaseModel):
    doc_name: str
    page: int


class BaselineAnswer(BaseModel):
    found: bool
    answer: str
    value: float | None = None
    unit: str | None = None
    sources: list[Source] = Field(default_factory=list)


ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string"},
        "value": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "unit": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"doc_name": {"type": "string"}, "page": {"type": "integer"}},
                "required": ["doc_name", "page"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["found", "answer", "value", "unit", "sources"],
    "additionalProperties": False,
}

SYSTEM = (
    "You answer questions about company filings (10-K, 10-Q, 8-K, earnings releases). "
    "Use only the extracts in the message. Do not use outside knowledge."
)

RULES = """Answer the question from the extracts only. Fill the JSON fields:
- found: false if the extracts do not contain the answer.
- answer: a short answer in words, with the period it refers to.
- value: the main number of the answer as a plain number (no commas, no symbols), or null for
  an answer without a number. For a change, use a negative value for a decrease.
- unit: the unit of value with its scale, for example "USD million", "USD", "%", "shares";
  null when value is null.
- sources: the extracts you used, as doc_name and page."""


class SearchFn(Protocol):
    def search(self, query: str, company: str | None = None, k: int = 10) -> list[Hit]: ...


@dataclass
class BaselineResult:
    question: str
    hits: list[Hit]
    answer: BaselineAnswer | None
    error: str | None
    calls: list[LLMResult] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def latency_s(self) -> float:
        return sum(c.latency_s for c in self.calls)


def _page_label(h: Hit) -> str:
    return f"page {h.page}" if h.page == h.page_end else f"pages {h.page}-{h.page_end}"


def build_prompt(question: str, hits: list[Hit]) -> str:
    parts = ["Extracts:"]
    for i, h in enumerate(hits, start=1):
        text = str(h.payload.get("text", "")).strip()
        parts.append(f"[{i}] {h.doc_name}, {_page_label(h)}\n{text}")
    parts += [RULES, f"Question: {question}"]
    return "\n\n".join(parts)


def parse_answer(result: LLMResult) -> BaselineAnswer:
    """Raise ValueError when the reply is not a complete, valid answer."""
    if result.stop_reason == "max_tokens":
        raise ValueError("reply cut off at max_tokens")
    if result.stop_reason == "refusal":
        raise ValueError("model refused")
    try:
        return BaselineAnswer.model_validate(json.loads(result.text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid JSON answer: {exc}") from exc


class BaselinePipeline:
    def __init__(
        self, searcher: SearchFn, llm: LLM, top_k: int = 5, max_tokens: int = 1024
    ) -> None:
        self.searcher = searcher
        self.llm = llm
        self.top_k = top_k
        self.max_tokens = max_tokens

    def retrieve(self, question: str) -> list[Hit]:
        return self.searcher.search(question, company=None, k=self.top_k)

    def answer(
        self,
        question: str,
        hits: list[Hit] | None = None,
        on_progress: Callable[[str], None] | None = None,  # unused (Q108 API interface)
    ) -> BaselineResult:
        hits = self.retrieve(question) if hits is None else hits
        prompt = build_prompt(question, hits)
        res = BaselineResult(question=question, hits=hits, answer=None, error=None)
        for _attempt in range(2):  # one retry on a broken reply (Q32)
            call = self.llm.complete_json(SYSTEM, prompt, ANSWER_SCHEMA, self.max_tokens)
            res.calls.append(call)
            try:
                res.answer = parse_answer(call)
                res.error = None
                return res
            except ValueError as exc:
                res.error = str(exc)
        return res
