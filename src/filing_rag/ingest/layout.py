"""Read PDF pages into lines with position and font data (pdfplumber, Q85).

Per page:
1. words with font name and size → lines (words with the same vertical position);
2. two-column pages: read the left column, then the right column (M1a finding);
3. `$` printed as `S` in some fonts is fixed (M1a finding, ULTA).
Per document: lines that repeat at the top or bottom of many pages (page headers, footers,
page numbers) are removed.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BOLD_RE = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)
DOLLAR_AS_S_RE = re.compile(r"^S(\(?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|\d+\.\d+)$")
NUMBER_WORD_RE = re.compile(r"^\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?$")
PAGE_NUMBER_RE = re.compile(r"^(?:page\s*)?[-–]?\s*#\s*[-–]?(?:\s*of\s*#)?$")
LINE_TOLERANCE = 0.35  # share of font size: words this close vertically are on one line
GUTTER_HALF_WIDTH = 3.0
MIN_LINES_FOR_COLUMNS = 12
EDGE_LINES = 3  # top/bottom lines checked for repeating headers and footers


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    bold: bool


@dataclass
class Line:
    words: list[Word]
    page: int

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def size(self) -> float:
        return statistics.median(w.size for w in self.words)

    @property
    def bold(self) -> bool:
        chars = sum(len(w.text) for w in self.words)
        bold = sum(len(w.text) for w in self.words if w.bold)
        return chars > 0 and bold / chars >= 0.8

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    def spans(self) -> list[tuple[float, float, str]]:
        """Groups of words split at big gaps (table columns). Returns (x0, x1, text)."""
        gap = max(self.size * 0.9, 4.0)
        out: list[tuple[float, float, list[str]]] = []
        prev_x1: float | None = None
        for w in self.words:
            if prev_x1 is None or w.x0 - prev_x1 > gap:
                out.append((w.x0, w.x1, [w.text]))
            else:
                x0, _, ts = out[-1]
                ts.append(w.text)
                out[-1] = (x0, w.x1, ts)
            prev_x1 = w.x1
        return [(x0, x1, " ".join(ts)) for x0, x1, ts in out]

    def segments(self) -> list[tuple[float, str]]:
        """Groups of words split at big gaps (table columns). Returns (x0, text) pairs."""
        return [(x0, text) for x0, _, text in self.spans()]

    def aligned(self, char_width: float) -> str:
        """Layout text: each column starts near its position on the page."""
        s = ""
        for x, text in self.segments():
            col = int(round(x / char_width))
            pad = col - len(s)
            s += (" " * max(pad, 2 if s else 0)) + text
        return s


@dataclass
class Page:
    number: int  # 1-based PDF page index (never the printed number)
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    char_width: float = 4.0
    two_column: bool = False

    @property
    def landscape(self) -> bool:
        return self.width > self.height


def fix_word(text: str, next_text: str | None) -> str:
    m = DOLLAR_AS_S_RE.match(text)
    if m:
        return "$" + m.group(1)
    if text == "S" and next_text is not None and NUMBER_WORD_RE.match(next_text):
        return "$"
    return text


def words_from_pdfplumber(raw: Iterable[dict[str, Any]]) -> list[Word]:
    out = []
    for w in raw:
        out.append(
            Word(
                text=str(w["text"]),
                x0=float(w["x0"]),
                x1=float(w["x1"]),
                top=float(w["top"]),
                bottom=float(w["bottom"]),
                size=float(w.get("size") or 0.0),
                bold=bool(BOLD_RE.search(str(w.get("fontname") or ""))),
            )
        )
    return out


def group_lines(words: list[Word], page: int) -> list[Line]:
    """Words whose tops are close form one line; each line is sorted left to right."""
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.top, w.x0)):
        if lines:
            cur = lines[-1]
            ref = min(x.top for x in cur)
            if abs(w.top - ref) <= max(2.0, LINE_TOLERANCE * max(w.size, 1.0)):
                cur.append(w)
                continue
        lines.append([w])
    out = []
    for ws in lines:
        ws.sort(key=lambda w: w.x0)
        fixed = [
            Word(fix_word(w.text, ws[i + 1].text if i + 1 < len(ws) else None), w.x0, w.x1,
                 w.top, w.bottom, w.size, w.bold)
            for i, w in enumerate(ws)
        ]  # fmt: skip
        out.append(Line(words=fixed, page=page))
    return out


def char_width_of(words: list[Word]) -> float:
    widths = [(w.x1 - w.x0) / len(w.text) for w in words if len(w.text) >= 2]
    return statistics.median(widths) if widths else 4.0


def _alpha_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    return sum(c.isalpha() for c in chars) / len(chars) if chars else 0.0


def _crosses(line: Line, x: float) -> bool:
    return any(w.x0 < x + GUTTER_HALF_WIDTH and w.x1 > x - GUTTER_HALF_WIDTH for w in line.words)


def _split(line: Line, x: float) -> tuple[Line | None, Line | None]:
    left = [w for w in line.words if w.x1 <= x]
    right = [w for w in line.words if w.x0 >= x]
    return (Line(left, line.page) if left else None, Line(right, line.page) if right else None)


def find_gutter(lines: list[Line], width: float) -> float | None:
    """Return the x of a column gutter if the page has two text columns, else None.

    A gutter: few lines cross it, many lines have words on both sides, and both sides are
    text (letters), not numbers. Tables have numbers on the right, so they are not split.
    """
    n = len(lines)
    if n < MIN_LINES_FOR_COLUMNS:
        return None
    valid: list[tuple[int, float]] = []
    for xi in range(int(width * 0.3), int(width * 0.7), 2):
        x = float(xi)
        crossing = sum(1 for ln in lines if _crosses(ln, x))
        if crossing / n > 0.2:
            continue
        both = [
            ln for ln in lines
            if any(w.x1 <= x for w in ln.words) and any(w.x0 >= x for w in ln.words)
        ]  # fmt: skip
        if len(both) < max(8, int(0.4 * n)):
            continue
        texty = 0
        for ln in both:
            left, right = _split(ln, x)
            if (
                left
                and right
                and _alpha_ratio(left.text) >= 0.6
                and _alpha_ratio(right.text) >= 0.6
                and len(right.words) >= 3
                and len(left.words) >= 3
            ):
                texty += 1
        if texty < 0.7 * len(both):
            continue
        valid.append((len(both), x))
    if not valid:
        return None
    top = max(n for n, _ in valid)
    xs = [x for n, x in valid if n == top]
    return xs[len(xs) // 2]  # middle of the free band


def order_columns(lines: list[Line], gutter: float) -> list[Line]:
    """Full-width lines stay in place; between them, the left column comes before the right."""
    out: list[Line] = []
    left_buf: list[Line] = []
    right_buf: list[Line] = []

    def flush() -> None:
        out.extend(left_buf)
        out.extend(right_buf)
        left_buf.clear()
        right_buf.clear()

    for ln in lines:
        if _crosses(ln, gutter):
            flush()
            out.append(ln)
            continue
        left, right = _split(ln, gutter)
        if left:
            left_buf.append(left)
        if right:
            right_buf.append(right)
    flush()
    return out


def build_page(number: int, width: float, height: float, words: list[Word]) -> Page:
    lines = group_lines(words, number)
    page = Page(number=number, width=width, height=height, char_width=char_width_of(words))
    gutter = find_gutter(lines, width)
    if gutter is not None:
        lines = order_columns(lines, gutter)
        page.two_column = True
    page.lines = lines
    return page


def _edge_key(line: Line) -> str:
    return re.sub(r"\d+", "#", line.text.lower()).strip()


def strip_repeating(pages: list[Page]) -> int:
    """Remove page headers, footers and page numbers. Returns the number of lines removed."""
    n = len(pages)
    counts: Counter[str] = Counter()
    for p in pages:
        edge = p.lines[:EDGE_LINES] + p.lines[-EDGE_LINES:]
        counts.update({_edge_key(ln) for ln in edge})
    threshold = max(3, int(0.25 * n))
    removed = 0
    for p in pages:
        keep = []
        last = len(p.lines) - 1
        for i, ln in enumerate(p.lines):
            at_edge = i < EDGE_LINES or i > last - EDGE_LINES
            key = _edge_key(ln)
            if at_edge and ((n >= 4 and counts[key] >= threshold) or PAGE_NUMBER_RE.match(key)):
                removed += 1
                continue
            keep.append(ln)
        p.lines = keep
    return removed


def read_pdf(path: Path) -> list[Page]:
    import pdfplumber

    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            raw = page.extract_words(extra_attrs=["fontname", "size"])
            pages.append(
                build_page(i, float(page.width), float(page.height), words_from_pdfplumber(raw))
            )
            page.flush_cache()  # keep memory flat on long documents
    strip_repeating(pages)
    return pages
