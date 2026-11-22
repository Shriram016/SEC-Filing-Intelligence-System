"""Summarise data/v3/report.json + catalog.json after a full ingestion run.

Run: uv run python experiments/m2/analyse_report.py
"""

from __future__ import annotations

import json
from collections import Counter

from filing_rag.config import get_settings
from filing_rag.ingest.pipeline import MIN_ITEMS


def main() -> None:
    s = get_settings()
    rep = json.loads((s.ingest_dir / "report.json").read_text(encoding="utf-8"))
    cat = json.loads((s.ingest_dir / "catalog.json").read_text(encoding="utf-8"))
    print("documents", rep["documents"], "ok", rep["ok"], "chunks", rep["chunks"],
          "tables", rep["table_chunks"])  # fmt: skip
    print("tokens", rep["tokens"])
    print("checks", rep["checks"])
    print("label checks", {k: v["count"] for k, v in rep["label_checks"].items()})
    print("\nSKIPPED:")
    for k, v in rep["skipped"].items():
        print(" ", k, "|", v)

    ok = [r for r in cat if r["status"] == "ok"]
    print("\nby type:", Counter(r["doc_type"] for r in ok))
    print("period source:", Counter(r["period_source"] for r in ok))
    few = [r for r in ok if r["sections_found"] < MIN_ITEMS.get(r["doc_type"], 0)]
    print(f"\nFEW SECTIONS ({len(few)}):", Counter(r["doc_type"] for r in few))
    for r in sorted(few, key=lambda r: r["doc_name"]):
        print(f"  {r['doc_name']}: {r['sections_found']} Items, {r['pages']} p")
    warn = Counter()
    for r in ok:
        for w in r["warnings"]:
            warn[w.split(":")[0][:70]] += 1
    print("\nWARNINGS:", warn.most_common(15))
    flags = Counter()
    for r in ok:
        for k, v in r["label_flags"].items():
            flags[(k, r["doc_name"])] += v
    print("\nLABEL FLAGS per doc (top 20):")
    for (k, d), v in flags.most_common(20):
        print(f"  {k} {d}: {v}")
    no_chunks = [r["doc_name"] for r in ok if r["chunks"] < 5]
    print("\nfew chunks (<5):", no_chunks)


if __name__ == "__main__":
    main()
