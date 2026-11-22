"""Print the section changes (page, section) of documents, to find wrong section starts.

Run: uv run python experiments/m2/section_seq.py DOC [DOC ...] [--max N]
"""

from __future__ import annotations

import json
import sys

from filing_rag.config import get_settings


def main() -> None:
    args = sys.argv[1:]
    limit = 40
    if "--max" in args:
        i = args.index("--max")
        limit = int(args[i + 1])
        args = args[:i] + args[i + 2 :]
    d = get_settings().ingest_dir / "chunks"
    for doc in args:
        prev: object = object()
        seq = []
        for line in (d / f"{doc}.jsonl").read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            if c["section"] != prev:
                seq.append(f"p{c['page']}:{(c['section'] or '-')[:38]}")
                prev = c["section"]
        print(f"== {doc} ({len(seq)} changes)")
        print("  " + " | ".join(seq[:limit]))


if __name__ == "__main__":
    main()
