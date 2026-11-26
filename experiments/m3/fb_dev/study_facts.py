"""Q112 step 2, part B (code): where each FB-dev answer is and how our data stores the page.

For each question and evidence page: document type, fiscal year/quarter (catalog), whether
the document is in the collection, and the chunks that cover the page (table / text, split
table, section). Also mechanical tags from the question text: formula given, unit or rounding
instruction, statement named.

Outputs:
- data/fb_dev/study_input.md: question, answer, justification + facts (has FinanceBench
  text: stays out of git) — what I read for parts A and C.
- experiments/m3/fb_dev/study_facts.json: IDs + facts only (no question text).

Run: uv run python experiments/m3/fb_dev/study_facts.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from filing_rag.config import get_settings
from filing_rag.evaluation.fb_dev import fb_id
from filing_rag.evaluation.locked import load_fb_dev

HERE = Path(__file__).parent
STATEMENTS = {
    "income": r"income statement|statement of income|p&l|profit and loss|statement of operations",
    "balance": r"balance sheet|statement of financial position",
    "cash_flow": r"cash flow",
}


def chunks_by_page(path: Path) -> dict[int, list[dict[str, Any]]]:
    pages: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        for p in range(int(c["page"]), int(c.get("page_end") or c["page"]) + 1):
            pages[p].append(c)
    return pages


def main() -> None:
    s = get_settings()
    catalog = {d["doc_name"]: d for d in json.loads((s.ingest_dir / "catalog.json").read_text())}
    cache: dict[str, dict[int, list[dict[str, Any]]]] = {}
    facts, md = [], ["# FB-dev study input (FinanceBench text: do not commit)", ""]
    for row in sorted(load_fb_dev(s), key=lambda r: fb_id(r["financebench_id"])):
        q = str(row["question"])
        ql = q.lower()
        pages = []
        for ev in row["evidence"]:
            doc, page = ev["doc_name"], int(ev["evidence_page_num"]) + 1
            cat = catalog.get(doc)
            info: dict[str, Any] = {"doc": doc, "page": page, "in_collection": bool(
                cat and cat["status"] == "ok")}  # fmt: skip
            if cat:
                info |= {"doc_type": cat["doc_type"], "fiscal_year": cat["fiscal_year"],
                         "quarter": cat.get("fiscal_quarter")}  # fmt: skip
            path = s.ingest_dir / "chunks" / f"{doc}.jsonl"
            if info["in_collection"] and path.exists():
                cache.setdefault(doc, chunks_by_page(path))
                cs = cache[doc].get(page, [])
                info |= {
                    "chunks": len(cs),
                    "table_chunks": sum(bool(c["is_table"]) for c in cs),
                    "split_table": any(int(c.get("table_parts") or 1) > 1 for c in cs),
                    "untitled_table": any(c["is_table"] and not c.get("table_title") for c in cs),
                    "sections": sorted({str(c.get("section")) for c in cs}),
                }
            if info not in pages:
                pages.append(info)
        f = {
            "id": fb_id(row["financebench_id"]),
            "type": row["question_type"],
            "reasoning": row.get("question_reasoning"),
            "pages": pages,
            "n_pages": len(pages),
            "n_docs": len({p["doc"] for p in pages}),
            "formula_given": bool(
                re.search(
                    r"defined as|define .* as|calculated as|using "
                    r"the formula|formula",
                    ql,
                )
            ),  # fmt: skip
            "unit_instruction": bool(
                re.search(
                    r"usd (millions|billions|thousands)|in millions|"
                    r"in billions|percentage|%",
                    ql,
                )
            ),  # fmt: skip
            "rounding": bool(re.search(r"round|decimal", ql)),
            "statements_named": [k for k, pat in STATEMENTS.items() if re.search(pat, ql)],
            "average": "average" in ql,
        }
        facts.append(f)
        md += [f"## {f['id']} ({f['type']}, {f['reasoning']})", "", f"**Q:** {q}", "",
               f"**A:** {row['answer']}", "", f"**Justification:** {row.get('justification')}",
               "", "**Facts:** " + json.dumps({k: v for k, v in f.items() if k not in (
                   "id", "type", "reasoning")}), ""]  # fmt: skip
    (HERE / "study_facts.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
    (s.data_dir / "fb_dev" / "study_input.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{len(facts)} questions")
    missing = [f["id"] for f in facts if not all(p["in_collection"] for p in f["pages"])]
    no_chunk = [f["id"] for f in facts if any(p.get("chunks") == 0 for p in f["pages"])]
    print("not in collection:", missing)
    print("page has no chunk:", no_chunk)
    print("multi-doc:", [f["id"] for f in facts if f["n_docs"] > 1])


if __name__ == "__main__":
    main()
