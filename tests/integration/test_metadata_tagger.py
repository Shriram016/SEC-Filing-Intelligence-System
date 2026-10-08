"""
Test metadata_tagger logic on AAPL_2020 before scaling to all 25 filings.
Run from project root: python test_metadata_tagger.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))
from ingestion.metadata_tagger import tag_file, TICKER_TO_COMPANY, SECTION_TO_NAME

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TICKER    = "AAPL"
YEAR      = 2020
SRC_PATH  = f"data/processed/{TICKER}_{YEAR}_chunks.json"
OUT_PATH  = f"data/processed/{TICKER}_{YEAR}_tagged.json"

EXPECTED_COMPANY      = "Apple"
EXPECTED_FILING_TYPE  = "10-K"
EXPECTED_SOURCE_FILE  = f"{TICKER}_{YEAR}.htm"

REQUIRED_OLD_FIELDS = ["chunk_id", "ticker", "year", "section",
                        "chunk_index", "total_chunks", "word_count", "text"]
REQUIRED_NEW_FIELDS = ["company", "section_name", "filing_type", "source_file"]
ALL_FIELDS          = REQUIRED_OLD_FIELDS + REQUIRED_NEW_FIELDS

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    status = "PASS" if condition else "FAIL"
    if condition:
        PASS += 1
    else:
        FAIL += 1
    suffix = f"  -> {detail}" if detail else ""
    print(f"  [{status}] {label}{suffix}")


# ---------------------------------------------------------------------------
# Run tagger on AAPL 2020
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"  Metadata Tagger — Test on {TICKER} {YEAR}")
print(f"{'='*60}")

# Load original chunks for comparison
with open(SRC_PATH, encoding="utf-8") as f:
    original_chunks = json.load(f)

# Run tagger (writes _tagged.json, returns tagged list)
tagged_chunks = tag_file(TICKER, YEAR)

print(f"\n  Input  chunks : {len(original_chunks)}")
print(f"  Output chunks : {len(tagged_chunks) if tagged_chunks else 'N/A'}")

# ---------------------------------------------------------------------------
# Check 1: Output file was created
# ---------------------------------------------------------------------------
print(f"\n--- Check 1: Output file created ---")
check("_tagged.json exists on disk", os.path.exists(OUT_PATH), OUT_PATH)

# ---------------------------------------------------------------------------
# Check 2: Reload from disk — confirms file is valid JSON
# ---------------------------------------------------------------------------
print(f"\n--- Check 2: Output file is valid JSON ---")
try:
    with open(OUT_PATH, encoding="utf-8") as f:
        reloaded = json.load(f)
    check("File loads as valid JSON", True)
except Exception as e:
    check("File loads as valid JSON", False, str(e))
    reloaded = []

# ---------------------------------------------------------------------------
# Check 3: Chunk count matches input
# ---------------------------------------------------------------------------
print(f"\n--- Check 3: Chunk count matches input ---")
check(
    f"Chunk count unchanged ({len(original_chunks)})",
    len(reloaded) == len(original_chunks),
    f"got {len(reloaded)}"
)

# ---------------------------------------------------------------------------
# Check 4: Every chunk has all 12 fields
# ---------------------------------------------------------------------------
print(f"\n--- Check 4: All 12 fields present on every chunk ---")
missing_fields_chunks = []
for i, chunk in enumerate(reloaded):
    missing = [f for f in ALL_FIELDS if f not in chunk]
    if missing:
        missing_fields_chunks.append((i, missing))

check(
    "All chunks have all 12 fields",
    len(missing_fields_chunks) == 0,
    f"{len(missing_fields_chunks)} chunks with missing fields" if missing_fields_chunks else ""
)
if missing_fields_chunks:
    for idx, missing in missing_fields_chunks[:3]:
        print(f"    chunk[{idx}] missing: {missing}")

# ---------------------------------------------------------------------------
# Check 5: company field is correct
# ---------------------------------------------------------------------------
print(f"\n--- Check 5: company field ---")
wrong_company = [c for c in reloaded if c.get("company") != EXPECTED_COMPANY]
check(
    f"All chunks have company='{EXPECTED_COMPANY}'",
    len(wrong_company) == 0,
    f"{len(wrong_company)} wrong" if wrong_company else ""
)

# ---------------------------------------------------------------------------
# Check 6: section_name maps correctly for all sections present
# ---------------------------------------------------------------------------
print(f"\n--- Check 6: section_name maps correctly ---")
sections_seen = {}
for chunk in reloaded:
    sec     = chunk.get("section")
    secname = chunk.get("section_name")
    if sec not in sections_seen:
        sections_seen[sec] = secname

for section_key, section_name in sections_seen.items():
    expected = SECTION_TO_NAME.get(section_key, "Unknown")
    check(
        f"'{section_key}' -> '{section_name}'",
        section_name == expected,
        f"expected '{expected}'" if section_name != expected else ""
    )

# ---------------------------------------------------------------------------
# Check 7: filing_type is "10-K" on every chunk
# ---------------------------------------------------------------------------
print(f"\n--- Check 7: filing_type field ---")
wrong_type = [c for c in reloaded if c.get("filing_type") != EXPECTED_FILING_TYPE]
check(
    f"All chunks have filing_type='{EXPECTED_FILING_TYPE}'",
    len(wrong_type) == 0,
    f"{len(wrong_type)} wrong" if wrong_type else ""
)

# ---------------------------------------------------------------------------
# Check 8: source_file is correct on every chunk
# ---------------------------------------------------------------------------
print(f"\n--- Check 8: source_file field ---")
wrong_src = [c for c in reloaded if c.get("source_file") != EXPECTED_SOURCE_FILE]
check(
    f"All chunks have source_file='{EXPECTED_SOURCE_FILE}'",
    len(wrong_src) == 0,
    f"{len(wrong_src)} wrong" if wrong_src else ""
)

# ---------------------------------------------------------------------------
# Check 9: Original 8 fields are untouched (no data corruption)
# ---------------------------------------------------------------------------
print(f"\n--- Check 9: Original fields untouched ---")
corrupted = []
for orig, tagged in zip(original_chunks, reloaded):
    for field in REQUIRED_OLD_FIELDS:
        if orig.get(field) != tagged.get(field):
            corrupted.append((tagged.get("chunk_id"), field))

check(
    "All original fields identical to input",
    len(corrupted) == 0,
    f"{len(corrupted)} field mismatches found" if corrupted else ""
)
if corrupted:
    for chunk_id, field in corrupted[:3]:
        print(f"    {chunk_id} — field '{field}' changed")

# ---------------------------------------------------------------------------
# Sample output — first tagged chunk
# ---------------------------------------------------------------------------
if reloaded:
    print(f"\n--- Sample: First tagged chunk ---")
    first = reloaded[0]
    for k, v in first.items():
        if k == "text":
            print(f"  text         : {v[:80]}...")
        else:
            print(f"  {k:<14}: {v}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*60}")
print(f"  RESULT: {PASS} passed, {FAIL} failed")
print(f"{'='*60}\n")
