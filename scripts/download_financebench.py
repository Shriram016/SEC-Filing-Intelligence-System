"""Download the FinanceBench PDFs, document list and the 150 questions (free; no LLM calls).

Usage (from the project root):  uv run python scripts/download_financebench.py
"""

import logging
import sys
from pathlib import Path

import httpx

from filing_rag.config import get_settings
from filing_rag.data.financebench import download_financebench

MANIFEST = Path("manifests/financebench.json")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    headers = {"User-Agent": settings.http_user_agent}
    with httpx.Client(headers=headers, timeout=settings.http_timeout_s, follow_redirects=True) as c:
        report = download_financebench(settings, c, MANIFEST)
    print(
        f"downloaded={len(report.downloaded)} skipped={len(report.skipped)} "
        f"failed={len(report.failed)} duplicate_doc_names={report.duplicate_doc_names}"
    )
    for key, err in report.failed.items():
        print(f"FAILED {key}: {err}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
