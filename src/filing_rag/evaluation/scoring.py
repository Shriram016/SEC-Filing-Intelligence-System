"""Answer scoring by code (Q10, Q11, Q103).

- Number check: the answer's value and unit vs the gold_value / gold_unit. Units are converted
  to a base (USD, %, count); a relative difference up to 1% is allowed (rounding). A decrease
  given as a positive number counts when the answer says it is a decrease.
- Questions without a gold_value (text answers, choices) are marked by hand.
- Search check: were all evidence pages in the chunks the model saw?
- Source check: did the model cite the evidence pages?
- Failure tag for a wrong answer: broken_json / search_miss / answer_error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from filing_rag.baseline.pipeline import BaselineAnswer
from filing_rag.evaluation.dev_set import DevQuestion
from filing_rag.search.searcher import Hit

REL_TOLERANCE = 0.01
SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
SCALE_RE = re.compile(r"\b(thousands?|millions?|billions?|trillions?|k|mn|m|bn|b)\b")
SCALE_ALIASES = {"k": "thousand", "mn": "million", "m": "million", "bn": "billion", "b": "billion"}
DECREASE_RE = re.compile(
    r"\b(decrease[sd]?|declined?|down|lower|fell|drop(ped)?|reduction)\b", re.I
)


class Mark(StrEnum):
    CORRECT = "correct"
    WRONG = "wrong"
    HAND = "hand"  # marked by the user


class FailureTag(StrEnum):
    BROKEN_JSON = "broken_json"
    SEARCH_MISS = "search_miss"
    ANSWER_ERROR = "answer_error"


def normalise(value: float, unit: str | None) -> tuple[str, float]:
    """Return (family, value in the base unit). Families: pct, usd, count."""
    u = (unit or "").lower().strip()
    if "%" in u or "percent" in u:
        return "pct", value
    if "basis point" in u or "bps" in u:
        return "pct", value / 100
    m = SCALE_RE.search(u)
    scale = 1.0
    if m:
        word = m.group(1).rstrip("s")
        scale = SCALES[SCALE_ALIASES.get(word, word)]
    family = "usd" if ("usd" in u or "$" in u or "dollar" in u) else "count"
    return family, value * scale


def numbers_match(gold: tuple[str, float], got: tuple[str, float]) -> bool:
    gf, gv = gold
    af, av = got
    if (gf == "pct") != (af == "pct"):
        return False  # a percent never matches an amount; usd vs count is allowed
    if gv == 0:
        return abs(av) < 1e-9
    return abs(av - gv) / abs(gv) <= REL_TOLERANCE


def mark_number(q: DevQuestion, a: BaselineAnswer | None) -> Mark:
    if q.gold_value is None:
        return Mark.HAND
    if a is None or not a.found or a.value is None:
        return Mark.WRONG
    gold = normalise(q.gold_value, q.gold_unit)
    got = normalise(a.value, a.unit)
    if numbers_match(gold, got):
        return Mark.CORRECT
    # a decrease given as a positive number, with the words saying "decrease"
    flipped = (got[0], -got[1])
    if gold[1] < 0 < got[1] and DECREASE_RE.search(a.answer) and numbers_match(gold, flipped):
        return Mark.CORRECT
    return Mark.WRONG


def evidence_seen(q: DevQuestion, hits: list[Hit]) -> bool:
    """True when every evidence page is inside a chunk the model saw."""
    return all(any(h.covers(e.doc_name, e.page) for h in hits) for e in q.evidence)


def sources_ok(q: DevQuestion, a: BaselineAnswer | None, hits: list[Hit]) -> bool:
    """True when the model cited every evidence page: the page itself, or the start page of
    a shown chunk that spans the evidence page."""
    if a is None:
        return False

    def cited(doc: str, page: int) -> bool:
        for s in a.sources:
            if s.doc_name != doc:
                continue
            if s.page == page:
                return True
            if any(h.doc_name == doc and h.page == s.page and h.covers(doc, page) for h in hits):
                return True
        return False

    return all(cited(e.doc_name, e.page) for e in q.evidence)


def failure_tag(mark: Mark, error: str | None, seen: bool) -> FailureTag | None:
    """Tag a wrong answer (Q11). Hand-marked answers get a tag after the user marks them."""
    if error is not None:
        return FailureTag.BROKEN_JSON
    if mark != Mark.WRONG:
        return None
    return FailureTag.ANSWER_ERROR if seen else FailureTag.SEARCH_MISS


@dataclass
class Score:
    mark: Mark
    tag: FailureTag | None
    evidence_seen: bool
    sources_ok: bool


def score(q: DevQuestion, a: BaselineAnswer | None, error: str | None, hits: list[Hit]) -> Score:
    seen = evidence_seen(q, hits)
    mark = Mark.WRONG if error is not None and q.gold_value is not None else mark_number(q, a)
    return Score(mark, failure_tag(mark, error, seen), seen, sources_ok(q, a, hits))
