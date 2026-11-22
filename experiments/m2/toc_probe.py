"""Probe TOC rules on known TOC pages and known body pages with many short Items."""

from __future__ import annotations

from filing_rag.config import get_settings
from filing_rag.ingest.catalog import resolve_pdf
from filing_rag.ingest.layout import read_pdf
from filing_rag.ingest.sections import match_item

CASES = {
    "PG_E_2020_10K": ([4, 5], [214, 215, 216]),
    "Pfizer_2023Q2_10Q": ([3], [63, 64, 65]),
    "PFIZER_2019_10K": ([], [42, 47, 48]),
    "WALMART_2016_10K": ([], [30, 31, 32]),
    "EBAY_2019_10K": ([], [59, 60]),
    "ACTIVISIONBLIZZARD_2015_10K": ([], [87, 89]),
    "APPLE_2019_10K": ([2], []),
    "COSTCO_2019_10K": ([2, 3], []),
}

s = get_settings()
for doc, (toc, body) in CASES.items():
    pages = {p.number: p for p in read_pdf(resolve_pdf(s, doc)[0])}
    for n in toc + body:
        lines = [ln.text for ln in pages[n].lines]
        items = {m[0] for t in lines if (m := match_item(t))}
        words = [len(t.split()) for t in lines]
        short = sum(w <= 14 for w in words) / max(1, len(words))
        head = " / ".join(t[:25] for t in lines[:3])
        kind = "TOC " if n in toc else "body"
        print(f"{kind} {doc} p{n}: items={len(items)} short={short:.2f} n={len(lines)} | {head}")
