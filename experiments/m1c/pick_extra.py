"""M1c: extra random text pages for a slot when the first picks have no usable number.

Rule (written before looking at the new pages): a text page qualifies if its text chunks
contain a money amount ("$1.2 billion", "$850,000") or a percent ("82%"). Pages already in
pages.json are excluded. Fixed seed, spread over documents.

Run: uv run python experiments/m1c/pick_extra.py <slot> <n> <seed>  → appends to pages.json
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

from filing_rag.config import get_settings

HERE = Path(__file__).parent
NUMBER_RE = re.compile(r"\$\s?\d[\d,.]*(?:\s?(?:million|billion))?|\d+(?:\.\d+)?\s?%")
MIN_TEXT_TOKENS = 250


def main() -> None:
    slot, n, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    data = json.loads((HERE / "pages.json").read_text(encoding="utf-8"))
    taken = {(p["doc_name"], p["page"]) for p in data["pages"]}
    pool: dict[str, list[int]] = defaultdict(list)
    for f in sorted((get_settings().ingest_dir / "chunks").glob("*.jsonl")):
        if f.stem not in {p["doc_name"] for p in data["pages"]}:
            continue  # stay inside the M1b documents
        pages: dict[int, dict[str, object]] = defaultdict(
            lambda: {"t": 0, "table": False, "num": False}
        )
        for line in f.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            st = pages[c["page"]]
            if c["is_table"]:
                st["table"] = True
            else:
                st["t"] = int(st["t"]) + c["n_tokens"]  # type: ignore[call-overload]
                st["num"] = bool(st["num"]) or bool(NUMBER_RE.search(c["text"]))
        for page, st in sorted(pages.items()):
            ok = not st["table"] and int(st["t"]) >= MIN_TEXT_TOKENS and st["num"]  # type: ignore[call-overload]
            if ok and (f.stem, page) not in taken:
                pool[f.stem].append(page)
    rng = random.Random(seed)
    docs = sorted(pool)
    rng.shuffle(docs)
    left = {d: rng.sample(pool[d], len(pool[d])) for d in docs}
    out = []
    while len(out) < n and any(left.values()):
        for d in docs:
            if left[d] and len(out) < n:
                out.append({"slot": slot, "spare": True, "extra_seed": seed, "doc_name": d,
                            "page": left[d].pop()})  # fmt: skip
    data["pages"].extend(out)
    (HERE / "pages.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    for p in out:
        print(p["doc_name"], p["page"])


if __name__ == "__main__":
    main()
