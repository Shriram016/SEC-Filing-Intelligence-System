"""Q106 count: how many tables have no title, and how many look cut in two (free, no LLM).

The same detector runs before and after the reader fix, so the two counts compare.

- untitled: table blocks (after the cross-page join) with no title.
- cut A ("label gap"): two tables on one page, 1-2 lines between them, the lines are not rows,
  do not end with a full stop and are not Item headings; the second table has no column
  header of its own; its number columns line up with the first table.
- cut B ("lost top"): a row that is in no table (a 1-row run), then 1-2 such lines, then a
  table with no column header whose columns line up with the row.

Samples for the hand check skip the locked evidence pages and the pages next to them (Q21).

Run (the output folder must not exist):
    uv run python experiments/m2/table_reader/count.py --out before
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from filing_rag.config import get_settings
from filing_rag.ingest.blocks import (
    Block,
    _is_structure_heading,
    body_font_size,
    find_tables,
    is_row,
    join_continued,
    numeric_segment,
    page_blocks,
)
from filing_rag.ingest.catalog import resolve_pdf
from filing_rag.ingest.layout import Line, read_pdf
from filing_rag.ingest.sections import is_toc_page

BASE = Path("experiments/m2/table_reader")
SAMPLE_FILE = BASE / "sample_docs.json"
RANDOM_DOCS = 20
SEED = 106
ALIGN_TOL = 6.0  # points: right edges of the same column
MIN_ALIGNED = 2
UNTITLED_SAMPLE = 40
CONTEXT_LINES = 7


def num_edges(line: Line) -> list[float]:
    """Right edges of the numeric segments of a line."""
    out = []
    for _x0, x1, text in spans(line):
        if numeric_segment(text):
            out.append(x1)
    return out


def spans(line: Line) -> list[tuple[float, float, str]]:
    gap = max(line.size * 0.9, 4.0)
    groups: list[list[Any]] = []
    prev_x1: float | None = None
    for w in line.words:
        if prev_x1 is None or w.x0 - prev_x1 > gap:
            groups.append([w.x0, w.x1, [w.text]])
        else:
            groups[-1][1] = w.x1
            groups[-1][2].append(w.text)
        prev_x1 = w.x1
    return [(a, b, " ".join(t)) for a, b, t in groups]


def aligned(above: list[Line], below: list[Line]) -> bool:
    """At least MIN_ALIGNED number columns of `below` sit under number columns of `above`."""
    top = [e for ln in above for e in num_edges(ln)]
    edges = sorted({round(e) for ln in below[:3] for e in num_edges(ln)})
    hits = sum(1 for e in edges if any(abs(e - t) <= ALIGN_TOL for t in top))
    return hits >= MIN_ALIGNED and hits >= 0.6 * len(edges)


def gap_ok(gap: list[Line]) -> bool:
    return 1 <= len(gap) <= 2 and all(
        not is_row(g)
        and not g.text.rstrip().endswith(".")
        and not _is_structure_heading(g.text.strip())
        for g in gap
    )


def page_cuts(lines: list[Line]) -> list[dict[str, Any]]:
    tables = find_tables(lines)
    in_table = {i for h, _, e in tables for i in range(h, e)}
    cuts: list[dict[str, Any]] = []
    for (_h1, r1, e1), (h2, r2, e2) in zip(tables, tables[1:], strict=False):
        gap = lines[e1:h2]
        if h2 == r2 and gap_ok(gap) and aligned(lines[r1:e1], lines[r2:e2]):
            cuts.append({"kind": "A", "gap": [g.text for g in gap]})
    for h2, r2, e2 in tables:
        if h2 != r2:
            continue
        for k in (1, 2):
            i = h2 - k - 1
            if i < 0 or i in in_table or not is_row(lines[i]):
                continue
            gap = lines[i + 1 : h2]
            if gap_ok(gap) and aligned([lines[i]], lines[r2:e2]):
                cuts.append({"kind": "B", "gap": [g.text for g in gap], "row": lines[i].text})
                break
    return cuts


def near_locked(locked: set[tuple[str, int]], doc: str, page: int) -> bool:
    return any((doc, page + d) in locked for d in (-1, 0, 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="folder name under experiments/m2/table_reader")
    args = ap.parse_args()
    out_dir = BASE / args.out
    if out_dir.exists():
        print(f"{out_dir} exists; choose another --out (no overwrite)")
        return 1
    s = get_settings()

    if SAMPLE_FILE.exists():
        docs = json.loads(SAMPLE_FILE.read_text("utf-8"))["documents"]
    else:
        dev_file = Path("experiments/m2/table_titles/dev_docs.json")
        dev = [d["doc_name"] for d in json.loads(dev_file.read_text("utf-8"))["documents"]]
        catalog = json.loads((s.ingest_dir / "catalog.json").read_text("utf-8"))
        ok = [r["doc_name"] for r in catalog if r["status"] == "ok"]
        rest = sorted(d for d in ok if d not in dev)
        docs = dev + random.Random(SEED).sample(rest, RANDOM_DOCS)
        SAMPLE_FILE.write_text(json.dumps({"note": "Q106: 21 dev documents + 20 random (seed 106)",
                                           "documents": docs}, indent=1), "utf-8")  # fmt: skip
    locked = {(r["doc_name"], int(r["page"])) for r in json.loads(
        (s.eval_dir / "locked_evidence_pages.json").read_text("utf-8"))}  # fmt: skip

    per_doc: dict[str, dict[str, int]] = {}
    cut_rows: list[dict[str, Any]] = []
    untitled_rows: list[dict[str, Any]] = []
    for doc in docs:
        path, _ = resolve_pdf(s, doc)
        pages = read_pdf(path)
        body = body_font_size(pages)
        toc = {p.number for p in pages if is_toc_page([ln.text for ln in p.lines])}
        blocks: list[Block] = []
        lines_of: dict[int, list[Line]] = {}
        counts: Counter[str] = Counter()
        for p in pages:
            if p.number in toc:
                continue
            lines_of[p.number] = p.lines
            blocks.extend(page_blocks(p, body))
            for c in page_cuts(p.lines):
                counts[f"cut_{c['kind']}"] += 1
                cut_rows.append({"doc": doc, "page": p.number} | c)
        tables = [b for b in join_continued(blocks) if b.kind == "table"]
        counts["tables"] = len(tables)
        for b in tables:
            if not b.title:
                counts["untitled"] += 1
                first = b.rows[0].split() if b.rows else []
                untitled_rows.append({"doc": doc, "page": b.page, "first_row": " ".join(first)})
        per_doc[doc] = dict(counts)
        print(doc, dict(counts), flush=True)

    total: Counter[str] = Counter()
    for c in per_doc.values():
        total.update(c)
    out_dir.mkdir(parents=True)
    rng = random.Random(SEED)
    pool = [u for u in untitled_rows if not near_locked(locked, u["doc"], u["page"])]
    sample = rng.sample(pool, min(UNTITLED_SAMPLE, len(pool)))
    cut_sample = [c for c in cut_rows if not near_locked(locked, c["doc"], c["page"])]
    summary = {"documents": len(docs), "total": dict(total), "per_doc": per_doc}
    (out_dir / "counts.json").write_text(json.dumps(summary, indent=1), "utf-8")
    (out_dir / "cuts.json").write_text(json.dumps(cut_sample, indent=1), "utf-8")
    (out_dir / "untitled_sample.json").write_text(json.dumps(sample, indent=1), "utf-8")
    print("TOTAL", dict(total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
