"""
section_detector.py
-------------------
Reads each parsed JSON from data/processed/{TICKER}_{YEAR}_parsed.json,
detects the 4 target SEC section boundaries, extracts section text,
and writes data/processed/{TICKER}_{YEAR}_sections.json.

Target sections:
    Item 1   — Business
    Item 1A  — Risk Factors
    Item 7   — MD&A
    Item 7A  — Market Risk (ends at Item 8)

Detection strategy:
    Two formats observed across companies:
      Format A (AAPL, MSFT) — item number + title on same line
                               e.g. "Item 1A. Risk Factors"
      Format B (AMZN, GOOGL, META) — item number alone on its own line
                               e.g. "Item 1A."

    Priority 1 — Look for Format A match first (unambiguous, always real header)
    Priority 2 — Fall back to Format B with gap logic:
                 TOC entries are bunched within ~50 lines of each other.
                 Real section headers have large gaps between them.
                 Pick the first occurrence where gap to the next section > MIN_GAP.

Boundary map:
    Item 1   → ends at Item 1A
    Item 1A  → ends at Item 2  (skips Items 2–6 cleanly)
    Item 7   → ends at Item 7A
    Item 7A  → ends at Item 8

Run from project root:
    python ingestion/section_detector.py
"""

import os
import re
import json

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROCESSED_DATA_DIR = os.path.join("data", "processed")

COMPANIES = {
    "Apple":     "AAPL",
    "Microsoft": "MSFT",
    "Amazon":    "AMZN",
    "Google":    "GOOGL",
    "Meta":      "META",
}

YEARS = [2020, 2021, 2022, 2023, 2024]

# All section patterns — order matters, defines boundary sequence
TARGET_SECTIONS = [
    ("Item 1",  r"^\s*Item\s+1\."),
    ("Item 1A", r"^\s*Item\s+1A\."),
    ("Item 2",  r"^\s*Item\s+2\."),   # end boundary for Item 1A — skips Items 2-6
    ("Item 7",  r"^\s*Item\s+7\."),
    ("Item 7A", r"^\s*Item\s+7A\."),
    ("Item 8",  r"^\s*Item\s+8\."),   # end boundary for Item 7A
]

# Format A — item number + title on same line (unambiguous)
FORMAT_A_PATTERNS = {
    "Item 1":  r"^\s*Item\s+1\.\s+\S",
    "Item 1A": r"^\s*Item\s+1A\.\s+\S",
    "Item 2":  r"^\s*Item\s+2\.\s+\S",
    "Item 7":  r"^\s*Item\s+7\.\s+\S",
    "Item 7A": r"^\s*Item\s+7A\.\s+\S",
    "Item 8":  r"^\s*Item\s+8\.\s+\S",
}

# Sections to extract and their end boundaries
EXTRACT_TARGETS = ["Item 1", "Item 1A", "Item 7",  "Item 7A"]
END_MARKERS     = ["Item 1A", "Item 2", "Item 7A", "Item 8"]

# Minimum line gap between consecutive sections to be considered real (not TOC)
MIN_SECTION_GAP = 50


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------

def find_section_starts(lines: list[str]) -> dict[str, int | None]:
    """
    For each target section, find the line number of the real section header.

    Priority 1 — Format A (title on same line) — unambiguous, take first match.
    Priority 2 — Format B (alone on line) — use gap logic to skip TOC cluster.

    Returns dict: { "Item 1": line_num, ... } — None if not found.
    """
    section_names = [name for name, _ in TARGET_SECTIONS]

    # Collect all matching line numbers for each section
    all_hits: dict[str, list[int]] = {}
    for name, pattern in TARGET_SECTIONS:
        all_hits[name] = [
            i for i, line in enumerate(lines)
            if re.match(pattern, line, re.IGNORECASE)
        ]

    results: dict[str, int | None] = {}

    for idx, (name, _) in enumerate(TARGET_SECTIONS):
        hits = all_hits[name]

        if not hits:
            results[name] = None
            continue

        # Priority 1 — Format A match (title on same line) — unambiguous
        format_a_hits = [
            i for i in hits
            if re.match(FORMAT_A_PATTERNS[name], lines[i], re.IGNORECASE)
        ]
        if format_a_hits:
            results[name] = format_a_hits[0]
            continue

        # Priority 2 — Format B — single occurrence, take directly
        if len(hits) == 1:
            results[name] = hits[0]
            continue

        # Priority 2 — Format B — multiple occurrences, use gap logic
        next_name  = section_names[idx + 1] if idx + 1 < len(section_names) else None
        next_hits  = all_hits.get(next_name, []) if next_name else []

        chosen = hits[-1]   # fallback — last occurrence
        for hit in hits:
            future_next = [n for n in next_hits if n > hit]
            if future_next:
                gap = future_next[0] - hit
                if gap > MIN_SECTION_GAP:
                    chosen = hit
                    break

        results[name] = chosen

    return results


def extract_sections(lines: list[str], starts: dict[str, int | None]) -> dict[str, str | None]:
    """
    Slices lines between section boundaries to extract text per section.

    Returns dict: { "Item 1": "text...", ... } — None if section not found.
    """
    sections: dict[str, str | None] = {}

    for section, end_marker in zip(EXTRACT_TARGETS, END_MARKERS):
        start_line = starts.get(section)
        end_line   = starts.get(end_marker)

        if start_line is None:
            sections[section] = None
            continue

        chunk = lines[start_line:end_line] if end_line is not None else lines[start_line:]
        sections[section] = "\n".join(chunk).strip()

    return sections


# ---------------------------------------------------------------------------
# File processor
# ---------------------------------------------------------------------------

def process_file(ticker: str, year: int) -> bool:
    """
    Reads one parsed JSON, detects sections, writes sections JSON.
    Returns True on success, False on failure.
    """
    src_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_parsed.json")
    out_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_sections.json")

    if not os.path.exists(src_path):
        print(f"  [FAIL] Source not found: {src_path}")
        return False

    with open(src_path, encoding="utf-8") as f:
        data = json.load(f)

    lines    = data["text"].split("\n")
    starts   = find_section_starts(lines)
    sections = extract_sections(lines, starts)

    # Check all 4 sections were found
    missing = [s for s in EXTRACT_TARGETS if sections.get(s) is None]
    if missing:
        print(f"  [WARN] Missing sections: {missing}")

    # Build output record
    record = {
        "ticker":      ticker,
        "year":        year,
        "source_file": src_path,
        "sections":    {k: v for k, v in sections.items() if v is not None},
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    # Report section sizes
    for section in EXTRACT_TARGETS:
        text = sections.get(section)
        if text:
            words = len(text.split())
            print(f"    {section:10s} -> {words:>6,} words")
        else:
            print(f"    {section:10s} -> MISSING")

    size_kb = os.path.getsize(out_path) / 1024
    print(f"  [OK] Saved -> {out_path}  ({size_kb:.1f} KB)")
    return len(missing) == 0


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def detect_all(single_file: tuple[str, int] | None = None) -> None:
    """
    Runs section detection on all 25 filings (or one file if single_file given).
    single_file: (ticker, year) tuple — e.g. ("AAPL", 2020)
    """
    os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

    if single_file:
        jobs = [single_file]
    else:
        jobs = [
            (ticker, year)
            for ticker in COMPANIES.values()
            for year in YEARS
        ]

    total   = len(jobs)
    success = 0
    failed  = 0

    for ticker, year in jobs:
        print(f"\n{'='*55}")
        print(f"  {ticker} — {year}")
        print(f"{'='*55}")

        ok = process_file(ticker, year)
        if ok:
            success += 1
        else:
            failed += 1

    print(f"\n{'='*55}")
    print(f"  SECTION DETECTION SUMMARY")
    print(f"{'='*55}")
    print(f"  Total   : {total}")
    print(f"  Success : {success}")
    print(f"  Failed  : {failed}")
    print(f"{'='*55}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3:
        # Single file mode: python ingestion/section_detector.py AAPL 2020
        ticker = sys.argv[1].upper()
        year   = int(sys.argv[2])
        print(f"Single file mode: {ticker} {year}")
        detect_all(single_file=(ticker, year))
    else:
        # Full run: python ingestion/section_detector.py
        print("Full run: all 25 filings")
        detect_all()
