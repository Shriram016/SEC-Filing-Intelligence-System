"""Claim + quote check (engine.md §3.5, Q107, ADR-0003). Code only, no LLM.

A claim passes when its quote is in the cited extract (whitespace, case, curly quotes and
dashes forgiven) and its value is in the quote as printed. Failed claims are removed later by
the final rule; the reason is kept for the logs and the scorecard.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from filing_rag.engine.answer import Claim
from filing_rag.numbers import has_number, number_patterns
from filing_rag.search.searcher import Hit

MIN_QUOTE_WORDS = 3
_TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", " ": " ",
})  # fmt: skip
_SPACE_RE = re.compile(r"\s+")


class Failure(StrEnum):
    BAD_EXTRACT = "bad_extract"
    QUOTE_TOO_SHORT = "quote_too_short"
    QUOTE_NOT_FOUND = "quote_not_found"
    VALUE_NOT_IN_QUOTE = "value_not_in_quote"
    CALC_ERROR = "calc_error"


@dataclass(frozen=True)
class ClaimCheck:
    claim: Claim
    failure: Failure | None
    hit: Hit | None  # the cited chunk (None when the extract number is wrong)

    @property
    def ok(self) -> bool:
        return self.failure is None


def norm(text: str) -> str:
    """Text for comparison: NFKC, plain quote marks and dashes, one space, lower case."""
    t = unicodedata.normalize("NFKC", text).translate(_TRANSLATE)
    return _SPACE_RE.sub(" ", t).strip().lower()


def quote_in_text(quote: str, text: str) -> bool:
    q = norm(quote)
    return bool(q) and q in norm(text)


def quote_long_enough(quote: str) -> bool:
    words = quote.split()
    return len(words) >= MIN_QUOTE_WORDS and any(sum(c.isalpha() for c in w) >= 2 for w in words)


def check_claim(claim: Claim, hits: list[Hit]) -> ClaimCheck:
    if not 1 <= claim.extract <= len(hits):
        return ClaimCheck(claim, Failure.BAD_EXTRACT, None)
    hit = hits[claim.extract - 1]
    if not quote_long_enough(claim.quote):
        return ClaimCheck(claim, Failure.QUOTE_TOO_SHORT, hit)
    if not quote_in_text(claim.quote, str(hit.payload.get("text", ""))):
        return ClaimCheck(claim, Failure.QUOTE_NOT_FOUND, hit)
    if claim.value is not None and not has_number(claim.quote, number_patterns(claim.value)):
        return ClaimCheck(claim, Failure.VALUE_NOT_IN_QUOTE, hit)
    return ClaimCheck(claim, None, hit)


def check_claims(claims: list[Claim], hits: list[Hit]) -> list[ClaimCheck]:
    return [check_claim(c, hits) for c in claims]
