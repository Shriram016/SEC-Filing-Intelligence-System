"""Code-made context text (Q93, Q95). No LLM.

- `chunk_header`: the section path put before every chunk, e.g.
  "Adobe 10-K FY2018 › Item 8. Financial Statements › Note 12 Income Taxes".
- Label depth (Q99): what goes into the embedded text.
  "none" = no label; "section" = company, type, period + section (default);
  "full" = + subsection and heading. The stored fields keep the full path.
- `table_label`: the search label of a table chunk: header + table title + unit + columns.
  The table title is always in it (Q105): it is part of the table, not a label level.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

LabelDepth = Literal["none", "section", "full"]
LABEL_DEPTHS: tuple[LabelDepth, ...] = ("none", "section", "full")


@dataclass(frozen=True)
class DocMeta:
    doc_name: str
    company: str
    doc_type: str
    fiscal_year: int
    fiscal_quarter: int | None = None
    list_fiscal_year: int | None = None
    period_end: date | None = None
    report_date: date | None = None
    period_source: str = "estimated"


def period_label(meta: DocMeta) -> str:
    if meta.doc_type == "8-K" and meta.report_date:
        return f"dated {meta.report_date.isoformat()}"
    label = f"FY{meta.fiscal_year}"
    if meta.fiscal_quarter and meta.doc_type in ("10-Q", "earnings"):
        label += f" Q{meta.fiscal_quarter}"
    return label


def chunk_header(
    meta: DocMeta,
    section: str | None,
    subsection: str | None,
    heading: str | None,
    depth: LabelDepth = "full",
) -> str:
    if depth == "none":
        return ""
    head = f"{meta.company} {meta.doc_type} {period_label(meta)}"
    parts = (section,) if depth == "section" else (section, subsection, heading)
    path = [p for p in parts if p]
    return " › ".join([head, *path])


def collapse(text: str) -> str:
    """Runs of spaces → one space, per line (alignment matters for reading, not embedding)."""
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def table_label(header_text: str, title: str | None, unit: str | None, columns: list[str]) -> str:
    parts = [header_text + "."] if header_text else []
    parts.append(f"Table: {title}." if title else "Table.")
    if unit:
        parts.append(f"Unit: {unit}.")
    cols = " ".join(collapse(c) for c in columns).strip()
    if cols:
        parts.append(f"Columns: {cols}.")
    return " ".join(parts)
