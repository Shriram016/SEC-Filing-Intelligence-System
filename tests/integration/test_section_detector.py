"""
test_section_detector.py
------------------------
Tests section detection logic on one file per company (2020):
  - AAPL_2020, MSFT_2020, AMZN_2020, GOOGL_2020, META_2020

For each file:
  1. Find real section headers (Item + title on same line)
  2. Slice text between boundaries
  3. Report what was found and what was missed

Run: python test_section_detector.py
"""

import json
import re

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TEST_FILES = [
    "data/processed/AAPL_2020_parsed.json",
    "data/processed/MSFT_2020_parsed.json",
    "data/processed/AMZN_2020_parsed.json",
    "data/processed/GOOGL_2020_parsed.json",
    "data/processed/META_2020_parsed.json",
]

# Section headers to detect — matches both formats:
#   Format A (AAPL, MSFT): "Item 1A. Risk Factors"  — title on same line
#   Format B (AMZN, GOOGL, META): "Item 1A."         — alone on its own line
# Order matters — defines slicing boundaries
TARGET_SECTIONS = [
    ("Item 1",  r"^\s*Item\s+1\."),
    ("Item 1A", r"^\s*Item\s+1A\."),
    ("Item 2",  r"^\s*Item\s+2\."),   # end boundary for Item 1A — skips Items 2-6
    ("Item 7",  r"^\s*Item\s+7\."),
    ("Item 7A", r"^\s*Item\s+7A\."),
    ("Item 8",  r"^\s*Item\s+8\."),   # end boundary for Item 7A
]

# Minimum line gap between consecutive sections to be considered real (not TOC)
MIN_SECTION_GAP = 50


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def find_section_starts(lines):
    """
    For each target section, find the line number of the REAL section header.

    Strategy:
      1. Collect ALL line numbers where each target pattern matches
      2. TOC entries are bunched together (gap < MIN_SECTION_GAP lines apart)
         Real headers are far apart (gap > MIN_SECTION_GAP lines)
      3. Pick the first occurrence where the gap to the next target section
         is large enough — that's the real section start

    Returns dict: { "Item 1": line_num, "Item 1A": line_num, ... }
    Returns None for any section not found.
    """
    # Step 1 — find all occurrences of each target pattern
    all_hits = {}
    for section_name, pattern in TARGET_SECTIONS:
        hits = [i for i, line in enumerate(lines)
                if re.match(pattern, line, re.IGNORECASE)]
        all_hits[section_name] = hits

    section_names = [s for s, _ in TARGET_SECTIONS]

    # Format A patterns — item + title on same line (unambiguous, always real header)
    format_a = {
        "Item 1":  r"^\s*Item\s+1\.\s+\S",
        "Item 1A": r"^\s*Item\s+1A\.\s+\S",
        "Item 2":  r"^\s*Item\s+2\.\s+\S",
        "Item 7":  r"^\s*Item\s+7\.\s+\S",
        "Item 7A": r"^\s*Item\s+7A\.\s+\S",
        "Item 8":  r"^\s*Item\s+8\.\s+\S",
    }

    # Step 2 — for each section, pick the correct occurrence
    results = {}
    for idx, section_name in enumerate(section_names):
        hits = all_hits[section_name]

        if not hits:
            results[section_name] = None
            continue

        # Priority 1 — Format A match (title on same line) — unambiguous, take first
        format_a_hits = [i for i in hits
                         if re.match(format_a[section_name], lines[i], re.IGNORECASE)]
        if format_a_hits:
            results[section_name] = format_a_hits[0]
            continue

        # Priority 2 — Format B (alone on line) — use gap logic to skip TOC
        if len(hits) == 1:
            results[section_name] = hits[0]
            continue

        next_section = section_names[idx + 1] if idx + 1 < len(section_names) else None
        next_hits    = all_hits.get(next_section, []) if next_section else []

        chosen = hits[-1]   # fallback — last occurrence
        for hit in hits:
            future_next = [n for n in next_hits if n > hit]
            if future_next:
                gap = future_next[0] - hit
                if gap > MIN_SECTION_GAP:
                    chosen = hit
                    break

        results[section_name] = chosen

    return results


def extract_sections(lines, starts):
    """
    Slices lines between section boundaries.
    Returns dict: { "Item 1": "text...", "Item 1A": "text...", ... }
    """
    extract_targets = ["Item 1", "Item 1A", "Item 7", "Item 7A"]
    end_markers     = ["Item 1A", "Item 2", "Item 7A", "Item 8"]

    sections = {}
    for section, end in zip(extract_targets, end_markers):
        start_line = starts.get(section)
        end_line   = starts.get(end)

        if start_line is None:
            sections[section] = None
            continue

        # Slice lines — if no end boundary found, take to end of doc
        if end_line is not None:
            chunk = lines[start_line:end_line]
        else:
            chunk = lines[start_line:]

        sections[section] = "\n".join(chunk).strip()

    return sections


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def test_file(filepath):
    ticker_year = filepath.split("/")[-1].replace("_parsed.json", "")
    print(f"\n{'='*60}")
    print(f"  {ticker_year}")
    print(f"{'='*60}")

    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    lines = data["text"].split("\n")
    print(f"  Total lines : {len(lines):,}")

    # Find section start line numbers
    starts = find_section_starts(lines)

    print(f"\n  Section header locations:")
    for section, line_num in starts.items():
        if line_num is not None:
            print(f"    {section:10s} -> line {line_num:5d} : [{lines[line_num].strip()[:70]}]")
        else:
            print(f"    {section:10s} -> NOT FOUND")

    # Extract sections
    sections = extract_sections(lines, starts)

    print(f"\n  Extracted section sizes:")
    all_found = True
    for section, text in sections.items():
        if text:
            word_count = len(text.split())
            print(f"    {section:10s} -> {len(text):>8,} chars  |  {word_count:>6,} words  |  first 80: [{text[:80]}]")
        else:
            print(f"    {section:10s} -> MISSING")
            all_found = False

    print(f"\n  Result: {'ALL 4 SECTIONS FOUND' if all_found else 'SOME SECTIONS MISSING'}")
    return all_found


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Section Detection Test — 5 companies, 2020 filings")

    results = {}
    for filepath in TEST_FILES:
        ticker_year = filepath.split("/")[-1].replace("_parsed.json", "")
        results[ticker_year] = test_file(filepath)

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for ticker_year, passed in results.items():
        status = "PASS" if passed else "FAIL"
        mark   = "+" if passed else "-"
        print(f"  [{mark}] {ticker_year:20s} {status}")
    print(f"{'='*60}")
