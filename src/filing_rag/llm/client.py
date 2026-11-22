"""Model layer (ADR-0005): send a prompt, get JSON text back with tokens, cost and time.

Paid calls need an explicit `allow_paid=True` (working rule: no LLM call without the user's
approval). Unit tests use `FakeLLM` (filing_rag.llm.fake) and never call the API.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from filing_rag.config import Settings


class PaidCallNotAllowedError(RuntimeError):
    """A paid LLM call was attempted without explicit approval (`--allow-paid`)."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float
    model: str
    stop_reason: str | None = None


class LLM(Protocol):
    model: str

    def complete_json(
        self, system: str, user: str, schema: dict[str, Any], max_tokens: int
    ) -> LLMResult: ...


def cost_usd(input_tokens: int, output_tokens: int, price_in: float, price_out: float) -> float:
    """Cost in USD; prices are per 1M tokens."""
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


class AnthropicLLM:
    """Claude through the official SDK, with the JSON format enforced by the API.

    `role` picks the model settings: "answer" (Sonnet) or "router" (Haiku).
    """

    def __init__(
        self,
        settings: Settings,
        allow_paid: bool = False,
        client: Any = None,
        role: Literal["answer", "router"] = "answer",
    ) -> None:
        if not allow_paid:
            raise PaidCallNotAllowedError(
                "paid LLM calls need explicit approval: run with --allow-paid"
            )
        if client is None:
            if settings.anthropic_api_key is None:
                raise RuntimeError("ANTHROPIC_API_KEY is not set (add it to .env)")
            from anthropic import Anthropic

            client = Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
        self._client = client
        self.role = role
        if role == "router":
            self.model = settings.router_model
            self.price_in = settings.router_price_in_per_mtok
            self.price_out = settings.router_price_out_per_mtok
            self.thinking = settings.router_thinking
            self.effort = settings.router_effort
        else:
            self.model = settings.answer_model
            self.price_in = settings.answer_price_in_per_mtok
            self.price_out = settings.answer_price_out_per_mtok
            self.thinking = settings.answer_thinking
            self.effort = settings.answer_effort

    def complete_json(
        self, system: str, user: str, schema: dict[str, Any], max_tokens: int
    ) -> LLMResult:
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        if self.effort:
            output_config["effort"] = self.effort
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": output_config,
        }
        if self.thinking:
            kwargs["thinking"] = {"type": self.thinking}
        start = time.perf_counter()
        resp = self._client.messages.create(**kwargs)
        latency = time.perf_counter() - start
        # read by block type, not position (a thinking block can come first)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        tin, tout = int(resp.usage.input_tokens), int(resp.usage.output_tokens)
        return LLMResult(
            text=text,
            input_tokens=tin,
            output_tokens=tout,
            cost_usd=cost_usd(tin, tout, self.price_in, self.price_out),
            latency_s=latency,
            model=self.model,
            stop_reason=getattr(resp, "stop_reason", None),
        )
