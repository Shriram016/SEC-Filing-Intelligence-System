"""Print the text of the picked pages of one slot (for drafting questions).

Run: uv run python experiments/m1c/show_pages.py <slot> [max_chars]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pdfplumber

from filing_rag.config import get_settings
from filing_rag.ingest.catalog import resolve_pdf

HERE = Path(__file__).parent


def main() -> None:
    slot = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 3500
    s = get_settings()
    picks = json.loads((HERE / "pages.json").read_text(encoding="utf-8"))["pages"]
    for i, p in enumerate(x for x in picks if x["slot"] == slot):
        path, _ = resolve_pdf(s, p["doc_name"])
        with pdfplumber.open(path) as pdf:
            text = pdf.pages[p["page"] - 1].extract_text(layout=True) or ""
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
        body = "\n".join(lines)
        spare = " (spare)" if p["spare"] else ""
        print(f"\n######## {slot} #{i + 1}{spare}: {p['doc_name']} p{p['page']}\n{body[:limit]}")


if __name__ == "__main__":
    main()
