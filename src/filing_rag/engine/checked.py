"""Checked answers (Q107): writer call → claim + quote check → calculator → final rule.

Same interface as the baseline answer step (`answer(question, hits)`), so the routed pipeline
and the runner use either. The result also carries the old answer fields (value, unit,
sources), so the scorer is unchanged; the checked details are in `checked`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from filing_rag.baseline.pipeline import BaselineResult
from filing_rag.engine.answer import SYSTEM, WRITER_SCHEMA, WriterOutput, build_prompt, parse_output
from filing_rag.engine.final import CheckedAnswer, decide
from filing_rag.llm.client import LLM
from filing_rag.search.searcher import Hit


@dataclass
class CheckedResult(BaselineResult):
    writer: WriterOutput | None = None
    checked: CheckedAnswer | None = None


class CheckedAnswerer:
    def __init__(self, llm: LLM, max_tokens: int = 2048) -> None:
        self.llm = llm
        self.max_tokens = max_tokens

    def answer(
        self,
        question: str,
        hits: list[Hit],
        on_progress: Callable[[str], None] | None = None,
    ) -> CheckedResult:
        prompt = build_prompt(question, hits)
        res = CheckedResult(question=question, hits=hits, answer=None, error=None)
        for _attempt in range(2):  # one retry on a broken reply (Q32); none for failed checks
            call = self.llm.complete_json(SYSTEM, prompt, WRITER_SCHEMA, self.max_tokens)
            res.calls.append(call)
            try:
                res.writer = parse_output(call)
            except ValueError as exc:
                res.error = str(exc)
                continue
            res.error = None
            if on_progress is not None:
                on_progress("checking")
            res.checked = decide(res.writer, hits, question)
            res.answer = res.checked.to_baseline()
            return res
        return res
