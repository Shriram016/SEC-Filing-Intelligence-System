"""M1b label check 2: measured hand-check of chunk labels.

1. Sample 50 chunks with a fixed seed: 2 per document (22 documents) + 6 more at random.
2. For each chunk, collect independent evidence (not from the ingest code):
   - the page text from pypdfium2 (a different reader);
   - the last "Item ..." and "Note ..." line found before the chunk by a simple scan of the
     document (table-of-contents pages skipped).
3. Render the chunk's page as a PNG for a by-eye check (experiments/m1b/audit_pages/, not
   committed: derived from FinanceBench PDFs).
4. Write experiments/m1b/label_audit.json. Verdicts are filled in by hand afterwards.

Run: uv run python experiments/m1b/label_audit.py [seed] [name]
  round 1: seed 20261120, name label_audit; round 2: seed 20261121, name label_audit_r2
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from typing import Any

import pdfplumber
import pypdfium2 as pdfium

from filing_rag.config import get_settings
from filing_rag.ingest.catalog import resolve_pdf

HERE = Path(__file__).parent
SEED = 20261120
PER_DOC = 2
EXTRA = 6
ITEM_LINE = re.compile(r"^\s*(part\s+i{1,2}\W+)?item\s*\d{1,2}[a-c]?(?!\.?\d)\b.{0,90}$", re.I)
ITEM_8K_LINE = re.compile(r"^\s*item\s*\d\.\d{2}\b.{0,90}$", re.I)
NOTE_LINE = re.compile(
    r"^\s*(note\s+\d{1,2}\b|\d{1,2}\.\s+[A-Z][A-Za-z ,&'-]{3,80}$).{0,90}$", re.I
)
EXHIBIT_LINE = re.compile(r"^\s*exhibit\s+\d{1,3}(\.\d{1,3})?\s*$", re.I)


def page_texts(path: Path) -> list[str]:
    pdf = pdfium.PdfDocument(path)
    out = []
    for page in pdf:
        tp = page.get_textpage()
        out.append(tp.get_text_range().replace("\xa0", " "))
        tp.close()
        page.close()
    pdf.close()
    return out


def last_markers(texts: list[str], page: int, doc_type: str) -> dict[str, Any]:
    """Scan pages 1..page (inclusive) for the last Item / Note / Exhibit line."""
    item_re = ITEM_8K_LINE if doc_type == "8-K" else ITEM_LINE
    found: dict[str, Any] = {"item": None, "note": None, "exhibit": None}
    for p in range(1, page + 1):
        lines = [ln.strip() for ln in texts[p - 1].splitlines() if ln.strip()]
        items = [ln for ln in lines if item_re.match(ln)]
        if len(items) >= 5:  # table of contents / index page
            continue
        for ln in lines:
            if item_re.match(ln):
                found["item"] = (p, ln[:100])
            elif NOTE_LINE.match(ln) and len(ln) < 90:
                found["note"] = (p, ln[:100])
            elif EXHIBIT_LINE.match(ln):
                found["exhibit"] = (p, ln[:100])
    return found


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else SEED
    name = sys.argv[2] if len(sys.argv) > 2 else "label_audit"
    s = get_settings()
    rng = random.Random(seed)
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for f in sorted((s.ingest_dir / "chunks").glob("*.jsonl")):
        by_doc[f.stem] = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]
    sample: list[dict[str, Any]] = []
    for doc in sorted(by_doc):
        sample += rng.sample(by_doc[doc], min(PER_DOC, len(by_doc[doc])))
    taken = {c["chunk_id"] for c in sample}
    rest = [c for cs in by_doc.values() for c in cs if c["chunk_id"] not in taken]
    sample += rng.sample(rest, EXTRA)

    img_dir = HERE / ("audit_pages" if name == "label_audit" else f"audit_pages_{name}")
    img_dir.mkdir(exist_ok=True)
    texts_cache: dict[str, list[str]] = {}
    records = []
    for i, c in enumerate(sample, start=1):
        doc = c["doc_name"]
        path, _ = resolve_pdf(s, doc)
        if doc not in texts_cache:
            texts_cache[doc] = page_texts(path)
        texts = texts_cache[doc]
        img = img_dir / f"{i:02d}_{doc}_p{c['page']}.png"
        if not img.exists():
            with pdfplumber.open(path) as pdf:
                pdf.pages[c["page"] - 1].to_image(resolution=90).save(img)
        records.append(
            {
                "n": i,
                "chunk_id": c["chunk_id"],
                "doc_name": doc,
                "doc_type": c["doc_type"],
                "page": c["page"],
                "page_end": c["page_end"],
                "is_table": c["is_table"],
                "label": {
                    "head": c["context"].split(" › ")[0],
                    "section": c["section"],
                    "subsection": c["subsection"],
                    "heading": c["heading"],
                    "table_title": c.get("table_title"),
                },
                "chunk_start": c["text"][:300],
                "evidence": {
                    "markers_before": last_markers(texts, c["page"], c["doc_type"]),
                    "page_text_start": texts[c["page"] - 1][:1500],
                },
                "image": img.relative_to(HERE).as_posix(),
                "verdict": {
                    "head": None,
                    "section": None,
                    "subsection": None,
                    "heading": None,
                    "table_title": None,
                    "note": "",
                },
            }
        )
    out = HERE / f"{name}.json"
    out.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(records)} chunks), images in {img_dir}")


if __name__ == "__main__":
    main()
