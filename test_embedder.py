"""
Validates all 25 _embedded.json files produced by embeddings/embedder.py.

Checks per file:
  1. File exists and is valid JSON
  2. Chunk count matches source _tagged.json
  3. Every chunk has an "embedding" field
  4. Every embedding is exactly 768 floats
  5. No null or empty embeddings
  6. All original fields from _tagged.json are preserved
  7. Embeddings are lists of floats (not strings or ints)
  8. Semantic sanity — two same-section chunks score higher cosine similarity
     than a same-section chunk vs an unrelated-section chunk

Prints per-file pass/fail, then a final summary.
"""

import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).parent))
from config import EMBEDDING_DIMENSION, PROCESSED_DATA_DIR, TICKERS, YEARS

REQUIRED_FIELDS = [
    "chunk_id", "ticker", "year", "section", "chunk_index",
    "total_chunks", "word_count", "text", "company",
    "section_name", "filing_type", "source_file", "embedding",
]


def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def validate_file(ticker, year):
    tagged_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_tagged.json")
    embedded_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_embedded.json")
    failures = []

    # Check 1 — file exists and is valid JSON
    if not os.path.exists(embedded_path):
        return [f"CHECK 1 FAIL: {embedded_path} does not exist"]
    try:
        with open(embedded_path, "r", encoding="utf-8") as f:
            chunks = json.load(f)
    except json.JSONDecodeError as e:
        return [f"CHECK 1 FAIL: invalid JSON — {e}"]

    # Check 2 — chunk count matches _tagged.json
    with open(tagged_path, "r", encoding="utf-8") as f:
        tagged_chunks = json.load(f)
    if len(chunks) != len(tagged_chunks):
        failures.append(
            f"CHECK 2 FAIL: chunk count mismatch — "
            f"embedded={len(chunks)}, tagged={len(tagged_chunks)}"
        )

    for i, chunk in enumerate(chunks):
        ref = f"chunk[{i}] ({chunk.get('chunk_id', '?')})"

        # Check 3 — embedding field exists
        if "embedding" not in chunk:
            failures.append(f"CHECK 3 FAIL: missing embedding field in {ref}")
            continue

        embedding = chunk["embedding"]

        # Check 4 — embedding is exactly 768 floats long
        if len(embedding) != EMBEDDING_DIMENSION:
            failures.append(
                f"CHECK 4 FAIL: wrong dimension {len(embedding)} in {ref}"
            )

        # Check 5 — no null or empty embedding
        if embedding is None or len(embedding) == 0:
            failures.append(f"CHECK 5 FAIL: null or empty embedding in {ref}")

        # Check 6 — all required fields present
        missing = [field for field in REQUIRED_FIELDS if field not in chunk]
        if missing:
            failures.append(f"CHECK 6 FAIL: missing fields {missing} in {ref}")

        # Check 7 — embedding values are floats
        if not all(isinstance(v, float) for v in embedding[:10]):
            failures.append(f"CHECK 7 FAIL: embedding values are not floats in {ref}")

    # Check 8 — semantic sanity check
    # Find two chunks from the same section and one from a different section
    # Same-section pair should have higher similarity than cross-section pair
    by_section = {}
    for chunk in chunks:
        sec = chunk.get("section")
        if sec and "embedding" in chunk:
            by_section.setdefault(sec, []).append(chunk)

    sections_with_multiple = [s for s, c in by_section.items() if len(c) >= 2]
    other_sections = [s for s in by_section if s not in sections_with_multiple]

    if sections_with_multiple and other_sections:
        anchor_section = sections_with_multiple[0]
        chunk_a = by_section[anchor_section][0]
        chunk_b = by_section[anchor_section][1]
        chunk_c = by_section[other_sections[0]][0]

        sim_same = cosine_similarity(chunk_a["embedding"], chunk_b["embedding"])
        sim_diff = cosine_similarity(chunk_a["embedding"], chunk_c["embedding"])

        if sim_same <= sim_diff:
            failures.append(
                f"CHECK 8 FAIL: same-section similarity ({sim_same:.4f}) not greater "
                f"than cross-section similarity ({sim_diff:.4f})"
            )

    return failures


def main():
    print("=" * 60)
    print("Validating all 25 _embedded.json files")
    print("=" * 60)

    total_files = 0
    passed = 0
    failed = 0

    for ticker in TICKERS:
        for year in YEARS:
            total_files += 1
            failures = validate_file(ticker, year)

            if not failures:
                print(f"  PASS  {ticker}_{year}")
                passed += 1
            else:
                print(f"  FAIL  {ticker}_{year}")
                for msg in failures:
                    print(f"         {msg}")
                failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed}/{total_files} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
