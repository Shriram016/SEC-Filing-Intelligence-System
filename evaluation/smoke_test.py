"""
Quick smoke test for RAGAS 0.4.3 setup with Groq.

Tests two approaches:
  A) v0.3-style evaluate() with deprecated imports (simpler, batch)
  B) v0.4-style ascore() per metric (recommended, per-sample)

Run from project root:
    python evaluation/smoke_test.py
"""

import os
import sys
import asyncio
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


# ── Step 1: Imports ──────────────────────────────────────────────────────

print("Step 1: Testing imports...")

from ragas import evaluate, EvaluationDataset, SingleTurnSample

# v0.4 collections imports (for ascore approach)
from ragas.metrics.collections import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecisionWithReference,
    ContextRecall,
)

from ragas.llms import llm_factory
from ragas.embeddings.base import embedding_factory

print("  All RAGAS imports OK")


# ── Step 2: LLM setup ───────────────────────────────────────────────────

print("\nStep 2: Setting up LLM...")

# RAGAS 0.4.3 collections metrics need InstructorLLM.
# Groq's native client failed (.messages attribute missing).
# Use OpenAI client pointed at Groq's OpenAI-compatible endpoint.
from openai import AsyncOpenAI

groq_client = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

llm = llm_factory(
    model="llama-3.1-8b-instant",
    provider="openai",
    client=groq_client,
)

print(f"  LLM OK: {type(llm).__name__}")


# ── Step 3: Embeddings setup ────────────────────────────────────────────

print("\nStep 3: Setting up embeddings...")

emb = embedding_factory(
    provider="huggingface",
    model="BAAI/bge-base-en",
    interface="modern",
)

print(f"  Embeddings OK: {type(emb).__name__}")


# ── Step 4: Build sample ────────────────────────────────────────────────

print("\nStep 4: Building test sample...")

sample = SingleTurnSample(
    user_input="What are Apple's main risk factors?",
    response="Apple faces risks from supply chain disruptions and single-source component dependencies.",
    retrieved_contexts=[
        "Apple currently obtains certain components from single or limited sources, making it subject to significant supply and pricing risks.",
        "The technology industry is highly competitive with aggressive pricing and rapid technological change.",
    ],
    reference="Apple disclosed risks related to single-source component suppliers and supply chain concentration.",
)

print("  SingleTurnSample OK")


# ── Step 5: Test ascore() per metric (v0.4 recommended approach) ─────

print("\nStep 5: Testing ascore() for each metric...")

faithfulness = Faithfulness(llm=llm)
answer_relevancy = AnswerRelevancy(llm=llm, embeddings=emb)
context_precision = ContextPrecisionWithReference(llm=llm)
context_recall = ContextRecall(llm=llm)

print("  All 4 metrics initialized OK")


async def test_ascore():
    print("\n  Running Faithfulness...")
    f_result = await faithfulness.ascore(
        user_input=sample.user_input,
        response=sample.response,
        retrieved_contexts=sample.retrieved_contexts,
    )
    print(f"    Faithfulness = {f_result}")

    print("  Running AnswerRelevancy...")
    ar_result = await answer_relevancy.ascore(
        user_input=sample.user_input,
        response=sample.response,
    )
    print(f"    AnswerRelevancy = {ar_result}")

    print("  Running ContextPrecision...")
    cp_result = await context_precision.ascore(
        user_input=sample.user_input,
        retrieved_contexts=sample.retrieved_contexts,
        reference=sample.reference,
    )
    print(f"    ContextPrecision = {cp_result}")

    print("  Running ContextRecall...")
    cr_result = await context_recall.ascore(
        user_input=sample.user_input,
        retrieved_contexts=sample.retrieved_contexts,
        reference=sample.reference,
    )
    print(f"    ContextRecall = {cr_result}")

    return {
        "faithfulness": f_result,
        "answer_relevancy": ar_result,
        "context_precision": cp_result,
        "context_recall": cr_result,
    }


results = asyncio.run(test_ascore())

print("\n" + "=" * 50)
print("SMOKE TEST RESULTS")
print("=" * 50)
for metric_name, score in results.items():
    print(f"  {metric_name:<25}: {score}")
print("\nSmoke test PASSED")
