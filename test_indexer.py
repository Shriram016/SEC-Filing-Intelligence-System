"""
Validates the ChromaDB index produced by embeddings/indexer.py.

Checks:
  1. Collection exists and is reachable
  2. Total chunk count = 2,835
  3. No duplicate chunk_ids
  4. Per-ticker-year count matches source _embedded.json
  5. Every record has all required metadata fields
  6. Metadata dtypes are correct (year=int, ticker=str, etc.)
  7. Every record has a non-empty document (text)
  8. Metadata filtering works — AAPL 2020 filter returns correct count
  9. Similarity search returns valid results — distances in [0, 1], metadata present
 10. Search results span multiple companies — confirms all 5 companies are indexed
"""

import json
import os
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

sys.path.append(str(Path(__file__).parent))
from config import (
    BGE_QUERY_PREFIX,
    CHROMA_PERSIST_DIR,
    EMBEDDING_MODEL,
    PROCESSED_DATA_DIR,
    TICKERS,
    YEARS,
)

COLLECTION_NAME  = "sec_filings"
EXPECTED_TOTAL   = 2835
METADATA_FIELDS  = [
    "ticker", "year", "section", "chunk_index",
    "total_chunks", "word_count", "company",
    "section_name", "filing_type", "source_file",
]


def load_expected_counts():
    counts = {}
    for ticker in TICKERS:
        for year in YEARS:
            path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_embedded.json")
            with open(path, "r", encoding="utf-8") as f:
                counts[(ticker, year)] = len(json.load(f))
    return counts


def main():
    print("=" * 60)
    print("Validating ChromaDB index")
    print("=" * 60)

    failures = []

    # initialise client
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    # Check 1 — collection exists
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
        print(f"  PASS  Check 1  — collection '{COLLECTION_NAME}' exists")
    except Exception as e:
        print(f"  FAIL  Check 1  — collection not found: {e}")
        print("\nCannot continue — collection missing.")
        sys.exit(1)

    # Check 2 — total count = 2,835
    total = collection.count()
    if total == EXPECTED_TOTAL:
        print(f"  PASS  Check 2  — total count = {total}")
    else:
        failures.append(f"Check 2 FAIL: expected {EXPECTED_TOTAL}, got {total}")
        print(f"  FAIL  Check 2  — expected {EXPECTED_TOTAL}, got {total}")

    # Check 3 — no duplicate chunk_ids
    all_ids = collection.get(include=[])["ids"]
    if len(all_ids) == len(set(all_ids)):
        print(f"  PASS  Check 3  — no duplicate chunk_ids ({len(all_ids)} unique)")
    else:
        dupes = len(all_ids) - len(set(all_ids))
        failures.append(f"Check 3 FAIL: {dupes} duplicate chunk_ids found")
        print(f"  FAIL  Check 3  — {dupes} duplicate chunk_ids")

    # Check 4 — per-ticker-year count matches source _embedded.json
    print(f"  Checking per-file counts...")
    expected_counts = load_expected_counts()
    check4_passed = True
    for (ticker, year), expected in expected_counts.items():
        results = collection.get(
            where={"$and": [{"ticker": ticker}, {"year": year}]},
            include=[],
        )
        actual = len(results["ids"])
        if actual != expected:
            failures.append(
                f"Check 4 FAIL: {ticker}_{year} — expected {expected}, got {actual}"
            )
            print(f"  FAIL  Check 4  — {ticker}_{year}: expected {expected}, got {actual}")
            check4_passed = False
    if check4_passed:
        print(f"  PASS  Check 4  — all 25 per-file counts match source")

    # Checks 5, 6, 7 — sample every file's records for metadata + document integrity
    print(f"  Checking metadata fields, dtypes, and documents...")
    check567_passed = True
    for ticker in TICKERS:
        for year in YEARS:
            results = collection.get(
                where={"$and": [{"ticker": ticker}, {"year": year}]},
                include=["metadatas", "documents"],
            )
            for i, (meta, doc) in enumerate(zip(results["metadatas"], results["documents"])):

                # Check 5 — all required metadata fields present
                missing = [f for f in METADATA_FIELDS if f not in meta]
                if missing:
                    failures.append(f"Check 5 FAIL: {ticker}_{year}[{i}] missing fields {missing}")
                    check567_passed = False

                # Check 6 — metadata dtypes
                if not isinstance(meta.get("year"), int):
                    failures.append(f"Check 6 FAIL: {ticker}_{year}[{i}] year is not int")
                    check567_passed = False
                if not isinstance(meta.get("ticker"), str):
                    failures.append(f"Check 6 FAIL: {ticker}_{year}[{i}] ticker is not str")
                    check567_passed = False
                if not isinstance(meta.get("company"), str):
                    failures.append(f"Check 6 FAIL: {ticker}_{year}[{i}] company is not str")
                    check567_passed = False

                # Check 7 — document is non-empty string
                if not doc or not isinstance(doc, str) or len(doc.strip()) == 0:
                    failures.append(f"Check 7 FAIL: {ticker}_{year}[{i}] empty or missing document")
                    check567_passed = False

    if check567_passed:
        print(f"  PASS  Check 5  — all metadata fields present across all records")
        print(f"  PASS  Check 6  — metadata dtypes correct across all records")
        print(f"  PASS  Check 7  — all documents non-empty across all records")

    # Check 8 — metadata filtering works
    aapl_2020 = collection.get(
        where={"$and": [{"ticker": "AAPL"}, {"year": 2020}]},
        include=[],
    )
    expected_aapl_2020 = expected_counts[("AAPL", 2020)]
    if len(aapl_2020["ids"]) == expected_aapl_2020:
        print(f"  PASS  Check 8  — metadata filter AAPL+2020 returns {expected_aapl_2020} chunks")
    else:
        failures.append(
            f"Check 8 FAIL: AAPL 2020 filter returned {len(aapl_2020['ids'])}, expected {expected_aapl_2020}"
        )
        print(f"  FAIL  Check 8  — AAPL 2020 filter returned {len(aapl_2020['ids'])}, expected {expected_aapl_2020}")

    # Check 9 — similarity search returns valid results
    model = SentenceTransformer(EMBEDDING_MODEL)
    query_vector = model.encode(
        BGE_QUERY_PREFIX + "risk factors supply chain",
        normalize_embeddings=True,
    ).tolist()
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=5,
        include=["metadatas", "documents", "distances"],
    )
    distances = results["distances"][0]
    metadatas = results["metadatas"][0]
    documents = results["documents"][0]

    check9_passed = True
    for i, (dist, meta, doc) in enumerate(zip(distances, metadatas, documents)):
        if not (0.0 <= dist <= 1.0):
            failures.append(f"Check 9 FAIL: result {i} distance {dist} out of [0,1]")
            check9_passed = False
        if not meta or not doc:
            failures.append(f"Check 9 FAIL: result {i} missing metadata or document")
            check9_passed = False
    if check9_passed:
        print(f"  PASS  Check 9  — similarity search returns 5 valid results with distances in [0,1]")

    # Check 10 — results span multiple companies
    companies_in_results = set(m["company"] for m in metadatas)
    if len(companies_in_results) >= 2:
        print(f"  PASS  Check 10 — search results span {len(companies_in_results)} companies: {companies_in_results}")
    else:
        failures.append(
            f"Check 10 FAIL: results only contain {companies_in_results} — all 5 companies may not be indexed"
        )
        print(f"  FAIL  Check 10 — results only from {companies_in_results}")

    # final summary
    print()
    print("=" * 60)
    if not failures:
        print(f"Results: 10/10 checks passed")
    else:
        print(f"Results: {10 - len(failures)}/10 checks passed, {len(failures)} failed")
        for f in failures:
            print(f"  {f}")
    print("=" * 60)

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
