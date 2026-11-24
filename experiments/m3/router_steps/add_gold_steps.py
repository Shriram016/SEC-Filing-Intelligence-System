"""Add `gold_steps` (Q109) to eval/dev_set.jsonl. Free: no LLM call.

The gold plan is one step per company + year pair that the question names or implies
(router prompt rules). Written by Claude from the question text, status draft (the user checks
them with the 50 dev questions). The script:

1. makes a backup of the dev set (once);
2. checks every company against the catalog;
3. checks that the step documents (catalog rule A) cover the gold evidence documents, and lists
   the questions where they do not (known limits, not gold errors);
4. writes the field, keeping every other field and the line format.

Run: uv run python experiments/m3/router_steps/add_gold_steps.py [--write]
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from filing_rag.config import Settings
from filing_rag.evaluation.dev_set import DevQuestion
from filing_rag.router.catalog import DocCatalog

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT / "eval" / "dev_set.jsonl"
BACKUP = Path(__file__).with_name("dev_set_before_gold_steps.jsonl")

S = list[tuple[str | None, int | None]]
GOLD: dict[str, S] = {
    "dev_0001": [("3M", 2019)],
    "dev_0002": [("JPMorgan", 2021)],
    "dev_0003": [("MGM Resorts", 2017)],
    "dev_0004": [("Apple", 2019)],
    "dev_0005": [("Apple", 2023)],
    "dev_0006": [("Walmart", 2023)],
    "dev_0007": [("FedEx", 2023)],
    "dev_0008": [("Amcor", 2022)],
    "dev_0009": [("Johnson & Johnson", 2023)],
    "dev_0010": [("Costco", 2019)],
    "dev_0011": [("Intel", 2019)],  # "by 2022" is a forecast year, not a step
    "dev_0012": [("3M", 2019)],
    "dev_0013": [("Costco", None)],  # no year named
    "dev_0014": [("PG&E Corporation", 2023)],
    "dev_0015": [("Ulta Beauty", 2023)],
    "dev_0016": [("Lockheed Martin", 2023)],
    "dev_0017": [("JPMorgan", 2021)],
    "dev_0018": [("Apple", 2019)],
    "dev_0019": [("Intel", 2023)],
    "dev_0020": [("Apple", 2023)],
    "dev_0021": [("FedEx", 2023)],
    "dev_0022": [("McDonalds", 2023)],
    "dev_0023": [("JPMorgan", 2021)],
    "dev_0024": [("Walmart", None)],  # no year named
    "dev_0025": [("MGM Resorts", 2016), ("MGM Resorts", 2015)],
    "dev_0026": [("Intel", 2019)],
    "dev_0027": [("eBay", 2023)],
    "dev_0028": [("Apple", 2019)],
    "dev_0029": [("3M", 2019)],
    "dev_0030": [("Costco", None)],  # no year named
    "dev_0031": [("Ulta Beauty", 2023), ("Ulta Beauty", 2022)],  # "year-ago quarter"
    "dev_0032": [("McDonalds", 2023)],
    "dev_0033": [("Adobe", 2018)],
    "dev_0034": [("Intel", 2019)],
    "dev_0035": [("Lockheed Martin", 2023), ("Lockheed Martin", 2022)],
    "dev_0036": [("MGM Resorts", 2015), ("MGM Resorts", 2017)],
    "dev_0037": [("Apple", 2019), ("Apple", 2018)],
    "dev_0038": [("Apple", 2023)],
    "dev_0039": [("Walmart", 2023)],
    "dev_0040": [("FedEx", 2023), ("FedEx", 2022)],
    "dev_0041": [("CVS Health", 2016), ("CVS Health", 2017)],
    "dev_0042": [("Oracle", 2020)],  # "five fiscal years ended May 31, 2020" = end year
    "dev_0043": [("Ulta Beauty", 2023), ("Ulta Beauty", 2022)],
    "dev_0044": [("McDonalds", 2023), ("McDonalds", 2022)],
    "dev_0045": [("Adobe", 2018), ("Adobe", 2017)],
    "dev_0046": [("Intel", 2018), ("Intel", 2019)],
    "dev_0047": [("Costco", 2019), ("Verizon", 2018)],
    "dev_0048": [("Intel", 2019), ("Costco", 2019)],
    "dev_0049": [("3M", 2019), ("Costco", 2019)],
    "dev_0050": [("CVS Health", 2017), ("MGM Resorts", 2017)],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write the field (else: check only)")
    args = ap.parse_args()

    catalog = DocCatalog.from_settings(Settings())
    companies = set(catalog.companies())
    lines = DEV.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    problems: list[str] = []
    for line in lines:
        row = json.loads(line)
        q = DevQuestion.model_validate(row)
        gold = GOLD.get(q.id)
        if gold is None:
            out.append(line)
            continue
        for c, _ in gold:
            if c is not None and c not in companies:
                raise SystemExit(f"{q.id}: company {c!r} is not in the catalog")
        docs: set[str] = set()
        for c, y in gold:
            sel = catalog.select([c] if c else [], [y] if y is not None else [])
            if sel.missing:
                problems.append(f"{q.id}: step {c} {y} has no document (not_covered)")
            docs.update(sel.doc_names or [])
        for ev in q.evidence:
            if ev.doc_name not in docs:
                problems.append(f"{q.id}: gold document {ev.doc_name} not in the step "
                                f"documents {sorted(docs)}")  # fmt: skip
        row["gold_steps"] = [{"company": c, "year": y} for c, y in gold]
        DevQuestion.model_validate(row)
        out.append(json.dumps(row, ensure_ascii=False))

    print(f"questions with gold_steps: {len(GOLD)}; two or more steps: "
          f"{sum(1 for g in GOLD.values() if len(g) > 1)}")  # fmt: skip
    print("\n".join(problems) or "no coverage problems")
    if args.write:
        if not BACKUP.exists():
            shutil.copyfile(DEV, BACKUP)
        eol = "\r\n" if b"\r\n" in DEV.read_bytes() else "\n"  # keep the line ends
        DEV.write_bytes((eol.join(out) + eol).encode("utf-8"))
        print(f"written {DEV} (backup {BACKUP.name})")


if __name__ == "__main__":
    main()
