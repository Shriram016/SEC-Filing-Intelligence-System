from types import SimpleNamespace
from typing import Any

import pytest

from filing_rag.config import Settings
from filing_rag.llm.client import AnthropicLLM, PaidCallNotAllowedError, cost_usd
from filing_rag.llm.fake import FakeLLM

SCHEMA: dict[str, Any] = {"type": "object"}


class FakeMessages:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        blocks = [
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text='{"a": 1}'),
        ]
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200)
        return SimpleNamespace(content=blocks, usage=usage, stop_reason="end_turn")


def settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_cost_uses_prices_per_million_tokens() -> None:
    assert cost_usd(1_000_000, 0, 2.0, 10.0) == 2.0
    assert cost_usd(1000, 200, 2.0, 10.0) == pytest.approx(0.004)


def test_real_model_refuses_without_allow_paid() -> None:
    with pytest.raises(PaidCallNotAllowedError):
        AnthropicLLM(settings())


def test_real_model_needs_api_key() -> None:
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicLLM(settings(anthropic_api_key=None), allow_paid=True)


def test_real_model_request_and_result() -> None:
    msgs = FakeMessages()
    llm = AnthropicLLM(settings(), allow_paid=True, client=SimpleNamespace(messages=msgs))
    res = llm.complete_json("sys", "user text", SCHEMA, 512)
    assert res.text == '{"a": 1}'  # text block read by type, thinking block skipped
    assert (res.input_tokens, res.output_tokens) == (1000, 200)
    assert res.cost_usd == pytest.approx(0.004)
    assert res.model == "claude-sonnet-5-5" and res.stop_reason == "end_turn"
    k = msgs.kwargs
    assert k["model"] == "claude-sonnet-5-5" and k["max_tokens"] == 512 and k["system"] == "sys"
    assert k["messages"] == [{"role": "user", "content": "user text"}]
    assert k["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
    assert k["thinking"] == {"type": "between_tools"}


def test_thinking_field_left_out_when_not_set() -> None:
    msgs = FakeMessages()
    llm = AnthropicLLM(
        settings(answer_thinking=None), allow_paid=True, client=SimpleNamespace(messages=msgs)
    )
    llm.complete_json("s", "u", SCHEMA, 10)
    assert "thinking" not in msgs.kwargs


def test_router_role_uses_haiku_settings_and_effort() -> None:
    msgs = FakeMessages()
    llm = AnthropicLLM(
        settings(), allow_paid=True, client=SimpleNamespace(messages=msgs), role="router"
    )
    res = llm.complete_json("s", "u", SCHEMA, 2048)
    k = msgs.kwargs
    assert k["model"] == "claude-haiku-5-5"
    assert "thinking" not in k  # Haiku 5.5: adaptive by default; between_tools is rejected
    assert k["output_config"] == {
        "format": {"type": "json_schema", "schema": SCHEMA},
        "effort": "low",
    }
    assert res.cost_usd == pytest.approx((1000 * 0.10 + 200 * 0.50) / 1_000_000)


def test_answer_role_sends_no_effort_by_default() -> None:
    msgs = FakeMessages()
    llm = AnthropicLLM(settings(), allow_paid=True, client=SimpleNamespace(messages=msgs))
    llm.complete_json("s", "u", SCHEMA, 10)
    assert "effort" not in msgs.kwargs["output_config"]


def test_fake_llm_replies_in_order_and_records_calls() -> None:
    fake = FakeLLM(["one", "two"])
    assert fake.complete_json("s", "u", SCHEMA, 10).text == "one"
    assert fake.complete_json("s", "u", SCHEMA, 10).text == "two"
    assert fake.complete_json("s", "u", SCHEMA, 10).text == "two"  # last one repeats
    assert len(fake.calls) == 3


def test_fake_llm_reply_can_depend_on_prompt() -> None:
    fake = FakeLLM([lambda s, u: u.upper()])
    assert fake.complete_json("s", "abc", SCHEMA, 10).text == "ABC"


def test_fake_llm_needs_a_reply() -> None:
    with pytest.raises(ValueError):
        FakeLLM([])
