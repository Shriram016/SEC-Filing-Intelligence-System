"""M1a step 1: choose the test pages for the PDF reader test.

Leakage rule (Q21): only documents that no locked question uses. As a second guard,
locked evidence pages +-1 are excluded (page base 0/1 is not yet known).

Selection (fixed seed, repeatable):
- one document per type (10k, 10q, 8k, Earnings, 10k_annualreport), all different companies;
- per document: 3 table-like pages + 1 text page; the 10-K also gets one 2-page table.

"Table-like" = >= 20 financial numbers in the raw page text (3+ digit values, decimals
with 2+ places, percentages, negatives in brackets; years and small integers such as page
or section numbers do not count). Calibrated by eye on 11 pages: prose with numbers
scored <= 10, a table of contents 0-7, real tables 22-109. Raw text only, so the rule does
not favour pages where pdfplumber's table finder already works.

"2-page table" = a table page whose first lines contain "continued", plus the page before.

Run: uv run python experiments/m1a/select_pages.py
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

import pdfplumber

from filing_rag.config import get_settings
from filing_rag.data.financebench import read_jsonl
from filing_rag.evaluation.locked import load_locked_evidence_pages

SEED = 42
DOC_TYPES = ["10k", "10q", "8k", "Earnings", "10k_annualreport"]
TABLE_MIN_NUMBERS = 20
TEXT_MAX_NUMBERS = 3
TEXT_MIN_WORDS = 250
OUT = Path(__file__).parent / "test_pages.json"

# Manual corrections after looking at every selected page (M1a step 2, 2026-11-19).
# The "continued" rule found a section header, not a continued table, in Adobe; the real
# 2-page table is the Lockheed underwriter schedule (headers only on the first page).
MANUAL_KINDS = {
    ("ADOBE_2018_10K", 89): "table",
    ("ADOBE_2018_10K", 90): "table",
    ("LOCKHEEDMARTIN_2023_8K_dated-2023-05-25", 22): "table_multipage",
    ("LOCKHEEDMARTIN_2023_8K_dated-2023-05-25", 23): "table_multipage",
    ("ULTABEAUTY_2024Q1_EARNINGS", 2): "text_numbers",  # prose with many numbers
}

NUMERIC = re.compile(r"\d{1,3}(,\d{3})+(\.\d+)?|\d+(\.\d+)?")
YEAR = re.compile(r"(19|20)\d\d")
TWO_DECIMALS = re.compile(r"\d+\.\d\d+")


def is_financial_number(token: str) -> bool:
    core = token.strip("$()%,;:")
    if not NUMERIC.fullmatch(core) or YEAR.fullmatch(core):
        return False
    digits = core.replace(",", "").split(".")[0]
    return (
        len(digits) >= 3
        or "%" in token
        or token.startswith("(")
        or bool(TWO_DECIMALS.fullmatch(core))
    )


def page_profile(pdf_path: Path) -> list[dict[str, Any]]:
    """Count financial numbers and words per page (0-based page index)."""
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tokens = text.split()
            head = " ".join(text.splitlines()[:4]).lower()
            out.append(
                {
                    "index": i,
                    "numbers": sum(map(is_financial_number, tokens)),
                    "words": len(tokens),
                    "continued": "continued" in head,
                }
            )
    return out


def main() -> None:
    settings = get_settings()
    rng = random.Random(SEED)
    rows = read_jsonl(settings.financebench_dir / "document_information.jsonl")
    docs = {r["doc_name"]: r for r in rows}  # duplicate name collapses to one entry

    locked = load_locked_evidence_pages(settings)
    locked_docs = {doc for doc, _ in locked}
    blocked = {(doc, page + d) for doc, page in locked for d in (-1, 0, 1)}

    used_companies: set[str] = set()
    selected: list[dict[str, Any]] = []
    for doc_type in DOC_TYPES:
        candidates = sorted(
            n
            for n, r in docs.items()
            if r["doc_type"] == doc_type
            and n not in locked_docs
            and r["company"] not in used_companies
            and (settings.pdf_dir / f"{n}.pdf").exists()
        )
        rng.shuffle(candidates)
        for name in candidates:
            try:
                prof = page_profile(settings.pdf_dir / f"{name}.pdf")
            except Exception as exc:  # broken source file: skip, log, continue
                print(f"skip {name}: cannot read ({exc})")
                continue
            prof = [p for p in prof if (name, p["index"]) not in blocked]
            tables = [p for p in prof if p["numbers"] >= TABLE_MIN_NUMBERS]
            texts = [
                p for p in prof if p["numbers"] <= TEXT_MAX_NUMBERS and p["words"] >= TEXT_MIN_WORDS
            ]
            if len(tables) < 3 or not texts:
                print(f"skip {name}: {len(tables)} table pages, {len(texts)} text pages")
                continue

            picks: list[tuple[dict[str, Any], str]] = []
            if doc_type == "10k":
                by_index = {p["index"]: p for p in tables}
                seconds = [p for p in tables if p["continued"] and p["index"] - 1 in by_index]
                if seconds:
                    second = rng.choice(seconds)
                    first = by_index[second["index"] - 1]
                    picks += [(first, "table_multipage"), (second, "table_multipage")]
                else:
                    print(f"skip {name}: no 'continued' table pair")
                    continue
            rest = [p for p in tables if all(p is not q for q, _ in picks)]
            picks += [(p, "table") for p in rng.sample(rest, 3)]
            picks.append((rng.choice(texts), "text"))

            for p, kind in sorted(picks, key=lambda x: x[0]["index"]):
                selected.append(
                    {
                        "doc_name": name,
                        "company": docs[name]["company"],
                        "doc_type": doc_type,
                        "page_index": p["index"],  # 0-based
                        "page_number": p["index"] + 1,  # as shown in a PDF viewer
                        "kind": kind,
                        "numbers": p["numbers"],
                        "words": p["words"],
                    }
                )
            used_companies.add(docs[name]["company"])
            print(f"{doc_type:17} {name}: {len(picks)} pages")
            break
        else:
            print(f"!! no usable document for {doc_type}")

    OUT.write_text(json.dumps(selected, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(selected)} pages to {OUT}")


if __name__ == "__main__":
    main()
