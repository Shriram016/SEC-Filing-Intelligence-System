"""
metadata_tagger.py
------------------
Reads each _chunks.json from data/processed/,
adds metadata fields to every chunk,
and saves the result to data/processed/{TICKER}_{YEAR}_tagged.json.

Fields added per chunk:
    company      -- full company name derived from ticker
    section_name -- human-readable section title derived from section key
    filing_type  -- always "10-K"
    source_file  -- original HTM filename e.g. "AAPL_2020.htm"

Fields already present (from chunker, untouched):
    chunk_id, ticker, year, section, chunk_index,
    total_chunks, word_count, text

Run from project root:
    python ingestion/metadata_tagger.py
"""

import os
import json

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROCESSED_DATA_DIR = os.path.join("data", "processed")

TICKER_TO_COMPANY = {
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "AMZN":  "Amazon",
    "GOOGL": "Google",
    "META":  "Meta",
}

SECTION_TO_NAME = {
    "Item 1":  "Business",
    "Item 1A": "Risk Factors",
    "Item 7":  "MD&A",
    "Item 7A": "Market Risk",
}

COMPANIES = {
    "Apple":     {"ticker": "AAPL"},
    "Microsoft": {"ticker": "MSFT"},
    "Amazon":    {"ticker": "AMZN"},
    "Google":    {"ticker": "GOOGL"},
    "Meta":      {"ticker": "META"},
}

YEARS = [2020, 2021, 2022, 2023, 2024]


# ---------------------------------------------------------------------------
# Core tagging logic
# ---------------------------------------------------------------------------

def tag_chunks(chunks, ticker, year):
    """
    Add metadata fields to a list of chunk dicts.
    Returns a new list — originals are not mutated.
    """
    company     = TICKER_TO_COMPANY.get(ticker, "Unknown")
    source_file = f"{ticker}_{year}.htm"

    tagged = []
    for chunk in chunks:
        enriched = dict(chunk)  # copy all existing fields
        enriched["company"]      = company
        enriched["section_name"] = SECTION_TO_NAME.get(chunk["section"], "Unknown")
        enriched["filing_type"]  = "10-K"
        enriched["source_file"]  = source_file
        tagged.append(enriched)

    return tagged


def tag_file(ticker, year):
    """
    Load _chunks.json for one ticker/year, tag it, write _tagged.json.
    Returns the tagged chunk list on success, None on failure.
    """
    src_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_chunks.json")
    out_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_tagged.json")

    if not os.path.exists(src_path):
        print(f"  [FAIL] Source not found: {src_path}")
        return None

    with open(src_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    tagged = tag_chunks(chunks, ticker, year)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(tagged, f, ensure_ascii=False, indent=2)

    return tagged


# ---------------------------------------------------------------------------
# Main orchestrator — runs all 25 files
# ---------------------------------------------------------------------------

def tag_all():
    total   = 0
    success = 0
    skipped = 0
    failed  = 0

    for company, info in COMPANIES.items():
        ticker = info["ticker"]

        for year in YEARS:
            total += 1
            out_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_tagged.json")

            print(f"\n{'='*55}")
            print(f"  {company} ({ticker}) — {year}")
            print(f"{'='*55}")

            if os.path.exists(out_path):
                print(f"  [SKIP] Already exists: {out_path}")
                skipped += 1
                continue

            try:
                tagged = tag_file(ticker, year)
                if tagged is None:
                    failed += 1
                    continue

                print(f"  [OK] {len(tagged)} chunks tagged -> {out_path}")
                success += 1

            except Exception as e:
                print(f"  [FAIL] {company} {year} — {e}")
                failed += 1

    print(f"\n{'='*55}")
    print(f"  TAGGING SUMMARY")
    print(f"{'='*55}")
    print(f"  Total    : {total}")
    print(f"  Success  : {success}")
    print(f"  Skipped  : {skipped}  (already tagged)")
    print(f"  Failed   : {failed}")
    print(f"{'='*55}")


if __name__ == "__main__":
    print("Starting metadata tagger...")
    tag_all()
