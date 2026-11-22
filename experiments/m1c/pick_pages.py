"""M1c: pick random pages for dev-set drafting (no hand choice of easy pages).

1. Read the M1b chunks (data/v3/chunks/*.jsonl): 22 documents, none used by a locked question.
2. Two pools of pages:
   - table pages: at least one table chunk with 3+ rows of numbers;
   - text pages: no table chunk, and at least 250 tokens of text.
3. Assign slots with a fixed seed, spread over the documents (round robin over shuffled
   documents), with 50% spare pages: a page that cannot give a fair question (signature page,
   legal boilerplate, blank) is skipped and the reason is logged in the drafts.
4. Company pairs for compare_companies: random pairs of 10-K documents of different companies.

Run: uv run python experiments/m1c/pick_pages.py  →  experiments/m1c/pages.json
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from filing_rag.config import get_settings

HERE = Path(__file__).parent
SEED = 20261121
SPARE = 1.5
TABLE_SLOTS = {"find_number_table": 10, "calculate": 10, "compare_years": 6}
TEXT_SLOTS = {"find_number_text": 10, "explain_why": 10}
COMPANY_PAIRS = 4
MIN_TEXT_TOKENS = 250
NUMBER_ROW_RE = re.compile(r"\d[\d,]*(\.\d+)?\s+.*\d[\d,]*(\.\d+)?")


def page_pools(
    chunk_dir: Path,
) -> tuple[dict[str, list[int]], dict[str, list[int]], dict[str, str]]:
    tables: dict[str, list[int]] = defaultdict(list)
    texts: dict[str, list[int]] = defaultdict(list)
    doc_types: dict[str, str] = {}
    for f in sorted(chunk_dir.glob("*.jsonl")):
        stats: dict[int, dict[str, int]] = defaultdict(lambda: {"tables": 0, "text": 0})
        for line in f.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            doc_types[f.stem] = c["doc_type"]
            st = stats[c["page"]]
            if c["is_table"]:
                rows = [r for r in c["text"].splitlines() if NUMBER_ROW_RE.search(r)]
                st["tables"] += len(rows) >= 3
            else:
                st["text"] += c["n_tokens"]
        for page, st in sorted(stats.items()):
            if st["tables"]:
                tables[f.stem].append(page)
            elif st["text"] >= MIN_TEXT_TOKENS:
                texts[f.stem].append(page)
    return tables, texts, doc_types


def spread(pool: dict[str, list[int]], n: int, rng: random.Random) -> list[tuple[str, int]]:
    """n pages, round robin over shuffled documents, a random page each time, no repeats."""
    left = {d: rng.sample(p, len(p)) for d, p in pool.items() if p}
    docs = sorted(left)
    rng.shuffle(docs)
    out: list[tuple[str, int]] = []
    while len(out) < n and any(left.values()):
        for d in docs:
            if left[d] and len(out) < n:
                out.append((d, left[d].pop()))
    return out


def assign(slots: dict[str, int], pages: list[tuple[str, int]]) -> list[dict[str, Any]]:
    out = []
    it = iter(pages)
    for slot, n in slots.items():
        for i in range(int(n * SPARE)):
            doc, page = next(it)
            out.append({"slot": slot, "spare": i >= n, "doc_name": doc, "page": page})
    return out


def main() -> None:
    rng = random.Random(SEED)
    tables, texts, doc_types = page_pools(get_settings().ingest_dir / "chunks")
    n_table = sum(int(n * SPARE) for n in TABLE_SLOTS.values())
    n_text = sum(int(n * SPARE) for n in TEXT_SLOTS.values())
    picks = assign(TABLE_SLOTS, spread(tables, n_table, rng))
    picks += assign(TEXT_SLOTS, spread(texts, n_text, rng))

    tenk = sorted(d for d, t in doc_types.items() if t == "10-K")
    pairs: list[list[str]] = []
    while len(pairs) < int(COMPANY_PAIRS * SPARE):
        a, b = rng.sample(tenk, 2)
        if a.split("_")[0] != b.split("_")[0] and sorted([a, b]) not in pairs:
            pairs.append(sorted([a, b]))
    out = {
        "seed": SEED,
        "pool_sizes": {
            "table_pages": sum(map(len, tables.values())),
            "text_pages": sum(map(len, texts.values())),
        },
        "pages": picks,
        "company_pairs": [{"spare": i >= COMPANY_PAIRS, "docs": p} for i, p in enumerate(pairs)],
    }
    (HERE / "pages.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out["pool_sizes"]), len(picks), "pages,", len(pairs), "pairs")


if __name__ == "__main__":
    main()
