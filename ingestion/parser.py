"""
parser.py
---------
Reads each downloaded 10-K HTM file from data/raw/,
strips all HTML and iXBRL tags using BeautifulSoup + lxml,
and saves clean plain text to data/processed/{TICKER}_{YEAR}_parsed.json.

One JSON file per filing. Output schema:
    {
        "ticker":      "AAPL",
        "year":        2020,
        "source_file": "data/raw/AAPL_2020.htm",
        "char_count":  1500000,
        "text":        "... full clean text ..."
    }

Why BeautifulSoup + lxml?
  - iXBRL files contain embedded XBRL namespace tags (ix:header, ix:nonfraction, etc.)
  - BeautifulSoup handles these cleanly; html.parser does not
  - lxml is the fastest and most lenient parser for large malformed HTML
"""

import os
import re
import json
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# iXBRL files are XML-flavored HTML — BS4 warns about this, but the HTML
# parser handles them correctly (verified via test_parser.py). Silence.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RAW_DATA_DIR       = os.path.join("data", "raw")
PROCESSED_DATA_DIR = os.path.join("data", "processed")

COMPANIES = {
    "Apple":     {"ticker": "AAPL"},
    "Microsoft": {"ticker": "MSFT"},
    "Amazon":    {"ticker": "AMZN"},
    "Google":    {"ticker": "GOOGL"},
    "Meta":      {"ticker": "META"},
}

YEARS = [2020, 2021, 2022, 2023, 2024]

# Tags whose entire content block should be removed before text extraction.
# ix:header  — XBRL metadata header (not visible text)
# ix:hidden  — hidden XBRL values (not visible text)
# script     — JavaScript
# style      — CSS
REMOVE_TAGS = ["script", "style", "ix:header", "ix:hidden"]


# ---------------------------------------------------------------------------
# Core extraction logic
# ---------------------------------------------------------------------------

def extract_text(htm_path: str) -> str:
    """
    Reads an iXBRL HTM file and returns clean plain text.

    Steps:
      1. Read raw HTML from disk
      2. Parse with BeautifulSoup + lxml
      3. Decompose (fully remove) all REMOVE_TAGS blocks
      4. Call .get_text(separator=" ") — extracts visible text, strips all tags
      5. Collapse all whitespace sequences into a single space
    """
    print(f"  Reading: {htm_path}")
    with open(htm_path, "r", encoding="utf-8", errors="ignore") as f:
        raw_html = f.read()
    print(f"  Raw file size : {len(raw_html) / (1024 * 1024):.2f} MB")

    print(f"  Parsing with BeautifulSoup + lxml ...")
    soup = BeautifulSoup(raw_html, "lxml")

    # Remove noise tag blocks entirely (content + tags)
    removed = 0
    for tag_name in REMOVE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
            removed += 1
    print(f"  Removed {removed} noise blocks ({', '.join(REMOVE_TAGS)})")

    # Extract text — separator=" " prevents adjacent words from merging
    text = soup.get_text(separator=" ")

    # Collapse all whitespace (spaces, tabs, newlines) into single spaces
    text = re.sub(r'\s+', ' ', text).strip()

    print(f"  Clean text length : {len(text):,} characters")
    return text


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def parse_all() -> None:
    """
    Iterates over all 25 company-year combinations.
    Reads each .htm, extracts clean text, saves as JSON.
    Skips filings already parsed. Reports summary at end.
    """
    os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

    total   = 0
    success = 0
    skipped = 0
    failed  = 0

    for company, info in COMPANIES.items():
        ticker = info["ticker"]

        for year in YEARS:
            total   += 1
            src_path = os.path.join(RAW_DATA_DIR,       f"{ticker}_{year}.htm")
            out_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_parsed.json")

            print(f"\n{'='*55}")
            print(f"  {company} ({ticker}) — {year}")
            print(f"{'='*55}")

            # Already parsed — skip
            if os.path.exists(out_path):
                print(f"  [SKIP] Already exists: {out_path}")
                skipped += 1
                continue

            # Source file missing
            if not os.path.exists(src_path):
                print(f"  [FAIL] Source file not found: {src_path}")
                failed += 1
                continue

            try:
                text = extract_text(src_path)

                record = {
                    "ticker":      ticker,
                    "year":        year,
                    "source_file": src_path,
                    "char_count":  len(text),
                    "text":        text,
                }

                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)

                size_kb = os.path.getsize(out_path) / 1024
                print(f"  [OK] Saved → {out_path}  ({size_kb:.1f} KB)")
                success += 1

            except Exception as e:
                print(f"  [FAIL] {company} {year} — {e}")
                failed += 1

    # Summary
    print(f"\n{'='*55}")
    print(f"  PARSE SUMMARY")
    print(f"{'='*55}")
    print(f"  Total    : {total}")
    print(f"  Success  : {success}")
    print(f"  Skipped  : {skipped}  (already parsed)")
    print(f"  Failed   : {failed}")
    print(f"{'='*55}")


if __name__ == "__main__":
    print("Start parser script")
    parse_all()
