"""A fake model for tests: fixed replies, no network, no cost."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from filing_rag.llm.client import LLMResult, cost_usd

Reply = str | Callable[[str, str], str]


class FakeLLM:
    """Gives back the replies in order (the last one repeats). A reply can be a function
    of (system, user). Tokens are counted as words; prices default to Sonnet 5.5."""

    def __init__(
        self, replies: list[Reply], price_in: float = 2.0, price_out: float = 10.0
    ) -> None:
        if not replies:
            raise ValueError("FakeLLM needs at least one reply")
        self.replies = replies
        self.model = "fake"
        self.price_in = price_in
        self.price_out = price_out
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self, system: str, user: str, schema: dict[str, Any], max_tokens: int
    ) -> LLMResult:
        reply = self.replies[min(len(self.calls), len(self.replies) - 1)]
        self.calls.append({"system": system, "user": user, "schema": schema})
        text = reply(system, user) if callable(reply) else reply
        tin = len((system + " " + user).split())
        tout = len(text.split())
        return LLMResult(
            text=text,
            input_tokens=tin,
            output_tokens=tout,
            cost_usd=cost_usd(tin, tout, self.price_in, self.price_out),
            latency_s=0.0,
            model=self.model,
            stop_reason="end_turn",
        )
