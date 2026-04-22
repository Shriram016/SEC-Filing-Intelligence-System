"""
test_parser.py
--------------
Tests parser.py logic on ONE file (AAPL_2020.htm) before running on all 25.

Verifies:
  1. BeautifulSoup + lxml loads the file
  2. Tag removal works (script, style, ix:header, ix:hidden)
  3. Clean text extraction (no HTML junk)
  4. Output JSON is well-formed
  5. Sample text looks like real 10-K content

Run:  python test_parser.py
"""

import os
import json
from ingestion.parser import extract_text

SRC_PATH = os.path.join("data", "raw",       "AAPL_2020.htm")
OUT_PATH = os.path.join("data", "processed", "AAPL_2020_parsed.json")


def main():
    print(f"\n{'='*60}")
    print(f"  TEST — Parser on AAPL 2020")
    print(f"{'='*60}")

    if not os.path.exists(SRC_PATH):
        print(f"[FAIL] Source file missing: {SRC_PATH}")
        return

    # --- Run the extractor ---
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    text = extract_text(SRC_PATH)

    record = {
        "ticker":      "AAPL",
        "year":        2020,
        "source_file": SRC_PATH,
        "char_count":  len(text),
        "text":        text,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"\n[OK] Saved → {OUT_PATH}  ({size_kb:.1f} KB)")

    # --- Verification checks ---
    print(f"\n{'='*60}")
    print(f"  VERIFICATION CHECKS")
    print(f"{'='*60}")

    checks = {
        "Non-empty text"              : len(text) > 10_000,
        "Company name 'Apple'"        : "apple"               in text.lower(),
        "Form type '10-K'"            : "10-k"                in text.lower(),
        "Year '2020'"                 : "2020"                in text,
        "Fiscal year reference"       : "fiscal 2020"         in text.lower()
                                        or "september 2020"   in text.lower()
                                        or "september 26, 2020" in text.lower(),
        "Revenue / Net sales"         : "net sales"           in text.lower(),
        "Risk factors section"        : "risk factors"        in text.lower(),
        "iPhone mentioned"            : "iphone"              in text.lower(),
        "No raw HTML tags leaked"     : "<div" not in text and "<span" not in text and "<p>" not in text,
        "No XBRL namespace leaked"    : "ix:" not in text and "xbrli:" not in text,
    }

    all_passed = True
    for label, result in checks.items():
        status = "PASS" if result else "FAIL"
        mark   = "+" if result else "-"
        print(f"  [{mark}] {label:35s} {status}")
        if not result:
            all_passed = False

    # --- Sample text (chars 2000–3500) ---
    print(f"\n{'='*60}")
    print(f"  SAMPLE TEXT (chars 2000–3500)")
    print(f"{'='*60}")
    print(text[2000:3500])

    # --- Final verdict ---
    print(f"\n{'='*60}")
    if all_passed:
        print(f"  ALL CHECKS PASSED  -  parser logic confirmed")
        print(f"  Next: delete this test file's output and run parser.py on all 25")
    else:
        print(f"  SOME CHECKS FAILED  -  inspect sample text above")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
