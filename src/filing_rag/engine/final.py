"""Final rule (engine.md §3.6, Q107): checked claims + calculations → answer / partial / refuse.

No number reaches the user unless it passed the quote check or came from the calculator:
- the model's sentence is used only when its placeholders all passed and it has no digits of
  its own (years and dates allowed); otherwise code writes a plain sentence;
- the period line comes from the chunk metadata, not from the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from filing_rag.baseline.pipeline import BaselineAnswer, Source
from filing_rag.engine.answer import WriterOutput
from filing_rag.engine.calculator import CalcError, Quantity, calculate, fmt_number
from filing_rag.engine.checks import Failure, check_claims
from filing_rag.numbers import unit_family, unit_scale
from filing_rag.search.searcher import Hit

PLACEHOLDER_RE = re.compile(r"\{([A-Za-z]+\d+)\}")
_ALLOWED_NUMBERS = [
    re.compile(r"\b(19[89]\d|20[0-4]\d)\b"),  # years
    re.compile(r"\bFY\s?'?\d{2}(\d{2})?\b", re.IGNORECASE),  # "FY2022", "FY 22"
    re.compile(r"\bQ[1-4]\b", re.IGNORECASE),  # quarters
    re.compile(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b",
        re.IGNORECASE,
    ),  # "July 1"
    re.compile(r"\b(10-K|10-Q|8-K)\b", re.IGNORECASE),
]
_SCALE_WORDS = {1e3: "thousand", 1e6: "million", 1e9: "billion", 1e12: "trillion"}


class Status(StrEnum):
    ANSWER = "answer"
    PARTIAL = "partial"
    REFUSED = "refused"


@dataclass
class Item:
    """A claim or a calculation after the checks."""

    id: str
    kind: str  # claim | calc
    label: str
    value: float | None
    unit: str | None
    failure: Failure | None
    detail: str | None = None  # calc error or formula
    hit: Hit | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None


@dataclass
class CheckedAnswer:
    status: Status
    text: str
    main_value: float | None
    main_unit: str | None
    items: list[Item] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    period: str = ""
    model_sentence: str = ""  # the writer's sentence with placeholders (for the logs)
    sentence_used: bool = False  # False: code wrote its own sentence (unsafe or failed)

    @property
    def claims_total(self) -> int:
        return sum(1 for i in self.items if i.kind == "claim")

    @property
    def claims_passed(self) -> int:
        return sum(1 for i in self.items if i.kind == "claim" and i.ok)

    @property
    def failures(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for i in self.items:
            if i.failure:
                out[str(i.failure)] = out.get(str(i.failure), 0) + 1
        return out

    def to_baseline(self) -> BaselineAnswer:
        """The old answer fields, so the scorer and the runner work unchanged."""
        return BaselineAnswer(
            found=self.status != Status.REFUSED,
            answer=self.text,
            value=self.main_value,
            unit=self.main_unit,
            sources=self.sources,
        )


def fmt_value(value: float, unit: str | None) -> str:
    """88945, "USD million" -> "$88,945 million"; 42.94, "%" -> "42.9%"."""
    family = unit_family(unit)
    if family == "pct":
        return f"{value:.1f}%"
    if unit is None:
        return f"{value:.2f}"
    sign = "-" if value < 0 else ""
    num = fmt_number(round(abs(value), 2))
    scale = _SCALE_WORDS.get(unit_scale(unit))
    if family == "usd":
        return f"{sign}${num}" + (f" {scale}" if scale else "")
    return f"{sign}{num} {unit}"


def _items(out: WriterOutput, hits: list[Hit]) -> dict[str, Item]:
    items: dict[str, Item] = {}
    for chk in check_claims(out.claims, hits):
        c = chk.claim
        items[c.id] = Item(c.id, "claim", c.label, c.value, c.unit, chk.failure, None, chk.hit)
    for k in out.calculations:
        inputs = [items.get(i) for i in k.inputs]
        if any(i is None or not i.ok or i.value is None for i in inputs):
            items[k.id] = Item(k.id, "calc", k.label, None, k.unit, Failure.CALC_ERROR,
                               "an input is missing or failed the check")  # fmt: skip
            continue
        try:
            res = calculate(
                k.op, [Quantity(i.value, i.unit) for i in inputs if i and i.value is not None]
            )
        except CalcError as exc:
            items[k.id] = Item(k.id, "calc", k.label, None, k.unit, Failure.CALC_ERROR, str(exc))
            continue
        items[k.id] = Item(k.id, "calc", k.label, res.value, res.unit, None, res.formula)
    return items


def _sentence_safe(sentence: str) -> bool:
    rest = PLACEHOLDER_RE.sub(" ", sentence)
    for pat in _ALLOWED_NUMBERS:
        rest = pat.sub(" ", rest)
    return not re.search(r"\d", rest)


def _fill(sentence: str, items: dict[str, Item]) -> str:
    def one(m: re.Match[str]) -> str:
        it = items[m.group(1)]
        assert it.value is not None
        return fmt_value(it.value, it.unit)

    return PLACEHOLDER_RE.sub(one, sentence)


def _line(it: Item) -> str:
    shown = fmt_value(it.value, it.unit) if it.value is not None else "(statement)"
    return f"{it.label}: {shown}"


def _period(used: list[Item]) -> str:
    seen: list[str] = []
    for it in used:
        if it.hit is None:
            continue
        p = it.hit.payload
        end = p.get("period_end")
        when = (
            f"period ended {date.fromisoformat(end):%d %b %Y}"
            if end
            else f"FY{p.get('fiscal_year')}"
        )
        text = f"{p.get('company', it.hit.doc_name)} {p.get('doc_type', '')} ({when})".replace(
            "  ", " "
        )
        if text not in seen:
            seen.append(text)
    return "; ".join(seen)


def _claims_behind(it: Item, items: dict[str, Item], out: WriterOutput) -> list[Item]:
    """The claims a calculation is built on (for sources and the period line)."""
    if it.kind == "claim":
        return [it]
    calc = next(k for k in out.calculations if k.id == it.id)
    found: list[Item] = []
    for i in calc.inputs:
        if i in items:
            found += _claims_behind(items[i], items, out)
    return found


def decide(out: WriterOutput, hits: list[Hit]) -> CheckedAnswer:
    items = _items(out, hits)
    passed = [i for i in items.values() if i.ok]
    if not out.found or not any(i.kind == "claim" for i in passed):
        reason = "I could not find this in the filings searched."
        if out.found and items:
            reason = "I could not find a fact I could check against the filings searched."
        return CheckedAnswer(Status.REFUSED, reason, None, None, list(items.values()),
                             model_sentence=out.answer)  # fmt: skip

    used_ids = PLACEHOLDER_RE.findall(out.answer)
    main = items.get(out.main) if out.main else None
    main_ok = main is None or main.ok
    used_ok = all(i in items and items[i].ok for i in used_ids)
    failed = [i for i in items.values() if not i.ok]

    claims_used: list[Item] = []
    for it in ([main] if main is not None and main.ok else []) + [
        items[i] for i in used_ids if i in items
    ]:
        claims_used += [c for c in _claims_behind(it, items, out) if c.ok and c not in claims_used]
    if not claims_used:
        claims_used = [i for i in passed if i.kind == "claim"]

    sentence_used = False
    if main_ok and used_ok and not (main is None and failed):
        status = Status.ANSWER
        if _sentence_safe(out.answer) and out.answer.strip():
            text = _fill(out.answer.strip(), items)
            sentence_used = True
        else:
            text = (
                _line(main) + "."
                if main is not None
                else "; ".join(_line(c) for c in claims_used) + "."
            )
    else:
        status = Status.PARTIAL
        checked = "; ".join(_line(i) for i in passed)
        missing = ", ".join(i.label for i in failed)
        text = f"Checked facts: {checked}. Could not check: {missing}."
    calcs = [
        i for i in passed if i.kind == "calc" and (i.id in used_ids or (main and i.id == main.id))
    ]
    if calcs:
        text += (
            " Computed: "
            + "; ".join(
                f"{c.label} = {c.detail} = {fmt_value(c.value, c.unit)}"
                for c in calcs
                if c.value is not None
            )
            + "."
        )
    period = _period(claims_used)
    if period:
        text += f" Source: {period}."
    sources: list[Source] = []
    for c in claims_used:
        if c.hit is not None:
            s = Source(doc_name=c.hit.doc_name, page=c.hit.page)
            if s not in sources:
                sources.append(s)
    main_value = main.value if main is not None and main.ok else None
    main_unit = main.unit if main_value is not None and main is not None else None
    return CheckedAnswer(status, text, main_value, main_unit, list(items.values()), sources, period,
                         model_sentence=out.answer, sentence_used=sentence_used)  # fmt: skip
