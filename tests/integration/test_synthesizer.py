"""
test_synthesizer.py

Validates Component 10 — synthesis/synthesizer.py

5 test cases:
  1. Single company + year + section  → 1 filter combination, grounded answer
  2. Multi-company comparison          → 2 filter combinations, balanced sources in answer
  3. Cross-year query (same company)   → 2 filter combinations across years
  4. Vague query (no filters)          → pure semantic search, no where clause
  5. Invalid / off-topic query         → rejected before retrieval, never reaches synthesizer

Run from project root:
    python test_synthesizer.py
"""

import sys
import os

sys.path.insert(0, os.path.abspath("."))

from retrieval.retriever import Retriever
from synthesis.synthesizer import Synthesizer

# -----------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------

retriever   = Retriever()
synthesizer = Synthesizer()

DIVIDER = "=" * 70

test_cases = [
    {
        "label":       "1 — Single company + year + section",
        "query":       "What were Apple's main risk factors in 2020?",
        "expect_error": False,
        "notes":       "Expect: 1 combination (AAPL+2020+Item 1A), all sources AAPL 2020 Item 1A",
    },
    {
        "label":       "2 — Multi-company comparison",
        "query":       "Compare Apple and Microsoft's risk factors in 2022",
        "expect_error": False,
        "notes":       "Expect: 2 combinations (AAPL+2022, MSFT+2022), sources split across both companies",
    },
    {
        "label":       "3 — Cross-year query (same company)",
        "query":       "How did Apple's business description change between 2020 and 2023?",
        "expect_error": False,
        "notes":       "Expect: 2 combinations (AAPL+2020+Item 1, AAPL+2023+Item 1), sources from both years",
    },
    {
        "label":       "4 — Vague query (no extractable filters)",
        "query":       "What are the biggest risks facing large technology companies?",
        "expect_error": False,
        "notes":       "Expect: no filters → 1 pure semantic query across all 2835 chunks, mixed sources",
    },
    {
        "label":       "5 — Invalid / off-topic query",
        "query":       "What is the capital of France?",
        "expect_error": True,
        "notes":       "Expect: retriever rejects query, synthesizer never called",
    },
]

# -----------------------------------------------------------------------
# Run tests
# -----------------------------------------------------------------------

passed = 0
failed = 0

for case in test_cases:
    print(f"\n{DIVIDER}")
    print(f"TEST {case['label']}")
    print(f"QUERY: {case['query']}")
    print(f"NOTE:  {case['notes']}")
    print(DIVIDER)

    # --- Retrieval ---
    chunks = retriever.retrieve(case["query"])

    if isinstance(chunks, dict) and "error" in chunks:
        if case["expect_error"]:
            print(f"\n  [PASS] Query correctly rejected.")
            print(f"  Reason: {chunks['error']}")
            passed += 1
        else:
            print(f"\n  [FAIL] Query unexpectedly rejected.")
            print(f"  Reason: {chunks['error']}")
            failed += 1
        continue

    if case["expect_error"]:
        print(f"\n  [FAIL] Expected rejection but retriever returned {len(chunks)} chunk(s).")
        failed += 1
        continue

    print(f"\n  Retriever: {len(chunks)} chunk(s) returned")

    # Source breakdown
    from collections import Counter
    ticker_year = Counter(f"{r['ticker']} {r['year']}" for r in chunks)
    for label, count in sorted(ticker_year.items()):
        print(f"    {label}: {count} chunk(s)")

    # --- Synthesis ---
    result = synthesizer.synthesize(case["query"], chunks)

    print(f"\n  Model      : {result['model_used']}")
    print(f"  Chunks used: {result['context_chunks']}")
    print(f"\n  ANSWER")
    print(f"  " + "-" * 66)
    for line in result["answer"].splitlines():
        print(f"  {line}")

    print(f"\n  SOURCES SENT TO LLM")
    print(f"  " + "-" * 66)
    for i, src in enumerate(result["sources"], 1):
        print(
            f"  [{i}] score={src['similarity_score']:.4f}  "
            f"{src['ticker']} {src['year']} | {src['section']} | {src['chunk_id']}"
        )

    # Basic checks
    checks = {
        "answer is non-empty":       len(result["answer"].strip()) > 0,
        "sources list non-empty":    len(result["sources"]) > 0,
        "context_chunks matches len": result["context_chunks"] == len(result["sources"]),
        "model_used is set":         bool(result["model_used"]),
    }

    all_pass = all(checks.values())
    print(f"\n  CHECKS")
    for check, ok in checks.items():
        print(f"    {'[PASS]' if ok else '[FAIL]'} {check}")

    if all_pass:
        print(f"\n  [PASS] Test {case['label'].split(' — ')[0]} passed.")
        passed += 1
    else:
        print(f"\n  [FAIL] Test {case['label'].split(' — ')[0]} failed.")
        failed += 1

# -----------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------

print(f"\n{DIVIDER}")
print(f"RESULTS: {passed} passed / {failed} failed / {len(test_cases)} total")
print(DIVIDER)
