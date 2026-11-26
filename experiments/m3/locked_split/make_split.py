"""Q112: split the 150 locked questions into 50 FB-dev + 100 closed, from the labels only.

- Reads the locked file through `read_labels` (checksum check + open-register line). Only the
  ID, the label fields and the number of evidence pages leave that function: never the
  question, answer, justification or evidence text.
- Prints label counts only (all 150, dev 50, closed 100).
- Writes eval/locked_split.json once. Refuses when it exists (the split is never redone).

Run (needs the user's approval; touches the locked file):
    uv run python experiments/m3/locked_split/make_split.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from filing_rag.config import get_settings
from filing_rag.evaluation.locked import (
    DEV_SIZE,
    ID_FIELD,
    LABEL_FIELDS,
    SPLIT_NAME,
    SPLIT_SEED,
    label_counts,
    read_labels,
    stratified_split,
)


def table(name: str, parts: dict[str, dict[str, dict[str, int]]]) -> list[str]:
    values = list(parts["all"][name])
    lines = [f"### {name}", "", "| Value | All 150 | Dev 50 | Closed 100 |", "|---|---|---|---|"]
    for v in values:
        cells = [str(parts[p][name].get(v, 0)) for p in ("all", "dev", "closed")]
        lines.append(f"| {v} | " + " | ".join(cells) + " |")
    return lines + [""]


def main() -> int:
    s = get_settings()
    out = s.eval_dir / SPLIT_NAME
    if out.exists():
        print(f"{out} exists; the split is never redone")
        return 1
    rows = read_labels(s, allow=True, reason="Q112 stratified split 50/100 from labels only")
    missing = [f for f in LABEL_FIELDS if all(r[f] is None for r in rows)]
    dev, closed = stratified_split(rows, DEV_SIZE, SPLIT_SEED)
    by_id = {r[ID_FIELD]: r for r in rows}
    parts = {"all": label_counts(rows),
             "dev": label_counts([by_id[i] for i in dev]),
             "closed": label_counts([by_id[i] for i in closed])}  # fmt: skip
    payload = {
        "decision": "Q112",
        "made_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": SPLIT_SEED,
        "rule": "proportional per question_type (largest remainder); systematic pick inside a "
        "type over questions sorted by question_reasoning, doc_type, evidence_pages>1, "
        "gics_sector, doc_period",
        "label_fields_missing": missing,
        "dev_ids": dev,
        "closed_ids": closed,
        "label_counts": parts,
    }
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    md = [f"# Q112 split ({payload['made_at']}, seed {SPLIT_SEED})", "",
          f"Dev {len(dev)}, closed {len(closed)}. Label fields with no value: {missing or 'none'}.",
          ""]  # fmt: skip
    for f in (*LABEL_FIELDS, "evidence_pages"):
        if f != "company":
            md += table(f, parts)
    md += [f"Companies: all {len(parts['all']['company'])}, dev {len(parts['dev']['company'])}, "
           f"closed {len(parts['closed']['company'])}."]  # fmt: skip
    (s.eval_dir / "locked_split.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
