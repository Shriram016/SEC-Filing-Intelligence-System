"""Find the period a document covers (Q96).

- `fiscal_year` comes from the document list (clean; the file name is not trusted).
- `period_end` (10-K, 10-Q, annual report) and `report_date` (8-K) come from cover-page patterns.
- Earnings releases have no fixed cover text: try patterns, else fall back to the list year and
  the quarter in the file name, with `period_source = "estimated"`.
- A mismatch between the list year and the cover date is a warning, not an error.

Search uses the year as a boost, not a hard filter (a 10-K holds 2-3 years of numbers).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sept", "sep"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for m in names
}
_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_RE = re.compile(rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})\s*,?\s*(\d{{4}})\b", re.IGNORECASE)

FISCAL_YEAR_END_RE = re.compile(r"(?:fiscal\s+year|year)\s+ended\s*:?\s*", re.IGNORECASE)
QUARTER_END_RE = re.compile(r"quarterly\s+period\s+ended\s*:?\s*", re.IGNORECASE)
REPORT_DATE_RE = re.compile(r"date\s+of\s+report", re.IGNORECASE)
NAME_DATE_RE = re.compile(r"dated[-_](\d{4})-(\d{2})-(\d{2})")
NAME_QUARTER_RE = re.compile(r"_(\d{4})Q([1-4])_")
QUARTER_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4}
EARNINGS_QUARTER_RE = re.compile(
    r"\b(first|second|third|fourth)[\s-]+quarter\b(?:\s+(?:of\s+)?(?:fiscal\s+)?(?:year\s+)?(\d{4}))?",
    re.IGNORECASE,
)
EARNINGS_Q_RE = re.compile(r"\b(?:Q([1-4])\s*(?:FY)?\s*'?(\d{2,4})|FY\s*(\d{2,4})\s*Q([1-4]))\b")
YEAR_BEFORE_QUARTER_RE = re.compile(
    r"\b(20\d{2})\s+(?:first|second|third|fourth)[\s-]+quarter\b", re.IGNORECASE
)
ENDED_RE = re.compile(r"\bended\s*:?\s*", re.IGNORECASE)
LOOKAHEAD_CHARS = 80
EARNINGS_WINDOW = 800


@dataclass
class Period:
    fiscal_year: int  # year stated in the document when found, else list year (Q97)
    list_fiscal_year: int = 0  # the document list year, kept for traceability
    fiscal_quarter: int | None = None
    period_end: date | None = None
    report_date: date | None = None
    source: str = "estimated"  # cover | name | estimated
    warnings: list[str] = field(default_factory=list)


def squash(text: str) -> str:
    """One space between words; layout text has runs of spaces and line breaks."""
    return re.sub(r"\s+", " ", text)


def parse_date(text: str) -> date | None:
    m = DATE_RE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
    except ValueError:
        return None


def date_after(pattern: re.Pattern[str], text: str) -> date | None:
    """First date that follows the pattern within a short window."""
    for m in pattern.finditer(text):
        d = parse_date(text[m.end() : m.end() + LOOKAHEAD_CHARS])
        if d:
            return d
    return None


def date_near(pattern: re.Pattern[str], text: str) -> date | None:
    """8-K covers print the date before or after "Date of Report"."""
    for m in pattern.finditer(text):
        after = parse_date(text[m.end() : m.end() + 120])
        if after:
            return after
        before = text[max(0, m.start() - 60) : m.start()]
        dates = list(DATE_RE.finditer(before))
        if dates:
            return parse_date(dates[-1].group(0))
    return None


def quarter_from_name(doc_name: str) -> int | None:
    m = NAME_QUARTER_RE.search(doc_name)
    return int(m.group(2)) if m else None


def date_from_name(doc_name: str) -> date | None:
    m = NAME_DATE_RE.search(doc_name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _check_year(p: Period, d: date, label: str) -> None:
    if d.year not in (p.fiscal_year, p.fiscal_year + 1):
        p.warnings.append(f"{label} {d.isoformat()} does not match fiscal year {p.fiscal_year}")


def find_period(doc_type: str, doc_name: str, list_year: int, cover_text: str) -> Period:
    """`cover_text` = text of the first pages (for an annual report: the whole document)."""
    text = squash(cover_text)
    p = Period(fiscal_year=list_year, list_fiscal_year=list_year)

    if doc_type in ("10-K", "annual report"):
        d = date_after(FISCAL_YEAR_END_RE, text)
        if d:
            p.period_end, p.source = d, "cover"
            if d.year != list_year:
                # Some companies name the fiscal year by its start (rare); always log it.
                p.warnings.append(
                    f"period end {d.isoformat()} is not in document list year {list_year}"
                )
        else:
            p.warnings.append("no 'fiscal year ended' date found on the cover")

    elif doc_type == "10-Q":
        p.fiscal_quarter = quarter_from_name(doc_name)
        d = date_after(QUARTER_END_RE, text)
        if d:
            p.period_end, p.source = d, "cover"
            _check_year(p, d, "quarter end")
        else:
            # FinanceBench lists some earnings releases as 10-Q (e.g. Lockheed 2023 Q2).
            p.warnings.append("no 'quarterly period ended' date on the cover; earnings rule used")
            _earnings_period(p, doc_name, text, list_year)

    elif doc_type == "8-K":
        d = date_near(REPORT_DATE_RE, text)
        name_d = date_from_name(doc_name)
        if d:
            p.report_date, p.source = d, "cover"
            if name_d and name_d != d:
                p.warnings.append(
                    f"cover date {d.isoformat()} differs from file name date {name_d.isoformat()}"
                )
        elif name_d:
            p.report_date, p.source = name_d, "name"
            p.warnings.append("report date taken from the file name")
        else:
            p.warnings.append("no report date found")
        if p.report_date:
            _check_year(p, p.report_date, "report date")

    elif doc_type == "earnings":
        _earnings_period(p, doc_name, text, list_year)
    else:
        p.warnings.append(f"no period rule for doc_type {doc_type}")
    return p


def _earnings_period(p: Period, doc_name: str, text: str, list_year: int) -> None:
    q_name = quarter_from_name(doc_name)
    q_text = _earnings_quarter(text)
    p.fiscal_quarter = q_text or q_name
    if q_text and q_name and q_text != q_name:
        p.warnings.append(f"quarter in text Q{q_text} differs from file name Q{q_name}")
    head = text[:3000]
    m = EARNINGS_QUARTER_RE.search(head)
    d = date_after(ENDED_RE, text[m.start() : m.start() + EARNINGS_WINDOW]) if m else None
    text_year = int(m.group(2)) if m and m.group(2) else None
    if text_year is None:
        mb = YEAR_BEFORE_QUARTER_RE.search(head)
        text_year = int(mb.group(1)) if mb else None
    if text_year and text_year != list_year:
        p.warnings.append(
            f"fiscal year in text ({text_year}) differs from document list ({list_year}); "
            "text year used"
        )
        p.fiscal_year = text_year
    if d:
        p.period_end, p.source = d, "cover"
        _check_year(p, d, "quarter end")
    else:
        p.source = "estimated"
        p.warnings.append("earnings period end not found; year from document list")
    name_d = date_from_name(doc_name)
    if name_d:
        p.report_date = name_d


def _earnings_quarter(text: str) -> int | None:
    head = text[:3000]
    m = EARNINGS_QUARTER_RE.search(head)
    if m:
        return QUARTER_WORDS[m.group(1).lower()]
    m2 = EARNINGS_Q_RE.search(head)
    if m2:
        return int(m2.group(1) or m2.group(4))
    return None
