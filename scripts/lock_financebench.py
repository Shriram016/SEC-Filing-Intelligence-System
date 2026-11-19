"""Lock the 150 FinanceBench questions: record the checksum and the evidence pages.

Usage:  uv run python scripts/lock_financebench.py
"""

import sys

from filing_rag.config import get_settings
from filing_rag.evaluation.locked import lock


def main() -> int:
    manifest = lock(get_settings())
    print(f"locked {manifest['count']} questions, sha256={manifest['sha256'][:12]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
