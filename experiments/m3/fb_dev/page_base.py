"""Q112 step 1: is FinanceBench `evidence_page_num` 0-based or 1-based? (FB-dev 50 only.)

For each evidence page, compare its `evidence_text_full_page` with the text of the PDF pages
around it (pdfplumber). The best match tells the base. Free, no LLM.

Run: uv run python experiments/m3/fb_dev/page_base.py
"""

from __future__ import annotations

import re
from collections import Counter

import pdfplumber

from filing_rag.config import get_settings
from filing_rag.evaluation.locked import load_fb_dev


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{3,}|\d[\d,.]*", text.lower()))


def overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / max(1, len(a))


def main() -> None:
    s = get_settings()
    offsets: Counter[int] = Counter()
    weak = []
    for row in load_fb_dev(s):
        for ev in row["evidence"]:
            num = int(ev["evidence_page_num"])
            target = words(ev.get("evidence_text_full_page") or ev["evidence_text"])
            pdf = s.pdf_dir / f"{ev['doc_name']}.pdf"
            if not pdf.exists():
                weak.append((row["financebench_id"], ev["doc_name"], "no pdf"))
                continue
            with pdfplumber.open(pdf) as doc:
                scores = {}
                for idx in range(max(0, num - 2), min(len(doc.pages), num + 3)):
                    scores[idx - num] = overlap(target, words(doc.pages[idx].extract_text() or ""))
            best = max(scores, key=lambda k: scores[k])
            if scores[best] < 0.6:
                weak.append((row["financebench_id"], ev["doc_name"], round(scores[best], 2)))
            offsets[best] += 1
    print("PDF index (0-based) minus evidence_page_num -> count:", dict(offsets))
    print("0 means evidence_page_num is a 0-based index (viewer page = num + 1).")
    print("weak matches:", weak)


if __name__ == "__main__":
    main()
