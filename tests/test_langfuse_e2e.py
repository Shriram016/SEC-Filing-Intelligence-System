"""
test_langfuse_e2e.py

End-to-end test for Langfuse instrumentation on the query pipeline.

Tests:
  1. Valid query  — runs full pipeline, checks all expected keys in result
  2. Invalid query — verifies rejection still works through the pipeline wrapper

Run from project root:
    python test_langfuse_e2e.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from retrieval.retriever import Retriever
from synthesis.synthesizer import Synthesizer
from scoring.scorer import Scorer
from pipeline import run_query_pipeline


def check_langfuse_keys():
    pub = os.getenv("LANGFUSE_PUBLIC_KEY")
    sec = os.getenv("LANGFUSE_SECRET_KEY")
    base = os.getenv("LANGFUSE_BASE_URL")
    if pub and sec and base:
        print(f"  Langfuse keys found. Base URL: {base}")
        return True
    print("  Langfuse keys NOT found — traces will not be sent.")
    return False


def test_valid_query(retriever, synthesizer, scorer):
    print("\n" + "=" * 60)
    print("TEST 1 — Valid query (Apple risk factors 2020)")
    print("=" * 60)

    query = "What were Apple's main risk factors in 2020?"
    result = run_query_pipeline(query, retriever, synthesizer, scorer)

    if isinstance(result, dict) and "error" in result:
        print(f"  FAIL — pipeline returned error: {result['error']}")
        return False

    synth_keys = {"query", "answer", "sources", "model_used", "context_chunks"}
    score_keys = {"confidence_score", "faithfulness_score", "avg_retrieval_similarity", "breakdown"}
    expected = synth_keys | score_keys
    missing = expected - set(result.keys())

    if missing:
        print(f"  FAIL — missing keys in result: {missing}")
        return False

    print(f"  answer length:    {len(result['answer'])} chars")
    print(f"  sources:          {result['context_chunks']}")
    print(f"  confidence:       {result['confidence_score']:.4f}")
    print(f"  faithfulness:     {result['faithfulness_score']:.4f}")
    print(f"  avg similarity:   {result['avg_retrieval_similarity']:.4f}")

    source_labels = [
        f"{s['ticker']} {s['year']} {s['section']}"
        for s in result['sources'][:3]
    ]
    print(f"  top 3 sources:    {source_labels}")
    print("  PASS")
    return True


def test_invalid_query(retriever, synthesizer, scorer):
    print("\n" + "=" * 60)
    print("TEST 2 — Invalid query (should be rejected)")
    print("=" * 60)

    query = "What is the weather forecast for New York tomorrow?"
    result = run_query_pipeline(query, retriever, synthesizer, scorer)

    if isinstance(result, dict) and "error" in result:
        print(f"  Rejected with: {result['error']}")
        print("  PASS")
        return True

    print("  FAIL — expected rejection but got a result")
    return False


def main():
    print("=" * 60)
    print("Langfuse E2E Test — Query Pipeline")
    print("=" * 60)

    print("\n[Langfuse check]")
    has_langfuse = check_langfuse_keys()

    print("\n[Loading components]")
    retriever = Retriever()
    synthesizer = Synthesizer()
    scorer = Scorer()

    results = []
    results.append(test_valid_query(retriever, synthesizer, scorer))
    results.append(test_invalid_query(retriever, synthesizer, scorer))

    print("\n" + "=" * 60)
    print(f"RESULTS: {sum(results)}/{len(results)} passed")
    if has_langfuse:
        print("Check Langfuse UI for traces: filter by name 'query-pipeline'")
    print("=" * 60)


if __name__ == "__main__":
    main()
