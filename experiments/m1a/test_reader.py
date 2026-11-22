"""M1a step 3: score pdfplumber against the hand-made correct cells.

Settings tested:
- lines: pdfplumber default table finder (ruling lines)
- text:  table finder based on text alignment (for tables without lines)

Per correct cell, three levels:
- found:  the value appears in the page output (plain text or any table)
- row:    the value is in a table row whose label matches the correct row name
- column: as "row", and the column header text contains the key words of the correct
          column (approximate: multi-level headers are matched on their last part)

Run: uv run python experiments/m1a/test_reader.py
Writes: experiments/m1a/results/reader_pdfplumber.json
"""

from __future__ import annotations

import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pdfplumber

from filing_rag.config import get_settings

HERE = Path(__file__).parent
OUT = HERE / "results" / "reader_pdfplumber.json"

SETTINGS: dict[str, dict[str, Any]] = {
    "lines": {},
    "text": {"vertical_strategy": "text", "horizontal_strategy": "text"},
    # fewer false column edges: a column edge needs at least 5 aligned words
    "text_tuned": {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "min_words_vertical": 5,
        "text_x_tolerance": 2,
    },
}
COL_WINDOW = 45.0  # points: max horizontal distance between a value and its header word
DASHES = {"—", "–", "-", "−"}
STOP = {"the", "of", "and", "to", "be", "ended", "months", "notes", "%", "/"}


def norm_value(v: str | None) -> str:
    """'(1,058)' -> '-1058'; '$ 2,634.3' -> '2634.3'; '—' -> 'DASH'; '18.0%' -> '18.0%'."""
    if v is None:
        return ""
    s = re.sub(r"\s+", " ", v).strip()
    if s in DASHES or s.replace("$", "").replace("S", "").strip() in DASHES:
        return "DASH"
    t = s.replace("$", "").replace(" ", "")
    t = re.sub(r"^S(?=\d)", "", t)  # ULTA font prints $ as S
    t = re.sub(r"\(\d+\)$", "", t) if re.search(r"\d\(\d\)$", t) else t  # trailing footnote
    m = re.fullmatch(r"\(([\d,.]+)\)(%?)", t) or re.fullmatch(r"\(([\d,.]+)(%?)\)", t)
    if m:
        return "-" + m.group(1).replace(",", "") + m.group(2)
    if re.fullmatch(r"[\d,]+(\.\d+)?%?", t):
        return t.replace(",", "")
    return re.sub(r"\s+", " ", s).lower()


def norm_label(s: str) -> str:
    s = re.sub(r"\(\w\)|\(\d\)", "", s.lower())
    return re.sub(r"[^a-z0-9 ]+", " ", s).split(":")[0].strip()


def similar(a: str, b: str) -> float:
    a, b = norm_label(a), norm_label(b)
    a, b = " ".join(a.split()), " ".join(b.split())
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0 if min(len(a), len(b)) >= 4 else 0.0
    return SequenceMatcher(None, a, b).ratio()


def key_words(column: str) -> set[str]:
    last = column.split(" / ")[-1]
    words = re.findall(r"[a-z0-9.]+", last.lower())
    return {w for w in words if w not in STOP and len(w) > 1}


def text_values(text: str) -> set[str]:
    toks = text.replace("$", " ").split()
    vals = {norm_value(t) for t in toks}
    # also join "(" "1,058" ")" style splits and "S 2,634.3"
    vals |= {norm_value(a + b) for a, b in zip(toks, toks[1:], strict=False)}
    return vals


def row_label(row: list[str | None]) -> str:
    for c in row:
        if c and re.search(r"[A-Za-z]{2,}", c):
            return c
    return ""


def column_headers(table: list[list[str | None]]) -> list[str]:
    """Join the non-numeric cells above the first data row, per column."""
    width = max(len(r) for r in table)
    headers = [""] * width
    for row in table:
        cells = [c or "" for c in row]
        if any(re.search(r"\d[\d,]{2,}", c) for c in cells[1:]):
            break
        for i, c in enumerate(cells):
            headers[i] += " " + c
    return [" ".join(h.split()) for h in headers]


def score_cell(
    cell: dict[str, Any], text: str, tables: list[list[list[str | None]]]
) -> dict[str, Any]:
    gold = norm_value(cell["value"])
    gold_row = cell["row"].split(" / ")[-1]
    found = gold in text_values(text)
    row_ok = col_ok = False
    seen_in_table = False
    col_note = ""
    for table in tables:
        if not table:
            continue
        headers = column_headers(table)
        for row in table:
            norm_cells = [norm_value(c) for c in row]
            # value split over two cells, e.g. "(1,058" + ")" or "$" + "315"
            joined = [norm_value((row[i] or "") + (row[i + 1] or "")) for i in range(len(row) - 1)]
            hits = [i for i, v in enumerate(norm_cells) if v == gold]
            hits += [i for i, v in enumerate(joined) if v == gold]
            if not hits:
                continue
            seen_in_table = True
            if similar(gold_row, row_label(row)) >= 0.8:
                row_ok = True
                kw = key_words(cell["column"])
                for i in hits:
                    h = " ".join(headers[max(0, i - 1) : i + 2]).lower()  # tolerate 1-col shift
                    if kw and all(k in h for k in kw):
                        col_ok = True
                if not col_ok:
                    col_note = f"headers near hit: {[headers[i] for i in hits][:2]}"
    return {
        "id": cell["id"],
        "found": found or seen_in_table,
        "in_table": seen_in_table,
        "row": row_ok,
        "column": col_ok,
        "note": col_note,
    }


def column_key(column: str) -> set[str]:
    """Years in the column path if any (most specific), else the words of the last part."""
    years = set(re.findall(r"\b(?:19|20)\d\d\b", column))
    return years or key_words(column)


def score_geometry(cell: dict[str, Any], words: list[dict[str, Any]]) -> dict[str, bool]:
    """Row and column check from word positions (independent of the table finder).

    row:    a text line holds the row name (left side) and the value.
    column: every column key word is printed above the value, horizontally close to it.
    """
    gold = norm_value(cell["value"])
    gold_row = cell["row"].split(" / ")[-1]
    lines: dict[int, list[dict[str, Any]]] = {}
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        key = next((k for k in lines if abs(k - w["top"]) <= 3), round(w["top"]))
        lines.setdefault(key, []).append(w)
    row_ok = col_ok = False
    for top, line in lines.items():
        line = sorted(line, key=lambda w: w["x0"])
        label = " ".join(w["text"] for w in line if not re.search(r"\d", w["text"]))
        spans = [(w["x0"], w["x1"], norm_value(w["text"])) for w in line]
        spans += [
            (a["x0"], b["x1"], norm_value(a["text"] + b["text"]))
            for a, b in zip(line, line[1:], strict=False)
        ]
        hits = [(x0, x1) for x0, x1, v in spans if v == gold]
        if not hits or similar(gold_row, label) < 0.8:
            continue
        row_ok = True
        keys = column_key(cell["column"])
        for x0, x1 in hits:
            above = [
                w
                for w in words
                if w["bottom"] <= top + 1
                and w["x1"] >= x0 - COL_WINDOW
                and w["x0"] <= x1 + COL_WINDOW
            ]
            text_above = " ".join(w["text"].lower() for w in above)
            if keys and all(k in text_above for k in keys):
                col_ok = True
    return {"geo_row": row_ok, "geo_column": col_ok}


def main() -> None:
    settings = get_settings()
    pages = json.loads((HERE / "test_pages.json").read_text(encoding="utf-8"))
    gold = json.loads((HERE / "gold_cells.json").read_text(encoding="utf-8"))["cells"]
    results: dict[str, Any] = {"settings": {}, "pages": {}}

    for sname, tset in SETTINGS.items():
        cell_scores = []
        page_info = []
        for p in pages:
            pdf_path = settings.pdf_dir / f"{p['doc_name']}.pdf"
            t0 = time.perf_counter()
            error = ""
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    page = pdf.pages[p["page_index"]]
                    text = page.extract_text() or ""
                    tables = page.extract_tables(tset)
                    words = page.extract_words()
            except Exception as exc:
                text, tables, words, error = "", [], [], str(exc)
            secs = time.perf_counter() - t0
            page_info.append(
                {
                    "doc_name": p["doc_name"],
                    "page_number": p["page_number"],
                    "kind": p["kind"],
                    "seconds": round(secs, 3),
                    "tables": len(tables),
                    "chars": len(text),
                    "error": error,
                }
            )
            results["pages"].setdefault(f"{p['doc_name']}|{p['page_number']}", {})[sname] = {
                "text": text,
                "tables": tables,
            }
            for c in gold:
                if c["doc_name"] == p["doc_name"] and c["page_number"] == p["page_number"]:
                    s = score_cell(c, text, tables)
                    s.update(score_geometry(c, words))
                    s.update(doc_name=c["doc_name"], page_number=c["page_number"], value=c["value"])
                    cell_scores.append(s)
        n = len(cell_scores)
        summary = {
            k: round(100 * sum(s[k] for s in cell_scores) / n, 1)
            for k in ("found", "in_table", "row", "column", "geo_row", "geo_column")
        }
        results["settings"][sname] = {
            "summary_pct": summary,
            "cells": cell_scores,
            "pages": page_info,
            "seconds_total": round(sum(x["seconds"] for x in page_info), 2),
        }
        print(f"[{sname}] n={n} {summary}  time={results['settings'][sname]['seconds_total']}s")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
