"""Validate eval/dev_set.jsonl (schema, ids, routes) and warn on locked-page overlaps.

Usage:  uv run python scripts/validate_dev_set.py
"""

import sys
from collections import Counter

from filing_rag.config import get_settings
from filing_rag.evaluation.dev_set import validate_dev_set
from filing_rag.evaluation.locked import EVIDENCE_PAGES_NAME, load_locked_evidence_pages


def main() -> int:
    s = get_settings()
    pages = load_locked_evidence_pages(s) if (s.eval_dir / EVIDENCE_PAGES_NAME).exists() else None
    report = validate_dev_set(s.eval_dir / "dev_set.jsonl", pages)
    print(f"questions={len(report.questions)} errors={len(report.errors)}")
    print(dict(Counter(q.category.value for q in report.questions)))
    for e in report.errors:
        print(f"ERROR {e}")
    for w in report.locked_page_overlaps:
        print(f"WARNING uses a locked evidence page: {w}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
