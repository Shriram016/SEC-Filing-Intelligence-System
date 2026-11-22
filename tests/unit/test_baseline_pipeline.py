import json
from typing import Any

from filing_rag.baseline.pipeline import ANSWER_SCHEMA, BaselinePipeline, build_prompt, parse_answer
from filing_rag.llm.client import LLMResult
from filing_rag.llm.fake import FakeLLM
from filing_rag.search.searcher import Hit

GOOD = json.dumps(
    {
        "found": True,
        "answer": "Revenue was $152,703 million in FY2019.",
        "value": 152703,
        "unit": "USD million",
        "sources": [{"doc_name": "COSTCO_2019_10K", "page": 36}],
    }
)


def hit(doc: str, page: int, text: str, page_end: int | None = None) -> Hit:
    return Hit(0.8, {"doc_name": doc, "page": page, "page_end": page_end or page, "text": text})


class FakeSearcher:
    def __init__(self, hits: list[Hit]) -> None:
        self.hits = hits
        self.calls: list[tuple[str, str | None, int]] = []

    def search(self, query: str, company: str | None = None, k: int = 10) -> list[Hit]:
        self.calls.append((query, company, k))
        return self.hits[:k]


def result(text: str, stop: str = "end_turn") -> LLMResult:
    return LLMResult(text, 10, 5, 0.001, 0.1, "fake", stop)


def test_prompt_lists_chunks_with_document_and_page() -> None:
    p = build_prompt("What was revenue?", [hit("A_10K", 3, "rev 10"), hit("B_10K", 7, "tbl", 8)])
    assert "[1] A_10K, page 3\nrev 10" in p
    assert "[2] B_10K, pages 7-8\ntbl" in p
    assert p.rstrip().endswith("Question: What was revenue?")


def test_search_uses_no_company_filter_and_top_k() -> None:
    s = FakeSearcher([hit("A_10K", i, f"t{i}") for i in range(1, 9)])
    pipe = BaselinePipeline(s, FakeLLM([GOOD]), top_k=5)
    r = pipe.answer("q?")
    assert s.calls == [("q?", None, 5)]
    assert len(r.hits) == 5


def test_good_json_is_accepted() -> None:
    fake = FakeLLM([GOOD])
    r = BaselinePipeline(FakeSearcher([hit("COSTCO_2019_10K", 36, "x")]), fake).answer("q?")
    assert r.error is None and r.answer is not None
    assert r.answer.value == 152703 and r.answer.sources[0].page == 36
    assert len(r.calls) == 1 and r.cost_usd > 0
    assert fake.calls[0]["schema"] is ANSWER_SCHEMA


def test_broken_json_is_retried_once() -> None:
    r = BaselinePipeline(FakeSearcher([]), FakeLLM(["not json", GOOD])).answer("q?")
    assert r.error is None and r.answer is not None and len(r.calls) == 2


def test_broken_twice_gives_clear_error() -> None:
    r = BaselinePipeline(FakeSearcher([]), FakeLLM(['{"found": true}'])).answer("q?")
    assert r.answer is None and r.error is not None and "invalid JSON" in r.error
    assert len(r.calls) == 2


def test_cut_off_and_refused_replies_are_errors() -> None:
    for stop in ("max_tokens", "refusal"):
        try:
            parse_answer(result(GOOD, stop))
        except ValueError:
            continue
        raise AssertionError(f"{stop} was accepted")


def test_schema_requires_all_fields() -> None:
    props: dict[str, Any] = ANSWER_SCHEMA["properties"]
    assert set(ANSWER_SCHEMA["required"]) == set(props)
    assert ANSWER_SCHEMA["additionalProperties"] is False
