"""Builders for synthetic pages and lines (no PDF needed)."""

from __future__ import annotations

from filing_rag.ingest.layout import Line, Page, Word

CHAR_W = 5.0


def line(
    *segments: tuple[float, str],
    top: float = 100.0,
    page: int = 1,
    size: float = 10.0,
    bold: bool = False,
) -> Line:
    """A line from (x, text) segments. Words inside a segment are one space apart."""
    words: list[Word] = []
    for x, text in segments:
        cur = x
        for tok in text.split():
            w = len(tok) * CHAR_W
            words.append(Word(tok, cur, cur + w, top, top + size, size, bold))
            cur += w + CHAR_W * 0.6
    return Line(words=words, page=page)


def text_line(text: str, top: float, page: int = 1, **kw: object) -> Line:
    return line((50.0, text), top=top, page=page, **kw)  # type: ignore[arg-type]


def page_of(lines: list[Line], number: int = 1, width: float = 612.0) -> Page:
    for ln in lines:
        ln.page = number
    return Page(number=number, width=width, height=792.0, lines=lines, char_width=CHAR_W)


def word_count(text: str) -> int:
    """Fake token counter: one token per word, plus 2 special tokens."""
    return len(text.split()) + 2
