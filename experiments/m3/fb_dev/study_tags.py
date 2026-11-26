"""Q112 step 2, parts A + C: my tags for the FB-dev 50 (IDs and tags only, no FinanceBench
text), merged with the code facts (study_facts.json) and counted into STUDY.md.

Tags:
- answer: number | numbers (2+ values) | yes_no (yes/no + reason) | choice (pick one item from a
  table or list) | text (short explanation or list) | absent (answer = none / 0 / "not relevant")
- calc: none | one_op | multi_op | average (needs an average of 2+ values) | rank (compare rows)
- constant: the formula needs a fixed number (365, 2, 3, 1 - x) that is not in the filing
- terms: the question uses analyst words that differ from the filing line item
- quarter: the right document depends on a quarter or a date inside the year
- judgement: needs knowledge or a threshold that the filing does not state
- risk: my guess of the main weak point (search_2pages | calc | absent | quarter | terms |
  judgement | ok)

Run: uv run python experiments/m3/fb_dev/study_tags.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent

# id: (answer, calc, constant, terms, quarter, judgement, risk)
TAGS: dict[str, tuple[str, str, bool, bool, bool, bool, str]] = {
    "fb_00206": ("absent", "none", False, False, False, True, "absent"),
    "fb_00215": ("yes_no", "one_op", False, True, False, True, "search_2pages"),
    "fb_00299": ("choice", "rank", False, False, True, False, "quarter"),
    "fb_00394": ("choice", "rank", False, False, True, False, "quarter"),
    "fb_00464": ("yes_no", "none", False, False, False, False, "ok"),
    "fb_00517": ("yes_no", "multi_op", False, False, False, False, "calc"),
    "fb_00521": ("absent", "none", False, False, False, False, "absent"),
    "fb_00552": ("yes_no", "multi_op", False, True, False, False, "calc"),
    "fb_00585": ("numbers", "multi_op", False, False, False, False, "calc"),
    "fb_00603": ("text", "none", False, False, True, False, "quarter"),
    "fb_00651": ("yes_no", "none", False, False, True, False, "quarter"),
    "fb_00684": ("yes_no", "multi_op", False, False, False, False, "calc"),
    "fb_00685": ("yes_no", "multi_op", False, False, False, True, "calc"),
    "fb_00711": ("number", "average", True, True, False, False, "calc"),
    "fb_00720": ("absent", "none", False, False, False, True, "absent"),
    "fb_00724": ("choice", "rank", False, False, True, False, "quarter"),
    "fb_00799": ("yes_no", "multi_op", False, True, False, False, "calc"),
    "fb_00839": ("yes_no", "none", False, False, False, True, "judgement"),
    "fb_00941": ("text", "none", False, False, True, False, "quarter"),
    "fb_01077": ("text", "none", False, False, False, False, "ok"),
    "fb_01107": ("text", "none", False, False, False, False, "search_2pages"),
    "fb_01198": ("text", "none", False, False, False, False, "ok"),
    "fb_01275": ("choice", "rank", False, False, False, False, "ok"),
    "fb_01319": ("absent", "none", False, True, False, False, "absent"),
    "fb_01351": ("numbers", "none", False, False, False, False, "ok"),
    "fb_01476": ("number", "none", False, False, True, False, "quarter"),
    "fb_01487": ("yes_no", "none", False, False, True, False, "quarter"),
    "fb_01491": ("number", "none", False, False, True, False, "ok"),
    "fb_01902": ("choice", "rank", False, False, True, False, "quarter"),
    "fb_01930": ("text", "none", False, True, True, False, "terms"),
    "fb_01964": ("choice", "rank", False, False, False, False, "ok"),
    "fb_02024": ("numbers", "none", False, False, False, False, "search_2pages"),
    "fb_02119": ("number", "one_op", False, True, True, True, "judgement"),
    "fb_02608": ("number", "average", True, False, False, False, "calc"),
    "fb_03029": ("number", "none", False, True, False, False, "terms"),
    "fb_03471": ("number", "one_op", False, False, False, False, "ok"),
    "fb_03473": ("number", "average", True, False, False, False, "calc"),
    "fb_03856": ("number", "one_op", False, False, False, False, "search_2pages"),
    "fb_03882": ("number", "none", False, True, False, False, "terms"),
    "fb_04209": ("number", "none", False, False, False, False, "ok"),
    "fb_04254": ("number", "one_op", False, True, False, False, "search_2pages"),
    "fb_04302": ("number", "average", True, True, False, False, "calc"),
    "fb_04481": ("number", "multi_op", False, True, False, False, "search_2pages"),
    "fb_04700": ("number", "none", False, True, False, False, "terms"),
    "fb_04854": ("number", "one_op", False, True, False, False, "ok"),
    "fb_06247": ("number", "average", True, True, False, False, "calc"),
    "fb_06741": ("number", "average", True, True, False, False, "calc"),
    "fb_07661": ("number", "none", False, False, False, False, "ok"),
    "fb_09724": ("number", "one_op", False, True, False, False, "ok"),
    "fb_10136": ("number", "multi_op", True, True, False, False, "calc"),
}
NAMES = ("answer", "calc", "constant", "terms", "quarter", "judgement", "risk")


def main() -> None:
    facts = {f["id"]: f for f in json.loads((HERE / "study_facts.json").read_text())}
    assert set(facts) == set(TAGS), set(facts) ^ set(TAGS)
    rows = [{"id": i, "type": facts[i]["type"].split("-")[0], "pages": facts[i]["n_pages"],
             **dict(zip(NAMES, TAGS[i], strict=True))} for i in sorted(TAGS)]  # fmt: skip
    for r in rows:
        r["two_pages"] = r["pages"] > 1
        r["split_table"] = any(p.get("split_table") for p in facts[r["id"]]["pages"])
        r["untitled_table"] = any(p.get("untitled_table") for p in facts[r["id"]]["pages"])
    md = ["# FB-dev study (Q112 step 2)", "",
          "IDs and tags only (FinanceBench text stays in `data/fb_dev/`). Tags: "
          "`study_tags.py`; code facts: `study_facts.py`.", ""]  # fmt: skip
    for key in ("type", "answer", "calc", "risk"):
        c = Counter(str(r[key]) for r in rows)
        md += [f"**{key}:** " + ", ".join(f"{k} {n}" for k, n in c.most_common()), ""]
    for key in ("two_pages", "constant", "terms", "quarter", "judgement", "split_table",
                "untitled_table"):  # fmt: skip
        ids = [r["id"] for r in rows if r[key]]
        md += [f"**{key}:** {len(ids)} — " + ", ".join(ids), ""]
    md += ["| ID | Type | Pages | Answer | Calc | Constant | Terms | Quarter | Judgement | Risk |",
           "|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    yn = {True: "yes", False: ""}
    for r in rows:
        md.append(f"| {r['id']} | {r['type']} | {r['pages']} | {r['answer']} | {r['calc']} | "
                  f"{yn[r['constant']]} | {yn[r['terms']]} | {yn[r['quarter']]} | "
                  f"{yn[r['judgement']]} | {r['risk']} |")  # fmt: skip
    (HERE / "STUDY_TABLE.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:30]))


if __name__ == "__main__":
    main()
