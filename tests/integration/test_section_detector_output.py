"""
test_section_detector_output.py
--------------------------------
Validates all 25 _sections.json files produced by section_detector.py.

Checks per file:
  1. File exists on disk
  2. All 4 sections present (Item 1, 1A, 7, 7A)
  3. No section is empty
  4. Word count minimums met per section
  5. Expected keywords found in each section

Run from project root:
    python test_section_detector_output.py
"""

import os
import json

# ---------------------------------------------------------------------------
# Config
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

EXTRACT_TARGETS = ["Item 1", "Item 1A", "Item 7", "Item 7A"]

# Minimum word counts per section — based on observed data across all 25 files
MIN_WORD_COUNTS = {
    "Item 1":  500,
    "Item 1A": 1_000,
    "Item 7":  1_000,
    "Item 7A": 100,
}

# Keywords that must appear in each section
EXPECTED_KEYWORDS = {
    "Item 1":  ["business", "products", "services", "employees", "competition"],
    "Item 1A": ["risk", "adverse", "uncertainty", "may", "could"],
    "Item 7":  ["operating", "results", "operations", "financial condition"],
    "Item 7A": ["market risk", "interest rate", "foreign currency", "exchange"],
}


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_file(ticker: str, year: int) -> tuple[bool, list[str]]:
    """
    Validates one _sections.json file.
    Returns (passed: bool, issues: list of failure messages).
    """
    filepath = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_sections.json")
    issues   = []

    # Check 1 — file exists
    if not os.path.exists(filepath):
        return False, [f"File not found: {filepath}"]

    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    sections = data.get("sections", {})

    for section in EXTRACT_TARGETS:
        text = sections.get(section)

        # Check 2 — section present
        if text is None:
            issues.append(f"{section}: MISSING")
            continue

        # Check 3 — not empty
        if not text.strip():
            issues.append(f"{section}: EMPTY")
            continue

        words = len(text.split())

        # Check 4 — word count minimum
        min_words = MIN_WORD_COUNTS[section]
        if words < min_words:
            issues.append(f"{section}: only {words} words (min {min_words})")

        # Check 5 — expected keywords
        text_lower = text.lower()
        for kw in EXPECTED_KEYWORDS[section]:
            if kw not in text_lower:
                issues.append(f"{section}: keyword '{kw}' not found")

    return len(issues) == 0, issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_validations() -> None:
    print("=" * 60)
    print("  Section Detector Output Validation — all 25 files")
    print("=" * 60)

    total   = 0
    passed  = 0
    failed  = 0
    all_results = []

    for company, ticker in COMPANIES.items():
        for year in YEARS:
            total += 1
            ok, issues = validate_file(ticker, year)

            if ok:
                passed += 1
                status = "PASS"
                mark   = "+"
            else:
                failed += 1
                status = "FAIL"
                mark   = "-"

            all_results.append((ticker, year, ok, issues))
            print(f"  [{mark}] {ticker}_{year}  {status}")
            if issues:
                for issue in issues:
                    print(f"         ! {issue}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total  : {total}")
    print(f"  Passed : {passed}")
    print(f"  Failed : {failed}")

    if failed == 0:
        print(f"\n  ALL 25 FILES VALID — section_detector.py output confirmed")
    else:
        print(f"\n  {failed} FILE(S) NEED ATTENTION — review issues above")

    print(f"{'=' * 60}")

    # Word count overview — useful for spotting outliers
    print(f"\n{'=' * 60}")
    print(f"  WORD COUNT OVERVIEW (all 25 files)")
    print(f"{'=' * 60}")
    print(f"  {'File':<20} {'Item 1':>8} {'Item 1A':>9} {'Item 7':>8} {'Item 7A':>9}")
    print(f"  {'-'*20} {'-'*8} {'-'*9} {'-'*8} {'-'*9}")

    for company, ticker in COMPANIES.items():
        for year in YEARS:
            filepath = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_sections.json")
            if not os.path.exists(filepath):
                continue
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            sections = data.get("sections", {})
            counts = {s: len(sections[s].split()) if sections.get(s) else 0
                      for s in EXTRACT_TARGETS}
            print(f"  {ticker}_{year:<15} "
                  f"{counts['Item 1']:>8,} "
                  f"{counts['Item 1A']:>9,} "
                  f"{counts['Item 7']:>8,} "
                  f"{counts['Item 7A']:>9,}")

    print(f"{'=' * 60}")


if __name__ == "__main__":
    run_all_validations()
