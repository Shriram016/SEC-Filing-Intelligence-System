"""Print the lines our reader makes for some pages, with the TOC decision.

Run: uv run python experiments/m2/show_lines.py DOC PAGE[,PAGE...] [max_lines]
"""

from __future__ import annotations

import sys

from filing_rag.config import get_settings
from filing_rag.ingest.catalog import resolve_pdf
from filing_rag.ingest.layout import read_pdf
from filing_rag.ingest.sections import is_toc_page, match_item

doc, pages = sys.argv[1], [int(x) for x in sys.argv[2].split(",")]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 40
path, _ = resolve_pdf(get_settings(), doc)
for p in read_pdf(path):
    if p.number in pages:
        texts = [ln.text for ln in p.lines]
        items = [t for t in texts if match_item(t)]
        toc = is_toc_page(texts)
        print(f"== {doc} p{p.number}: {len(texts)} lines, {len(items)} item lines, toc={toc}")
        for ln in p.lines[:limit]:
            print(f"   {'B' if ln.bold else ' '} {ln.size:4.1f} | {ln.text[:110]}")
