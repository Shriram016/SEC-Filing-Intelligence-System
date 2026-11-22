"""Free check of draft dev questions: is the first number of the gold answer on the evidence page?

Uses pypdfium2 (a different reader from the ingest code). For calculate / compare questions
the result is not on the page, so the input numbers are checked: the numbers in parentheses,
or (if there are none) all numbers after the first.

Run: uv run python experiments/m1c/check_numbers.py
"""

from __future__ import annotations

import json
import re

import pypdfium2 as pdfium

from filing_rag.config import get_settings
from filing_rag.ingest.catalog import resolve_pdf

NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
PAREN_RE = re.compile(r"\(([^)]*)\)")
DERIVED = {"calculate", "compare_years", "compare_companies"}


def page_text(path: object, page: int) -> str:
    pdf = pdfium.PdfDocument(path)
    tp = pdf[page - 1].get_textpage()
    text = tp.get_text_range()
    tp.close()
    pdf.close()
    return text.replace("\xa0", " ")


def main() -> None:
    s = get_settings()
    rows = [json.loads(x) for x in (s.eval_dir / "dev_set.jsonl").read_text("utf-8").splitlines()]
    bad = 0
    for q in rows:
        if q["expected_route"] != "answer":
            continue
        m = NUM_RE.search(q["gold_answer"])
        if not m:
            print(f"{q['id']}: no number in the answer (text answer) - skip")
            continue
        texts = [page_text(resolve_pdf(s, e["doc_name"])[0], e["page"]) for e in q["evidence"]]
        if q["category"] in DERIVED:
            # the results are calculated; the input numbers (in parentheses, else after the first)
            # must be on a page
            inside = " ".join(PAREN_RE.findall(q["gold_answer"]))
            nums = NUM_RE.findall(inside) or NUM_RE.findall(q["gold_answer"])[1:]
        else:
            nums = [m.group(0)]
        missing = [n for n in nums if not any(n in t for t in texts)]
        tag = "OK " if nums and not missing else ("n/a" if not nums else "MISS")
        bad += tag == "MISS"
        print(f"{q['id']}: {tag} {' '.join(nums)}" + (f"  missing: {missing}" if missing else ""))
    print(f"misses: {bad}")


if __name__ == "__main__":
    main()
