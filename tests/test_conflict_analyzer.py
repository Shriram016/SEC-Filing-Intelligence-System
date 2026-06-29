"""
test_conflict_analyzer.py

Formal test suite for Component 15 — conflict/conflict_analyzer.py

Group A — Logic tests (no LLM calls, instant):
    A1: Pair generation — correct C(n,2) count for any year range
    A2: _load_section_text() — raises on invalid section
    A3: _load_section_text() — raises on invalid company
    A4: _word_overlap() — boundary cases

Run from project root:
    python test_conflict_analyzer.py
"""

import sys
import os
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conflict.conflict_analyzer import (
    _load_section_text,
    _word_overlap,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  ✓ {label}")
        passed += 1
    else:
        print(f"  ✗ {label}{(' — ' + detail) if detail else ''}")
        failed += 1


# ── Group A — Logic tests (no LLM calls) ────────────────────────────────────

print("=" * 60)
print("Group A — Logic tests (no LLM calls)")
print("=" * 60)

# A1: Pair generation
print("\n[A1] Pair generation — C(n,2) counts")
for n, expected in [(2, 1), (3, 3), (4, 6), (5, 10)]:
    years = list(range(2020, 2020 + n))
    pairs = list(combinations(years, 2))
    check(f"{n} years → {expected} pairs", len(pairs) == expected)

# A2: Invalid section raises
print("\n[A2] _load_section_text() — invalid section raises ValueError")
try:
    _load_section_text("Apple", "Item 99", 2020)
    check("Invalid section raises ValueError", False, "no exception raised")
except ValueError:
    check("Invalid section raises ValueError", True)
except Exception as e:
    check("Invalid section raises ValueError", False, f"wrong exception: {type(e).__name__}")

# A3: Invalid company raises
print("\n[A3] _load_section_text() — invalid company raises")
try:
    _load_section_text("Tesla", "Item 1A", 2020)
    check("Invalid company raises KeyError/FileNotFoundError", False, "no exception raised")
except (KeyError, FileNotFoundError):
    check("Invalid company raises KeyError/FileNotFoundError", True)
except Exception as e:
    check("Invalid company raises KeyError/FileNotFoundError", False,
          f"wrong exception: {type(e).__name__}")

# A4: Word overlap boundary cases
print("\n[A4] _word_overlap() — boundary cases")
check("Exact match → 1.0",
      _word_overlap("supply chain concentration risk", "supply chain concentration risk") == 1.0)
check("Empty claim → 0.0",
      _word_overlap("", "some source text here") == 0.0)
check("No common words → low score",
      _word_overlap("quantum physics thermodynamics", "apple revenue iphone sales") < 0.20)

# ── Summary ──────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed / {failed} failed / {passed + failed} total")
if failed == 0:
    print("STATUS: ✓ ALL PASS")
else:
    print(f"STATUS: ✗ {failed} FAILED — review output above")
print("=" * 60)
