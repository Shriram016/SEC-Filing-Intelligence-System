"""Structure check: can simple rules find the 10-K Item headings and Note headings?

For each 10-K in the document list:
- read each page's text (pypdfium2, fast);
- a heading line = a short line that starts with "Item <n>" (e.g. "ITEM 7.", "Item 1A:");
- a page with 6+ Item lines is a table of contents (TOC) and is skipped;
- record the first page of each Item; check that Item 7 comes before Item 8;
- inside Item 8 (up to Item 9), count lines that start with "Note <n>" or "<n>. Title".

Run: uv run python experiments/structure/check_10k_items.py
Writes: experiments/structure/results/items_10k.json
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium

from filing_rag.config import get_settings

HERE = Path(__file__).parent
ITEMS = ["1", "1A", "1B", "1C", "2", "3", "4", "5", "6", "7", "7A", "8", "9", "9A", "9B", "9C",
         "10", "11", "12", "13", "14", "15", "16"]  # fmt: skip
ITEM_RE = re.compile(r"^\s*item\s+(\d{1,2}[A-C]?)\s*[.:\-—–]?(\s|$)", re.IGNORECASE)
NOTE_RE = re.compile(r"^\s*(note\s+\d{1,2}\b|\d{1,2}\.\s+[A-Z][A-Za-z]+)", re.IGNORECASE)
TOC_MIN_ITEMS = 6
MAX_HEADING_CHARS = 140


def page_lines(pdf: pdfium.PdfDocument) -> list[list[str]]:
    out = []
    for page in pdf:
        tp = page.get_textpage()
        out.append(tp.get_text_range().splitlines())
        tp.close()
        page.close()
    return out


def analyse(lines_by_page: list[list[str]]) -> dict[str, Any]:
    toc_pages, first_page = [], {}
    for p, lines in enumerate(lines_by_page, start=1):
        hits = [
            m.group(1).upper()
            for line in lines
            if len(line) <= MAX_HEADING_CHARS and (m := ITEM_RE.match(line))
        ]
        if len(set(hits)) >= TOC_MIN_ITEMS:
            toc_pages.append(p)
            continue
        for item in hits:
            if item in ITEMS and item not in first_page:
                first_page[item] = p
    p7, p8, p9 = first_page.get("7"), first_page.get("8"), first_page.get("9")
    notes = 0
    if p8:
        end = p9 if p9 and p9 > p8 else len(lines_by_page)
        for lines in lines_by_page[p8 - 1 : end]:
            notes += sum(1 for line in lines if len(line) <= 100 and NOTE_RE.match(line))
    return {
        "pages": len(lines_by_page),
        "toc_pages": toc_pages,
        "items_found": [i for i in ITEMS if i in first_page],
        "first_page": first_page,
        "order_7_before_8": bool(p7 and p8 and p7 < p8),
        "item8_pages": (p9 - p8) if p8 and p9 and p9 > p8 else None,
        "note_lines_in_item8": notes,
    }


def main() -> None:
    s = get_settings()
    docs: dict[str, dict[str, Any]] = {}
    for line in (s.financebench_dir / "document_information.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r["doc_type"] == "10k":
            docs[r["doc_name"]] = r
    results: dict[str, Any] = {}
    for i, (name, r) in enumerate(sorted(docs.items()), start=1):
        try:
            pdf = pdfium.PdfDocument(s.pdf_dir / f"{name}.pdf")
            res = analyse(page_lines(pdf))
            pdf.close()
        except Exception as e:  # noqa: BLE001 - log and continue
            res = {"error": f"{type(e).__name__}: {e}"}
        res["company"] = r["company"]
        res["year"] = r["doc_period"]
        results[name] = res
        if i % 25 == 0:
            print(f"{i}/{len(docs)}")

    ok = [v for v in results.values() if "error" not in v]
    n = len(ok)
    found = collections.Counter(i for v in ok for i in v["items_found"])
    key = ["1", "1A", "7", "7A", "8", "9A", "15"]
    all_key = sum(1 for v in ok if all(k in v["items_found"] for k in key))
    print(f"\n10-Ks read: {n}, errors: {len(results) - n}")
    print("share of 10-Ks where each Item heading is found (outside the TOC):")
    print("  " + "  ".join(f"{i}:{100 * found[i] / n:.0f}%" for i in ITEMS))
    print(f"all key items {key}: {all_key}/{n}")
    print(f"Item 7 before Item 8: {sum(v['order_7_before_8'] for v in ok)}/{n}")
    print(f"TOC page found: {sum(1 for v in ok if v['toc_pages'])}/{n}")
    notes_ok = sum(1 for v in ok if v["note_lines_in_item8"] >= 5)
    print(f"Note lines found in Item 8 (>=5): {notes_ok}/{n}")

    by_co: dict[str, list[tuple[int, str]]] = collections.defaultdict(list)
    for v in ok:
        by_co[v["company"]].append((v["year"], ",".join(v["items_found"])))
    same = sum(1 for lst in by_co.values() if len({x[1] for x in lst}) == 1)
    print(f"companies with the same item set in every year: {same}/{len(by_co)}")
    weak = sorted(
        (k for k, v in results.items() if "error" in v or not v["order_7_before_8"]),
    )
    print(f"10-Ks without Item 7 then Item 8 found: {len(weak)}")
    for k in weak:
        v = results[k]
        print(f"  {k}: items={v.get('items_found', v.get('error'))}")

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / "items_10k.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
