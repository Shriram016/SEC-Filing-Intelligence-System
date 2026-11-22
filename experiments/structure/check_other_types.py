"""Structure check for 10-Q, 8-K, earnings releases and annual reports.

Flexible heading rules (fixes from the 10-K check): no space after the dot, dashes,
non-breaking spaces. A table-of-contents (TOC) page = 6+ distinct Items within the first 5 pages.

- 10-Q: Part I / Part II and Items 1-6 (Part I: 1-4, Part II: 1, 1A, 2-6).
- 8-K: item codes like "Item 2.02", and "Exhibit 99.1" (attached press release).
- Earnings and annual reports: no legal structure → count common headings, and check
  whether an annual report contains a full 10-K (Item 7 + Item 8).

Run: uv run python experiments/structure/check_other_types.py
Writes: experiments/structure/results/other_types.json
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
ITEM_RE = re.compile(r"^\s*item\s*(\d{1,2}[A-C]?)(?!\d|\.\d)\s*[.:\-—–]?", re.IGNORECASE)
ITEM_8K_RE = re.compile(r"^\s*item\s*(\d\.\d{2})\b", re.IGNORECASE)
PART_RE = re.compile(r"^\s*part\s+(I{1,2}|1|2)\b\.?", re.IGNORECASE)
EXHIBIT_RE = re.compile(r"\bexhibit\s*99\.?\d*", re.IGNORECASE)
HEADINGS = {
    "income statement": r"statements? of (income|operations|earnings)",
    "balance sheet": r"balance sheets?|statements? of financial position",
    "cash flow": r"statements? of cash flows?",
    "non-GAAP reconciliation": r"non-gaap|reconciliation",
    "outlook / guidance": r"\boutlook\b|\bguidance\b",
    "segment results": r"\bsegment",
    "highlights": r"highlights",
    "forward-looking statements": r"forward-looking statements",
    "conference call": r"conference call|webcast",
    "letter to shareholders": (
        r"dear (fellow )?(shareholders|stockholders|shareowners)"
        r"|to our (shareholders|stockholders)"
    ),
}  # fmt: skip
MAX_HEADING_CHARS = 140


def read_pages(path: Path) -> list[list[str]]:
    pdf = pdfium.PdfDocument(path)
    out = []
    for page in pdf:
        tp = page.get_textpage()
        out.append([ln.replace("\xa0", " ") for ln in tp.get_text_range().splitlines()])
        tp.close()
        page.close()
    pdf.close()
    return out


def items_by_page(pages: list[list[str]], regex: re.Pattern[str]) -> dict[str, int]:
    first: dict[str, int] = {}
    for p, lines in enumerate(pages, start=1):
        hits = [
            m.group(1).upper()
            for ln in lines
            if len(ln) <= MAX_HEADING_CHARS and (m := regex.match(ln))
        ]
        if p <= 5 and len(set(hits)) >= 6:  # TOC
            continue
        for h in hits:
            first.setdefault(h, p)
    return first


def heading_hits(pages: list[list[str]]) -> list[str]:
    text = "\n".join(ln for lines in pages for ln in lines if len(ln) <= MAX_HEADING_CHARS)
    return [k for k, pat in HEADINGS.items() if re.search(pat, text, re.IGNORECASE)]


def analyse(doc_type: str, pages: list[list[str]]) -> dict[str, Any]:
    res: dict[str, Any] = {"pages": len(pages)}
    if doc_type == "10q":
        res["parts"] = sorted(
            {m.group(1).upper() for ln in sum(pages, []) if (m := PART_RE.match(ln))}
        )
        res["items"] = sorted(items_by_page(pages, ITEM_RE))
    elif doc_type == "8k":
        first = items_by_page(pages, ITEM_8K_RE)
        res["items_8k"] = sorted(first)
        res["exhibit_99"] = any(EXHIBIT_RE.search(ln) for lines in pages for ln in lines)
    else:
        items = items_by_page(pages, ITEM_RE)
        res["has_10k_inside"] = "7" in items and "8" in items
        res["headings"] = heading_hits(pages)
        words = [len(" ".join(lines).split()) for lines in pages]
        res["words_per_page_median"] = sorted(words)[len(words) // 2]
    return res


def main() -> None:
    s = get_settings()
    docs: dict[str, dict[str, Any]] = {}
    for line in (s.financebench_dir / "document_information.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r["doc_type"] != "10k":
            docs[r["doc_name"]] = r
    results: dict[str, Any] = {}
    for name, r in sorted(docs.items()):
        try:
            res = analyse(r["doc_type"], read_pages(s.pdf_dir / f"{name}.pdf"))
        except Exception as e:  # noqa: BLE001 - log and continue
            res = {"error": type(e).__name__}
        res.update(type=r["doc_type"], company=r["company"])
        results[name] = res
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / "other_types.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

    ok = {k: v for k, v in results.items() if "error" not in v}
    print("errors:", [k for k, v in results.items() if "error" in v])

    q = {k: v for k, v in ok.items() if v["type"] == "10q"}
    std_q = [k for k, v in q.items() if {"1", "2", "3", "4"} <= set(v["items"])]
    parts_ok = sum(
        1 for v in q.values() if {"I", "II"} <= set(v["parts"]) or {"1", "2"} <= set(v["parts"])
    )
    print(f"\n10-Q: {len(q)} docs; Items 1-4 found: {len(std_q)}; Part I+II found: {parts_ok}")
    for k, v in q.items():
        if k not in std_q:
            print(f"  not standard: {k} items={v['items']} parts={v['parts']}")

    e = {k: v for k, v in ok.items() if v["type"] == "8k"}
    codes = collections.Counter(c for v in e.values() for c in v["items_8k"])
    print(
        f"\n8-K: {len(e)} docs; item code found: {sum(1 for v in e.values() if v['items_8k'])}; "
        f"Exhibit 99 attached: {sum(v['exhibit_99'] for v in e.values())}"
    )
    print("  item codes:", dict(codes.most_common()))
    for k, v in e.items():
        print(f"  {k}: pages={v['pages']} items={v['items_8k']}")

    for t in ("Earnings", "10k_annualreport"):
        g = {k: v for k, v in ok.items() if v["type"] == t}
        hc = collections.Counter(h for v in g.values() for h in v["headings"])
        print(
            f"\n{t}: {len(g)} docs; contains a full 10-K: "
            f"{sum(v['has_10k_inside'] for v in g.values())}"
        )
        print("  headings found (docs):", dict(hc.most_common()))
        for k, v in g.items():
            print(
                f"  {k}: pages={v['pages']} words/page={v['words_per_page_median']} "
                f"10k_inside={v['has_10k_inside']}"
            )


if __name__ == "__main__":
    main()
