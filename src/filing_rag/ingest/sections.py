"""Find the section of each block (Q90): one general logic for every document.

1. Items (10-K, 10-Q, the 10-K inside an annual report) and 8-K item codes, found with
   flexible rules (no space after the dot, dashes, non-breaking spaces).
2. Exhibit headings (large 8-Ks, Exhibit 13 filings).
3. Fallback for every document: the headings on the page (`subsection`, `heading`).
Table-of-contents pages are found and skipped, so their Item lines do not start sections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ITEMS_10K = {
    "1", "1A", "1B", "1C", "2", "3", "4", "5", "6", "7", "7A", "8", "9", "9A", "9B", "9C",
    "10", "11", "12", "13", "14", "15", "16",
}  # fmt: skip
ITEM_RE = re.compile(r"^\s*item\s*(\d{1,2}[a-c]?)(?!\.?\d)\s*[.:\-—–]?\s*(.*)$", re.IGNORECASE)
ITEM_8K_RE = re.compile(r"^\s*item\s*(\d\.\d{2})\s*[.:\-—–]?\s*(.*)$", re.IGNORECASE)
PART_RE = re.compile(r"^\s*part\s+(iv|iii|ii|i)\b\s*[.:\-—–]?\s*(.*)$", re.IGNORECASE)
NOTE_RE = re.compile(r"^\s*(?:note\s+\d{1,2}\b|\d{1,2}\.\s+[A-Z])", re.IGNORECASE)
EXHIBIT_RE = re.compile(
    # MGM style: "Exhibit 10.5(40)" (a footnote number in brackets after the number)
    r"^\s*exhibit\s+(\d{1,3}(?:\.\d{1,3})?)(?:\(\d{1,3}\))?(?:\s*[-–—:.]?\s+[A-Z][^()]{0,80})?\s*$",
    re.IGNORECASE,
)
NOTE_LINE_RE = re.compile(r"^\s*note\s+\d{1,2}\b", re.IGNORECASE)
# fix 3 / fix 7: text that is never a heading
NOISE_RE = re.compile(
    r"telephone number|exact name of registrant|commission file|i\.?r\.?s\.? employer|"
    r"address of principal|cusip|\[•\]|for immediate release|more information|"
    r"^united states$|securities and exchange commission|washington, d\.?c\.?|"
    r"^form \d|^current report|^table of contents$|^page$|^\(?continued\)?$",
    re.IGNORECASE,
)
ENTITY_RE = re.compile(
    r"^[A-Z0-9&.,'’\- ]*\b(CORPORATION|COMPANY|INC|INCORPORATED|LLC|L\.L\.C|N\.A|"
    r"ASSOCIATION|BANK|LIMITED|LTD|PLC|L\.P|TRUST)\b[ ,.A-Z]*$"
)
MAX_ENTITY_WORDS = 8
ENDS_WITH_PAGE_RE = re.compile(r"(\d{1,3}|\d{1,3}\s*[-–]\s*\d{1,3}|not applicable)\s*$", re.I)
INDEX_LINE_RE = re.compile(r"^\s*(?:note\s+\d{1,2}|item\s*\d{1,2}[a-c]?)\b.*\s\d{1,3}\s*$", re.I)
TOC_MIN_ITEMS = 5
TOC_MIN_INDEX_LINES = 6
TOC_SHORT_WORDS = 14
TOC_SHORT_SHARE = 0.85
MAX_TITLE = 90


def clean(text: str, limit: int = MAX_TITLE) -> str:
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip(" .:-—–")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


SECOND_ITEM_RE = re.compile(r"\bitem\s*\d", re.IGNORECASE)
# Long official titles: 8-K Item 5.02 has 18 words; Costco Item 7 has 10 words + a
# bracket note "(amounts in millions, ...". Brackets are removed before the count.
MAX_ITEM_TITLE_WORDS = 24
BRACKET_RE = re.compile(r"\s*\([^)]*(?:\)|$)")


def _prose_start(rest: str) -> bool:
    """Prose, not a title: "Item 9A, management excluded ...", "Item 1. , \"Business\" of
    our ...", "Item 8. )". A title starts with a capital letter (or a bracket/quote + one)."""
    if not rest:
        return False
    if rest[0] in ",;:)" or not any(c.isalpha() for c in rest):
        return True
    first = next((c for c in rest if c.isalpha()), "")
    return first.islower()


def _sentence_like(rest: str) -> bool:
    """Prose that starts with an Item reference, e.g. "Item 1A. Risk Factors in this
    Form 10-Q and Part I, Item 1A ..." (a second Item, or too long for a title)."""
    return bool(SECOND_ITEM_RE.search(rest)) or len(rest.split()) > MAX_ITEM_TITLE_WORDS


def match_item(text: str) -> tuple[str, str] | None:
    """Return (item number, title) for a 10-K/10-Q Item heading line, else None."""
    m = ITEM_RE.match(text.replace("\xa0", " "))
    if not m:
        return None
    num, rest = m.group(1).upper(), BRACKET_RE.sub("", m.group(2)).strip()
    if num not in ITEMS_10K:
        return None
    if _prose_start(rest):  # prose: "Item 7 of this report ..."
        return None
    if _sentence_like(rest):
        return None
    return num, clean(rest)


def match_item_8k(text: str) -> tuple[str, str] | None:
    m = ITEM_8K_RE.match(text.replace("\xa0", " "))
    if not m:
        return None
    rest = BRACKET_RE.sub("", m.group(2)).strip()
    if _prose_start(rest) or _sentence_like(rest):
        return None
    return m.group(1), clean(rest)


def is_toc_page(lines: list[str]) -> bool:
    """A table of contents or a cross-reference index: many Item/Note lines ending in pages."""
    item_lines = [t for t in lines if match_item(t) or match_item_8k(t)]
    distinct = {(match_item(t) or match_item_8k(t) or ("", ""))[0] for t in item_lines}
    if len(distinct) >= TOC_MIN_ITEMS:
        with_page = sum(1 for t in item_lines if ENDS_WITH_PAGE_RE.search(t))
        if with_page >= 0.6 * len(item_lines):
            return True
        # a list with no page numbers (PG&E, Pfizer 10-Q): almost only short lines.
        # M2 probe: TOC pages 93-100% short lines, body pages with 5 Items at most 65%.
        short = sum(1 for t in lines if len(t.split()) <= TOC_SHORT_WORDS)
        if short >= TOC_SHORT_SHARE * len(lines):
            return True
    return sum(1 for t in lines if INDEX_LINE_RE.match(t)) >= TOC_MIN_INDEX_LINES


ITEM_ORDER = [
    "1", "1A", "1B", "1C", "2", "3", "4", "5", "6", "7", "7A", "8", "9", "9A", "9B", "9C",
    "10", "11", "12", "13", "14", "15", "16",
]  # fmt: skip
YEAR_TOKEN_RE = re.compile(r"^\(?(19[89]\d|20[0-4]\d)\)?[,.:]?$")
NUMBER_TOKEN_RE = re.compile(r"^[\(\$]*-?\d[\d,]*(?:\.\d+)?%?\)?[,.:]?$")
MAX_HEADING_WORDS = 15


def is_noise(text: str) -> bool:
    """Text that is never a heading: form fields, cover boilerplate, company names in
    signature blocks, spaced capital letters, and text that starts in lower case."""
    t = text.strip()
    words = t.split()
    if not words:
        return True
    if t[0].islower():
        return True
    if NOISE_RE.search(t):
        return True
    singles = sum(1 for w in words if len(w) == 1 and w.isalpha())
    if len(words) >= 4 and singles / len(words) > 0.4:
        return True  # S   P   A   F ... (spaced small capitals)
    return len(words) <= MAX_ENTITY_WORDS and bool(ENTITY_RE.match(t))


def heading_shape_ok(text: str) -> bool:
    """A label heading: short, has letters, not a sentence, not a row of numbers."""
    words = text.split()
    if not words or len(words) > MAX_HEADING_WORDS or sum(c.isalpha() for c in text) < 3:
        return False
    if is_noise(text):
        return False
    if text.rstrip().endswith(".") and len(words) > 8:
        return False
    numbers = [w for w in words if NUMBER_TOKEN_RE.match(w) and not YEAR_TOKEN_RE.match(w)]
    return len(numbers) <= 1


def row_like(text: str) -> bool:
    """Text that looks like a table row: 2+ numbers that are not years."""
    words = text.split()
    numbers = [w for w in words if NUMBER_TOKEN_RE.match(w) and not YEAR_TOKEN_RE.match(w)]
    return len(numbers) >= 2


def is_financial_section(doc_type: str, part: str | None, section: str | None) -> bool:
    """Where notes to the financial statements may appear."""
    if section is None:
        return True  # no Items found: page headings only
    if section.startswith("Exhibit"):
        return True  # Exhibit 13 (annual report), Exhibit 99 (press release)
    if doc_type == "10-Q":
        return "Item 1." in section and part in (None, "I") or section.endswith("Item 1")
    return "Item 8" in section or "Item 15" in section  # MGM puts F-pages after Item 15


PERIODIC_TYPES = ("10-K", "10-Q", "annual report")
# the last Items of a filing; an Exhibit heading after one of them starts the exhibits part
LAST_ITEMS = {"10-K": {"15", "16"}, "annual report": {"15", "16"}, "10-Q": {"6"}}


@dataclass
class SectionTracker:
    """Keeps the current section path while the blocks are read in order.

    Safety rule ("leave it out when unsure"): a heading that fails a check does not enter the
    label; the last good value is kept and the heading is recorded in `rejected`.
    - an Item that goes backwards (e.g. Item 3 after Item 8) is a cross-reference, not a start;
    - a Note heading outside the financial statements is a reference, not a note;
    - a heading with a bad shape (sentence, numbers, too long) is ignored.
    """

    doc_type: str
    part: str | None = None
    section: str | None = None
    subsection: str | None = None
    heading: str | None = None
    items_found: set[str] = field(default_factory=set)
    in_exhibits: bool = False  # exhibits after the last Item: their own Item lists are text
    rejected: list[str] = field(default_factory=list)
    _last_item: int | None = None

    def update(self, text: str, level: int, page: int = 0) -> None:
        """Call for each heading block. `level` 1 = major heading, 2 = minor heading."""
        t = text.replace("\xa0", " ").strip()
        periodic = self.doc_type in PERIODIC_TYPES
        if periodic and (page == 1 or self.in_exhibits) and match_item(t):
            where = "cover page" if page == 1 else "an exhibit"
            self.rejected.append(f"item on {where}: {clean(t)}")
            return
        if self.doc_type in ("8-K", "earnings"):
            m8 = match_item_8k(t)
            if m8:
                self._set_section(f"Item {m8[0]}" + (f" {m8[1]}" if m8[1] else ""), m8[0])
                return
        else:
            mp = PART_RE.match(t)
            if mp and len(t) <= 80:
                new_part = mp.group(1).upper()
                if new_part != self.part:
                    self.part, self._last_item = new_part, None  # Part II restarts at Item 1
                rest_item = match_item(mp.group(2)) if mp.group(2) else None
                if not rest_item:
                    return
                t = mp.group(2)
            mi = match_item(t)
            if mi:
                idx = ITEM_ORDER.index(mi[0])
                if self._last_item is not None and idx < self._last_item:
                    self.rejected.append(f"item goes backwards: {clean(t)}")
                    return
                self._last_item = idx
                prefix = f"Part {self.part}, " if self.doc_type == "10-Q" and self.part else ""
                title = f"Item {mi[0]}" + (f". {mi[1]}" if mi[1] else "")
                self._set_section(prefix + title, mi[0])
                return
        mx = EXHIBIT_RE.match(t)
        if mx:
            self._set_section(f"Exhibit {mx.group(1)}", None)
            self._last_item = None
            if self.items_found & LAST_ITEMS.get(self.doc_type, set()):
                self.in_exhibits = True
            return
        if not heading_shape_ok(t):
            self.rejected.append(f"bad heading shape: {clean(t)}")
            return
        if NOTE_RE.match(t):
            if not is_financial_section(self.doc_type, self.part, self.section):
                self.rejected.append(f"note outside financial statements: {clean(t)}")
                return
            self.subsection, self.heading = clean(t), None
        elif level == 1:
            self.subsection, self.heading = clean(t), None
        else:
            self.heading = clean(t)

    def _set_section(self, name: str, item: str | None) -> None:
        self.section, self.subsection, self.heading = clean(name), None, None
        if item:
            self.items_found.add(item)
