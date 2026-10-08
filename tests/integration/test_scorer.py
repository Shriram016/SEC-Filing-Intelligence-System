"""
test_scorer.py

Validation script for scoring/scorer.py (Components 12+13).

Five test cases — each targets a distinct code path:

  1. Single company + year + section  — core happy path (AAPL 2020 Item 1A)
  2. Multi-company comparison          — balanced sources from two companies
  3. Vague / broad query               — pure semantic or multi-ticker retrieval
  4. Invalid query                     — rejected by retriever; scorer never called
  5. Refusal trigger                   — valid query, valid retrieval, but answer
                                         not in the indexed sections → synthesizer
                                         emits refusal string → faithfulness = 1.0

Run from project root:
    python test_scorer.py
"""

import sys
import os

from retrieval.retriever import Retriever
from synthesis.synthesizer import Synthesizer
from scoring.scorer import Scorer, REFUSAL_STRING

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"   # used when upstream component legitimately stops the chain

results = []   # list of (test_name, status, notes)


def record(name, status, notes=""):
    results.append((name, status, notes))
    marker = "✓" if status == PASS else ("–" if status == SKIP else "✗")
    print(f"  [{marker}] {name}: {notes}")


def separator(title=""):
    width = 65
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'=' * pad} {title} {'=' * pad}")
    else:
        print("=" * width)


# -----------------------------------------------------------------------
# Initialise pipeline (once — shared across all tests)
# -----------------------------------------------------------------------

separator("INITIALISING PIPELINE")
retriever   = Retriever()
synthesizer = Synthesizer()
scorer      = Scorer()


# -----------------------------------------------------------------------
# TEST 1 — Single company + year + section (core happy path)
# -----------------------------------------------------------------------

separator("TEST 1: Single company + year + section")
print("Query: What were Apple's main risk factors in 2020?\n")

query  = "What were Apple's main risk factors in 2020?"
chunks = retriever.retrieve(query)
result = synthesizer.synthesize(query, chunks)
score  = scorer.score(result)

print(f"\n  Answer (first 200 chars): {result['answer'][:200]}...")
print(f"  context_chunks          : {result['context_chunks']}")
print(f"  avg_retrieval_similarity: {score['avg_retrieval_similarity']}")
print(f"  faithfulness_score      : {score['faithfulness_score']}")
print(f"  confidence_score        : {score['confidence_score']}\n")

checks_passed = True

# Retrieval sanity
if not chunks or isinstance(chunks, dict):
    record("T1 — chunks returned",   FAIL, "no chunks retrieved")
    checks_passed = False
else:
    record("T1 — chunks returned",   PASS, f"{len(chunks)} chunks")

# Sources are AAPL 2020
tickers = {s["ticker"] for s in result["sources"]}
years   = {s["year"]   for s in result["sources"]}
if tickers == {"AAPL"} and years == {2020}:
    record("T1 — sources are AAPL 2020", PASS, f"tickers={tickers}, years={years}")
else:
    record("T1 — sources are AAPL 2020", FAIL, f"tickers={tickers}, years={years}")
    checks_passed = False

# Score fields in range
if 0.0 <= score["confidence_score"] <= 1.0:
    record("T1 — confidence in [0,1]",   PASS, f"{score['confidence_score']}")
else:
    record("T1 — confidence in [0,1]",   FAIL, f"{score['confidence_score']}")
    checks_passed = False

if 0.0 <= score["faithfulness_score"] <= 1.0:
    record("T1 — faithfulness in [0,1]", PASS, f"{score['faithfulness_score']}")
else:
    record("T1 — faithfulness in [0,1]", FAIL, f"{score['faithfulness_score']}")
    checks_passed = False

# Confidence formula check: within floating-point tolerance
expected = round(
    score["breakdown"]["retrieval_weight"]    * score["avg_retrieval_similarity"] +
    score["breakdown"]["faithfulness_weight"] * score["faithfulness_score"],
    4
)
if abs(score["confidence_score"] - expected) < 0.001:
    record("T1 — confidence formula correct", PASS,
           f"{score['confidence_score']} ≈ {expected}")
else:
    record("T1 — confidence formula correct", FAIL,
           f"got {score['confidence_score']}, expected {expected}")
    checks_passed = False

# Not a refusal
if REFUSAL_STRING not in result["answer"]:
    record("T1 — answer is not a refusal", PASS)
else:
    record("T1 — answer is not a refusal", FAIL, "synthesizer returned refusal for valid query")
    checks_passed = False


# -----------------------------------------------------------------------
# TEST 2 — Multi-company comparison
# -----------------------------------------------------------------------

separator("TEST 2: Multi-company comparison")
print("Query: Compare Apple and Microsoft's risk factors in 2022\n")

query  = "Compare Apple and Microsoft's risk factors in 2022"
chunks = retriever.retrieve(query)
result = synthesizer.synthesize(query, chunks)
score  = scorer.score(result)

print(f"\n  Answer (first 200 chars): {result['answer'][:200]}...")
print(f"  context_chunks          : {result['context_chunks']}")
sources_span = [f"{s['ticker']} {s['year']}" for s in result['sources']]
print(f"  Sources                 : {sources_span}")
print(f"  avg_retrieval_similarity: {score['avg_retrieval_similarity']}")
print(f"  faithfulness_score      : {score['faithfulness_score']}")
print(f"  confidence_score        : {score['confidence_score']}\n")

# Both companies present in sources
source_tickers = {s["ticker"] for s in result["sources"]}
if {"AAPL", "MSFT"}.issubset(source_tickers):
    record("T2 — both AAPL and MSFT in sources", PASS, f"tickers={source_tickers}")
else:
    record("T2 — both AAPL and MSFT in sources", FAIL, f"tickers={source_tickers}")

# Year is 2022
source_years = {s["year"] for s in result["sources"]}
if source_years == {2022}:
    record("T2 — year locked to 2022", PASS, f"years={source_years}")
else:
    record("T2 — year locked to 2022", FAIL, f"years={source_years}")

# Scores in range
if 0.0 <= score["confidence_score"] <= 1.0:
    record("T2 — confidence in [0,1]",   PASS, f"{score['confidence_score']}")
else:
    record("T2 — confidence in [0,1]",   FAIL, f"{score['confidence_score']}")

if 0.0 <= score["faithfulness_score"] <= 1.0:
    record("T2 — faithfulness in [0,1]", PASS, f"{score['faithfulness_score']}")
else:
    record("T2 — faithfulness in [0,1]", FAIL, f"{score['faithfulness_score']}")


# -----------------------------------------------------------------------
# TEST 3 — Vague / broad query (no tight filters)
# -----------------------------------------------------------------------

separator("TEST 3: Vague / broad query")
print("Query: What are the biggest risks facing large technology companies?\n")

query  = "What are the biggest risks facing large technology companies?"
chunks = retriever.retrieve(query)
result = synthesizer.synthesize(query, chunks)
score  = scorer.score(result)

print(f"\n  Answer (first 200 chars): {result['answer'][:200]}...")
print(f"  context_chunks          : {result['context_chunks']}")
print(f"  Unique tickers in sources: {sorted({s['ticker'] for s in result['sources']})}")
print(f"  avg_retrieval_similarity : {score['avg_retrieval_similarity']}")
print(f"  faithfulness_score       : {score['faithfulness_score']}")
print(f"  confidence_score         : {score['confidence_score']}\n")

# Retrieval worked
if chunks and not isinstance(chunks, dict):
    record("T3 — chunks retrieved",        PASS, f"{len(chunks)} chunks")
else:
    record("T3 — chunks retrieved",        FAIL, "no chunks or error")

# Multiple companies (broad query should span at least 2)
unique_tickers = {s["ticker"] for s in result["sources"]}
if len(unique_tickers) >= 2:
    record("T3 — sources span ≥2 companies", PASS, f"{sorted(unique_tickers)}")
else:
    record("T3 — sources span ≥2 companies", FAIL,
           f"only {sorted(unique_tickers)} — filters may have been too narrow")

# Scores in range
if 0.0 <= score["confidence_score"] <= 1.0:
    record("T3 — confidence in [0,1]",   PASS, f"{score['confidence_score']}")
else:
    record("T3 — confidence in [0,1]",   FAIL, f"{score['confidence_score']}")

if 0.0 <= score["faithfulness_score"] <= 1.0:
    record("T3 — faithfulness in [0,1]", PASS, f"{score['faithfulness_score']}")
else:
    record("T3 — faithfulness in [0,1]", FAIL, f"{score['faithfulness_score']}")


# -----------------------------------------------------------------------
# TEST 4 — Invalid query (retriever rejects; scorer never called)
# -----------------------------------------------------------------------

separator("TEST 4: Invalid query (off-topic)")
print("Query: What is the weather forecast for New York tomorrow?\n")

query  = "What is the weather forecast for New York tomorrow?"
chunks = retriever.retrieve(query)

if isinstance(chunks, dict) and "error" in chunks:
    print(f"  Retriever rejected: {chunks['error']}")
    record("T4 — retriever rejects off-topic query", PASS,
           f"error: {chunks['error']}")
    record("T4 — scorer not called",                 SKIP,
           "correct — no chunks to score")
else:
    # If retriever didn't reject, synthesizer might still handle it gracefully
    # but this is unexpected behaviour — flag it
    record("T4 — retriever rejects off-topic query", FAIL,
           f"retriever returned {len(chunks)} chunks instead of an error")
    record("T4 — scorer not called", FAIL, "scorer should not have been reached")


# -----------------------------------------------------------------------
# TEST 5 — Refusal trigger (fabricated synthesizer result)
# -----------------------------------------------------------------------

separator("TEST 5: Refusal trigger")

# Finding a query that the retriever accepts but the synthesizer cannot answer
# from our four indexed sections is fragile — the LLM's rejection threshold
# varies. The direct approach: retrieve real AAPL 2020 chunks (guaranteed to
# work), then fabricate a synthesizer result dict where the answer IS the
# refusal string. This isolates and tests exactly the scorer branch we care
# about: REFUSAL_STRING in answer → faithfulness = 1.0.

print("Approach: real AAPL 2020 chunks + fabricated refusal answer\n")

refusal_query  = "What were Apple's main risk factors in 2020?"
refusal_chunks = retriever.retrieve(refusal_query)

if isinstance(refusal_chunks, dict) and "error" in refusal_chunks:
    record("T5 — retrieve chunks for fabrication", FAIL,
           f"retriever rejected: {refusal_chunks['error']}")
else:
    record("T5 — retrieve chunks for fabrication", PASS,
           f"{len(refusal_chunks)} chunks")

    # Build a synthesizer-shaped result dict with the refusal string as answer
    fabricated_result = {
        "query":          refusal_query,
        "answer":         REFUSAL_STRING,   # the exact string scorer checks for
        "sources":        refusal_chunks[:5],
        "model_used":     "fabricated-for-test",
        "context_chunks": 5,
    }

    print(f"  Fabricated answer : \"{fabricated_result['answer']}\"")
    print(f"  Num sources       : {fabricated_result['context_chunks']}\n")

    # REFUSAL_STRING present — faithfulness branch should fire (no Groq call)
    score = scorer.score(fabricated_result)

    print(f"\n  confidence_score   : {score['confidence_score']}")
    print(f"  faithfulness_score : {score['faithfulness_score']}")
    print(f"  avg_similarity     : {score['avg_retrieval_similarity']}\n")

    if score["faithfulness_score"] == 1.0:
        record("T5 — faithfulness = 1.0 on refusal", PASS)
    else:
        record("T5 — faithfulness = 1.0 on refusal", FAIL,
               f"got {score['faithfulness_score']}")

    if 0.0 <= score["confidence_score"] <= 1.0:
        record("T5 — confidence in [0,1]", PASS, f"{score['confidence_score']}")
    else:
        record("T5 — confidence in [0,1]", FAIL, f"{score['confidence_score']}")

    # avg_retrieval_similarity should be non-zero (real chunks have scores)
    if score["avg_retrieval_similarity"] > 0.0:
        record("T5 — avg_similarity non-zero (real sources)", PASS,
               f"{score['avg_retrieval_similarity']}")
    else:
        record("T5 — avg_similarity non-zero (real sources)", FAIL,
               "expected > 0 from real retrieved chunks")


# -----------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------

separator("SUMMARY")
total  = len(results)
passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)
skipped = sum(1 for _, s, _ in results if s == SKIP)

for name, status, notes in results:
    marker = "✓" if status == PASS else ("–" if status == SKIP else "✗")
    suffix = f"  ({notes})" if notes else ""
    print(f"  [{marker}] {name}{suffix}")

print(f"\n  {passed}/{total} checks passed   |   {failed} failed   |   {skipped} skipped (expected)")

if failed == 0:
    print("\n  scorer.py — ALL CHECKS PASSED ✓")
else:
    print(f"\n  scorer.py — {failed} CHECK(S) FAILED ✗")

separator()
