"""Q112: copy the 50 FB-dev questions (full rows) to data/fb_dev/fb_dev_50.jsonl, once.

Only the rows whose ID is in eval/locked_split.json `dev_ids` are written. Prints counts only.

Run: uv run python experiments/m3/locked_split/write_fb_dev.py
"""

from __future__ import annotations

import sys

from filing_rag.config import get_settings
from filing_rag.evaluation.locked import load_fb_dev, write_fb_dev


def main() -> int:
    s = get_settings()
    out = write_fb_dev(s, allow=True, reason="Q112: copy the 50 FB-dev questions once")
    print(f"wrote {len(load_fb_dev(s))} FB-dev questions to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
