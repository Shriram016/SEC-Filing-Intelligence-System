"""Automatic label checks (run on every document; results go to the run report).

The chunk label = "Company type year › section › subsection › heading". Company, type and
year come from the catalog; the section path comes from headings and can be wrong. These
rules flag chunks whose label looks wrong. The tracker already rejects most of these cases
("leave it out when unsure"), so a flag here means a case the safety rule did not catch.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from filing_rag.ingest.chunker import Chunk
from filing_rag.ingest.sections import (
    ITEM_ORDER,
    NOTE_RE,
    heading_shape_ok,
    is_financial_section,
    row_like,
)

SECTION_ITEM_RE = re.compile(r"(?:Part (I{1,2}), )?Item (\d{1,2}[A-C]?)\b")
NOTE_NUM_RE = re.compile(r"^\s*(?:note\s+)?(\d{1,2})\b", re.IGNORECASE)
LONG_SPAN_PAGES = 25
MAX_EXAMPLES = 5


def _flag(out: list[dict[str, Any]], rule: str, c: Chunk, detail: str) -> None:
    out.append({"rule": rule, "chunk_id": c.chunk_id, "page": c.page, "detail": detail})


def _statements_section(doc_type: str, section: str | None) -> bool:
    """Sections that hold the financial statements and their notes."""
    if section is None:
        return False
    if doc_type == "10-Q":
        return section.endswith("Item 1. Financial Statements") or "Item 1." in section
    return "Item 8" in section or section == "Exhibit 13"


def check_labels(doc_type: str, chunks: list[Chunk]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    last_item: dict[str | None, int] = {}
    last_note = 0
    last_section: str | None = None
    runs: list[tuple[str | None, str | None, int, int]] = []  # connected runs of one label
    for c in chunks:
        if c.section != last_section:
            last_note, last_section = 0, c.section
        m = SECTION_ITEM_RE.match(c.section or "") if doc_type != "8-K" else None
        if m:
            part, idx = m.group(1), ITEM_ORDER.index(m.group(2))
            if idx < last_item.get(part, -1):
                _flag(flags, "item_backwards", c, c.section or "")
            last_item[part] = max(idx, last_item.get(part, -1))
        part = m.group(1) if m else None
        if c.subsection and not NOTE_RE.match(c.subsection):
            last_note = 0  # another heading between notes: a new list may start
        explicit = bool(c.subsection and c.subsection.lower().startswith("note"))
        in_statements = _statements_section(doc_type, c.section)
        if c.subsection and NOTE_RE.match(c.subsection) and (explicit or in_statements):
            if not is_financial_section(doc_type, part, c.section):
                _flag(flags, "note_outside_financial", c, f"{c.section} › {c.subsection}")
            nm = NOTE_NUM_RE.match(c.subsection)
            if nm:
                n = int(nm.group(1))
                if n < last_note and n != 1:  # a restart at 1 is a new numbered list
                    _flag(flags, "note_backwards", c, c.subsection)
                last_note = max(last_note, n)
        for name, value in (("subsection", c.subsection), ("heading", c.heading)):
            if value and not heading_shape_ok(value.rstrip("…")):
                _flag(flags, "heading_shape", c, f"{name}: {value}")
        if c.is_table and c.table_title and row_like(c.table_title):
            _flag(flags, "table_title_shape", c, c.table_title[:80])
        if c.subsection:
            if runs and runs[-1][:2] == (c.section, c.subsection):
                runs[-1] = (c.section, c.subsection, runs[-1][2], c.page_end)
            else:
                runs.append((c.section, c.subsection, c.page, c.page_end))
    for sec, sub, start, end in runs:
        if end - start > LONG_SPAN_PAGES:
            flags.append(
                {
                    "rule": "long_span",
                    "chunk_id": None,
                    "page": start,
                    "detail": f"{sec} › {sub}: pages {start}-{end}",
                }
            )
    return flags


def summarise(flags: list[dict[str, Any]]) -> dict[str, Any]:
    by_rule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in flags:
        by_rule[f["rule"]].append(f)
    return {
        rule: {"count": len(items), "examples": items[:MAX_EXAMPLES]}
        for rule, items in sorted(by_rule.items())
    }
