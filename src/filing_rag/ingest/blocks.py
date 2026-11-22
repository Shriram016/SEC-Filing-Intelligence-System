"""Turn page lines into blocks: headings, text paragraphs and tables.

Tables (Q88, Q94) are kept as layout text: a run of lines with columns of numbers, plus the
column-header lines above it, the unit line ("in millions") and the title. A table that
continues on the next page is joined to the part on the previous page.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from filing_rag.ingest.layout import Line, Page
from filing_rag.ingest.sections import (
    EXHIBIT_RE,
    NOTE_LINE_RE,
    NOTE_RE,
    PART_RE,
    is_noise,
    match_item,
    match_item_8k,
    row_like,
)

NUM_TOKEN_RE = re.compile(r"^[\(\$€£]*[-–]?\d[\d,]*(?:\.\d+)?%?\)?[*,]?$")
FILLER_TOKENS = {"$", "%", "—", "–", "-", "(", ")", "*", "—%", "N/A", "n/a", "NM", "nm"}
YEAR_RE = re.compile(r"^\(?(19[89]\d|20[0-4]\d)\)?[,:]?$")
UNIT_RE = re.compile(
    r"\(?\b(?:(?:dollars|amounts|\$)\s+)?in\s+(?:millions|thousands|billions)\b[^)\n]*\)?"
    r"|\((?:millions|thousands|billions)[^)]*\)",
    re.IGNORECASE,
)
HEADER_HINT_RE = re.compile(
    r"\b(ended|as of|year|quarter|months|weeks|january|february|march|april|may|june|july|"
    r"august|september|october|november|december|fiscal|total|change|%)\b",
    re.IGNORECASE,
)
BULLET_RE = re.compile(r"^[•●▪■◦\-–]\s")
MAX_HEADING_WORDS = 14
MAX_LABEL_WORDS = 10
MAX_HEADER_LINES = 6
COLUMN_ZONE = 0.4  # header cells start right of this share of the text width
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
MAX_TITLE_WORDS = 30
UNIT_LINE_MAX_CHARS = 60
MAX_YEAR_HEADER_WORDS = 15
MAX_LEAD_LABELS = 2
MAX_LEAD_LABEL_WORDS = 6
CONTINUED_RE = re.compile(r"\(?continued\)?", re.IGNORECASE)
STATEMENT_RE = re.compile(
    r"\b(consolidated|condensed)\b.*\b(statements?|balance sheets?)\b", re.IGNORECASE
)
# fix 4: run-in headings at the start of a paragraph
RUN_IN_NUMBERED_RE = re.compile(r"^(\(?\d{1,2}\)?\.?\s+[A-Z][^.]{2,70}?)\.\s+\S")
MAX_RUN_IN_WORDS = 10
# CVS style note heading: "1 Significant Accounting Policies" (bold, no dot, no 'Note')
NUMBERED_TITLE_RE = re.compile(r"^\d{1,2}\.?\s+[A-Z][A-Za-z]")
MAX_UNIT_LINE_WORDS = 6
# a complete statement title: the next heading line is not part of it
STATEMENT_DONE_RE = re.compile(
    r"\b(income|operations|earnings|cash flows|equity|balance sheets?|comprehensive income|"
    r"financial position|loss)\b\s*(\([^)]*\))?\s*$",
    re.IGNORECASE,
)
CENTER_TOLERANCE = 0.08
MAX_SHORT_LABEL_WORDS = 3
# Q106: a long row name with no numbers does not end a table when the rows go on below it
MAX_GAP_LINES = 2
MAX_GAP_WORDS = 30
ALIGN_TOLERANCE = 0.6  # share of the font size: right edges of the same column
MIN_ALIGNED_COLUMNS = 2
ALIGNED_SHARE = 0.6
MAX_SECTION_LABEL_WORDS = 4
NUMBER_SHARE = 0.3  # a "row": numbers are at least this share of the words
MAX_ZONE_BLOCKS = 6  # loose header-zone blocks above a table with no title
MAX_ZONE_WORDS = 15
NUMBER_TOKEN_RE = re.compile(r"^[\(\$]*-?\d[\d,]*(?:\.\d+)?%?\)?[,.:]?$")
YEAR_TOKEN_RE = re.compile(r"^\(?(19[89]\d|20[0-4]\d)\)?[,.:]?$")


@dataclass
class Block:
    kind: str  # heading | text | table
    page: int
    text: str  # heading/text: plain text; table: layout text of title, unit, header, rows
    page_end: int = 0
    level: int = 0  # heading: 1 major, 2 minor
    title: str | None = None
    unit: str | None = None
    header: list[str] = field(default_factory=list)  # layout text lines
    rows: list[str] = field(default_factory=list)  # layout text lines

    def __post_init__(self) -> None:
        if not self.page_end:
            self.page_end = self.page


def is_num_token(tok: str) -> bool:
    return bool(NUM_TOKEN_RE.match(tok)) or tok in FILLER_TOKENS


def numeric_segment(seg: str) -> bool:
    toks = seg.split()
    return bool(toks) and all(is_num_token(t) for t in toks) and any(c.isdigit() for c in seg)


def is_year_header(line: Line) -> bool:
    toks = line.text.split()
    if len(toks) > MAX_YEAR_HEADER_WORDS:
        return False
    years = [t for t in toks if YEAR_RE.match(t)]
    return len(years) >= 2 and len(years) >= 0.5 * len(
        [t for t in toks if any(c.isdigit() for c in t)]
    )


def is_row(line: Line) -> bool:
    """A table row: 2+ column segments, at least one of them numeric, not only years."""
    segs = line.segments()
    if len(segs) < 2:
        return False
    if not any(numeric_segment(s) for _, s in segs):
        return False
    return not is_year_header(line)


def is_heading(line: Line, body_size: float, page_width: float = 0.0) -> int:
    """Return 0 (not a heading), 1 (major) or 2 (minor)."""
    t = line.text.strip()
    words = t.split()
    item = match_item(t) or match_item_8k(t)
    if words and item:
        if item[1] or line.bold or t.split()[0].isupper() or line.size >= body_size * 1.15:
            return 1  # Items first: long official titles (8-K 5.02), titles ending in ","
        return 0  # a bare "Item 8" in body style is the end of a wrapped sentence
    if not words or len(words) > MAX_HEADING_WORDS:
        return 0
    if sum(c.isalpha() for c in t) < 3 or t.endswith((",", ";")):
        return 0
    if BULLET_RE.match(t) or t[:1] in "•●▪■◦":
        return 0
    if _is_structure_heading(t):
        return 1
    if is_row(line) or is_year_header(line) or len(line.segments()) >= 3:
        return 0  # a table row or a column-header line
    if is_noise(t):
        return 0
    if UNIT_RE.search(t) and len(words) <= MAX_UNIT_LINE_WORDS:
        return 0  # "In millions" is a unit line, not a heading
    if t.endswith(".") and len(words) > 8:
        return 0
    numbers = sum(1 for w in words if NUM_TOKEN_RE.match(w) and not YEAR_RE.match(w))
    if numbers > 1:
        return 0
    letters = [c for c in t if c.isalpha()]
    caps = len(letters) >= 4 and all(c.isupper() for c in letters)
    big = body_size > 0 and line.size >= body_size * 1.15
    centered = page_width > 0 and abs((line.x0 + line.x1) / 2 - page_width / 2) < (
        CENTER_TOLERANCE * page_width
    )
    if STATEMENT_RE.search(t) and (caps or line.bold or big):
        return 1  # financial statement titles start a new part
    numbered = bool(NOTE_RE.match(t) or NUMBERED_TITLE_RE.match(t))
    if big or (caps and (line.bold or centered)) or (line.bold and numbered):
        return 1
    if line.bold or caps:
        return 2
    return 0


def body_font_size(pages: list[Page]) -> float:
    sizes = [round(ln.size, 1) for p in pages for ln in p.lines for _ in ln.words]
    return statistics.mode(sizes) if sizes else 0.0


def _is_label(line: Line) -> bool:
    t = line.text.strip()
    if _is_structure_heading(t) or NOTE_LINE_RE.match(t):
        return False  # fix 1: a Note heading is never inside a table
    return len(t.split()) <= MAX_LABEL_WORDS and not is_row(line)


def _is_structure_heading(t: str) -> bool:
    return bool(match_item(t) or match_item_8k(t) or PART_RE.match(t) or EXHIBIT_RE.match(t))


def _is_lead_label(line: Line) -> bool:
    """A row label above the first numeric row, e.g. "Current assets:"."""
    t = line.text.strip()
    if UNIT_RE.search(t):  # "... are as follows (in millions):" is a sentence, not a label
        return False
    return t.endswith(":") and len(t.split()) <= MAX_LEAD_LABEL_WORDS and not is_row(line)


def _is_section_label(line: Line) -> bool:
    """Q106: a short bold row label with no colon, e.g. "Operating activities" in a cash flow
    statement. Used only when a column header is directly above it."""
    t = line.text.strip()
    return (
        line.bold
        and 0 < len(t.split()) <= MAX_SECTION_LABEL_WORDS
        and not any(c.isdigit() for c in t)
        and not is_row(line)
        and not _is_structure_heading(t)
        and not NOTE_LINE_RE.match(t)
        and not UNIT_RE.search(t)
    )


def _is_header_line(line: Line, column_x: float) -> bool:
    t = line.text.strip()
    if _is_structure_heading(t) or NOTE_LINE_RE.match(t) or BULLET_RE.match(t):
        return False  # fix 1: "NOTE 6 : CONTRACT LIABILITIES" is a heading
    if is_year_header(line):
        return True
    words = t.split()
    if len(words) > 20 or (t.endswith((".", ":")) and len(words) > 6):
        return False  # a sentence, e.g. "... are as follows (in millions):"
    if line.x0 >= column_x and len(words) <= 6:
        return True  # a column-header cell over the numbers, e.g. "Pension and"
    return len(line.segments()) >= 2 or bool(HEADER_HINT_RE.search(t) or UNIT_RE.search(t))


def num_edges(line: Line) -> list[float]:
    """Right edges of the number columns of a line (numbers are right-aligned)."""
    return [x1 for _, x1, text in line.spans() if numeric_segment(text)]


def columns_line_up(above: list[Line], below: list[Line]) -> bool:
    """Most number columns of `below` sit under number columns of `above` (same table)."""
    top = [e for ln in above for e in num_edges(ln)]
    edges = sorted({round(e, 1) for ln in below for e in num_edges(ln)})
    if not top or not edges:
        return False
    tol = max(ALIGN_TOLERANCE * (below[0].size if below else 10.0), 4.0)
    hits = sum(1 for e in edges if any(abs(e - t) <= tol for t in top))
    return hits >= MIN_ALIGNED_COLUMNS and hits >= ALIGNED_SHARE * len(edges)


def _gap_label(line: Line) -> bool:
    """A long row name with no numbers, e.g. "Change in unrealized gains/losses on ...:"."""
    t = line.text.strip()
    return (
        bool(t)
        and not t.endswith(".")
        and len(t.split()) <= MAX_GAP_WORDS
        and not is_row(line)
        and not is_year_header(line)
        and not _is_structure_heading(t)
        and not NOTE_LINE_RE.match(t)
        and not BULLET_RE.match(t)
        and not UNIT_RE.search(t)
        and not any(c.isdigit() for c in t.replace("(1)", "").replace("(2)", ""))
    )


def _row_label_gap(lines: list[Line], rows: list[bool], j: int, run_rows: list[Line]) -> int:
    """Q106: the number of gap lines (1-2) at `j` that stay inside the table, else 0.

    The gap lines are long row names, the next line is a row, and its number columns line up
    with the rows above. Strict: when one test fails, the table ends here (as before).
    """
    if not run_rows:
        return 0
    for g in range(1, MAX_GAP_LINES + 1):
        k = j + g
        if k > len(lines) or not _gap_label(lines[k - 1]):
            return 0
        if k < len(lines) and rows[k]:
            below = [lines[m] for m in range(k, min(len(lines), k + 3)) if rows[m]]
            return g if columns_line_up(run_rows[-3:], below) else 0
    return 0


def find_tables(lines: list[Line]) -> list[tuple[int, int, int]]:
    """Return (header_start, first_row, end) index triples (end exclusive) for each table."""
    n = len(lines)
    rows = [is_row(ln) for ln in lines]
    column_x = 0.0
    if n:
        left = min(ln.x0 for ln in lines)
        column_x = left + COLUMN_ZONE * (max(ln.x1 for ln in lines) - left)
    out: list[tuple[int, int, int]] = []
    i = 0
    while i < n:
        if not rows[i]:
            i += 1
            continue
        j, last, count = i, i, 0
        while j < n:
            if rows[j]:
                last, count = j, count + 1
            elif is_year_header(lines[j]) or (
                _is_label(lines[j]) and any(rows[k] for k in range(j + 1, min(n, j + 4)))
            ):
                pass
            else:
                gap = _row_label_gap(lines, rows, j, [lines[k] for k in range(i, j) if rows[k]])
                if not gap:
                    break
                j += gap  # Q106: a long row name inside the table; the rows go on
                continue
            j += 1
        if count >= 2:
            start = i
            while (
                start > 0
                and i - start < MAX_LEAD_LABELS
                and (
                    _is_lead_label(lines[start - 1])
                    or (
                        start > 1
                        and _is_section_label(lines[start - 1])
                        and _is_header_line(lines[start - 2], column_x)
                    )
                )
                and not (out and start - 1 < out[-1][2])
            ):
                start -= 1
            i, h = start, start
            while h > 0 and i - h < MAX_HEADER_LINES and _is_header_line(lines[h - 1], column_x):
                if out and h - 1 < out[-1][2]:
                    break
                h -= 1
            out.append((h, i, last + 1))
            i = last + 1
        else:
            i += 1
    return out


def _join_text(lines: list[Line]) -> str:
    s = ""
    for ln in lines:
        t = ln.text.strip()
        if s.endswith("-") and t[:1].islower() and len(s) > 1 and s[-2].isalpha():
            s = s[:-1] + t
        else:
            s = f"{s} {t}" if s else t
    return s


def _paragraphs(lines: list[Line]) -> list[list[Line]]:
    """Split text lines into paragraphs at big vertical gaps and bullets."""
    if not lines:
        return []
    gaps = [b.top - a.top for a, b in zip(lines, lines[1:], strict=False) if b.top - a.top > 0]
    pitch = sorted(gaps)[len(gaps) // 4] if gaps else 12.0  # normal line spacing
    right = max(ln.x1 for ln in lines)
    paras: list[list[Line]] = [[lines[0]]]
    for prev, ln in zip(lines, lines[1:], strict=False):
        gap = ln.top - prev.top
        short_end = prev.text.rstrip().endswith((".", ":")) and prev.x1 < right - 0.2 * (
            right - prev.x0
        )
        if gap > pitch * 1.45 or gap < 0 or BULLET_RE.match(ln.text) or short_end:
            paras.append([ln])
        else:
            paras[-1].append(ln)
    return paras


def split_run_in(line: Line) -> tuple[str, Line | None] | None:
    """A heading at the start of a paragraph line: "12. Electronic Delivery. The Company"
    or a bold start "Derivatives. The Company ...". Returns (heading, rest of line)."""
    t = line.text.strip()
    words = line.words
    m = RUN_IN_NUMBERED_RE.match(t)
    head: str | None = None
    if m:
        cand = m.group(1).strip()
        body = cand.split(maxsplit=1)[1] if " " in cand else cand
        long_words = [w for w in body.split() if len(w) > 3]
        title_case = long_words and sum(w[0].isupper() for w in long_words) >= 0.6 * len(long_words)
        if title_case and len(cand.split()) <= MAX_RUN_IN_WORDS:
            head = cand
    elif words and words[0].bold and not line.bold:
        k = 0
        while k < len(words) and words[k].bold and k < MAX_RUN_IN_WORDS:
            k += 1
        bold_text = " ".join(w.text for w in words[:k])
        if bold_text.endswith(".") and k < len(words) and bold_text[0].isupper():
            head = bold_text
    if head is None:
        return None
    n = len(head.split())
    rest = Line(words[n:], line.page) if len(words) > n else None
    return head.rstrip("."), rest


def page_blocks(page: Page, body_size: float) -> list[Block]:
    lines = page.lines
    tables = find_tables(lines)
    blocks: list[Block] = []
    pending: list[Line] = []

    def flush_text() -> None:
        for para in _paragraphs(pending):
            text = _join_text(para)
            if text:
                blocks.append(Block("text", page.number, text))
        pending.clear()

    def table_block(h: int, r: int, end: int) -> Block:
        header = [ln.aligned(page.char_width) for ln in lines[h:r]]
        rows = [ln.aligned(page.char_width) for ln in lines[r:end]]
        unit = None
        for t in [ln.text for ln in lines[h:r]]:
            m = UNIT_RE.search(t)
            if m:
                unit = m.group(0).strip("() ")
                break
        return Block("table", page.number, "", unit=unit, header=header, rows=rows)

    i = 0
    t_iter = iter(tables)
    nxt = next(t_iter, None)
    while i < len(lines):
        if nxt and i == nxt[0]:
            flush_text()
            tb = table_block(*nxt)
            # Title and unit: up to 3 short lines just above the table (already-emitted
            # text blocks are taken back if they are short title/unit lines).
            for _ in range(3):
                if not blocks or blocks[-1].kind == "table":
                    break
                prev = blocks[-1]
                unit_m = UNIT_RE.search(prev.text) if prev.kind == "text" else None
                if unit_m:
                    tb.unit = tb.unit or unit_m.group(0).strip("() ")
                if prev.kind == "text" and prev.text.rstrip().endswith(":"):
                    # "... payments as of September 28, 2019, are as follows:" -> the
                    # last sentence of the paragraph is the title; the paragraph stays.
                    last = SENTENCE_END_RE.split(prev.text.strip())[-1]
                    if not mostly_numbers(last):  # Q106: "12 months or greater" is text
                        tb.title = tb.title or " ".join(last.split()[:MAX_TITLE_WORDS])
                    break
                if unit_m:
                    if len(prev.text) < UNIT_LINE_MAX_CHARS:  # a unit line on its own
                        blocks.pop()
                        continue
                    break
                words = prev.text.split()
                if (
                    tb.title is None
                    and len(words) <= 15
                    and not prev.text.endswith(".")
                    and not (prev.text.endswith(":") and len(words) > 8)
                    and title_shape_ok(prev.text)
                ):
                    tb.title = prev.text
                    # "OPERATING ACTIVITIES" under "CONSOLIDATED STATEMENTS OF CASH
                    # FLOWS": the statement heading is the title; the label is a row.
                    before = blocks[-2] if len(blocks) >= 2 else None
                    if (
                        prev.kind == "heading"
                        and len(words) <= MAX_SHORT_LABEL_WORDS
                        and before is not None
                        and before.kind == "heading"
                        and before.page == prev.page
                    ):
                        tb.title = before.text
                        tb.rows.insert(0, prev.text)
                    if prev.kind == "text":
                        blocks.pop()
                    break
                break
            if tb.title is None:
                title_from_header_zone(blocks, tb)
            blocks.append(tb)
            i = nxt[2]
            nxt = next(t_iter, None)
            continue
        ln = lines[i]
        run_in = split_run_in(ln) if not pending or _para_start(pending[-1], ln) else None
        if run_in is not None and not is_noise(run_in[0]):
            flush_text()
            blocks.append(Block("heading", page.number, run_in[0], level=2))
            if run_in[1] is not None:
                pending.append(run_in[1])
            i += 1
            continue
        level = is_heading(ln, body_size, page.width)
        if level:
            flush_text()
            last = blocks[-1] if blocks else None
            if (
                last
                and last.kind == "heading"
                and last.level == level
                and len((last.text + " " + ln.text).split()) <= MAX_HEADING_WORDS
                and not _is_structure_heading(ln.text)
                and not _is_structure_heading(last.text)
                and not STATEMENT_DONE_RE.search(last.text)
            ):
                last.text = f"{last.text} {ln.text.strip()}"
            else:
                blocks.append(Block("heading", page.number, ln.text.strip(), level=level))
        else:
            pending.append(ln)
        i += 1
    flush_text()
    for b in blocks:
        if b.kind == "table":
            b.text = render_table(b.title, b.unit, b.header, b.rows)
    return blocks


def mostly_numbers(text: str) -> bool:
    """A row, not a sentence: 2+ numbers (not years) and they are a big share of the words."""
    words = text.split()
    nums = [w for w in words if NUMBER_TOKEN_RE.match(w) and not YEAR_TOKEN_RE.match(w)]
    return len(nums) >= 2 and len(nums) >= NUMBER_SHARE * len(words)


def _short_line(b: Block) -> bool:
    """A loose line of the header zone: a label, a unit line, column text (not a sentence)."""
    words = b.text.split()
    return (
        b.kind in ("heading", "text")
        and 0 < len(words) <= MAX_ZONE_WORDS
        and not b.text.rstrip().endswith(".")
        and not _is_structure_heading(b.text.strip())
    )


def title_from_header_zone(blocks: list[Block], tb: Block) -> None:
    """Q106: a table with no title, under loose header lines (J&J "Supplementary Sales Data",
    then the unit line, the years and "Sales to customers by segment"). Walk up the short
    blocks on the same page; the highest heading among them is the title, and the short
    blocks below it move into the table header. Strict: no heading in the run, no change."""
    run: list[int] = []
    k = len(blocks) - 1
    while k >= 0 and len(run) < MAX_ZONE_BLOCKS:
        b = blocks[k]
        if b.page != tb.page or not _short_line(b):
            break
        run.append(k)
        k -= 1
    heads = [m for m in run if blocks[m].kind == "heading" and title_shape_ok(blocks[m].text)]
    if not heads:
        return
    top = heads[-1]  # the highest heading of the run
    moved = blocks[top + 1 :]
    tb.title = blocks[top].text
    tb.header = [b.text for b in moved] + tb.header
    if tb.unit is None:
        for b in moved:
            m = UNIT_RE.search(b.text)
            if m:
                tb.unit = m.group(0).strip("() ")
                break
    del blocks[top + 1 :]


def title_shape_ok(text: str) -> bool:
    """A table title is not a row, a bullet, a list fragment or noise."""
    t = text.strip()
    if not t or row_like(t) or BULLET_RE.match(t) or t[0] in "•●▪■◦" or is_noise(t):
        return False
    return t.count("(") == t.count(")")  # "Exhibit 4.1)" is a fragment


def _para_start(prev: Line, ln: Line) -> bool:
    """The line starts a new paragraph (gap above, or the previous line ended one)."""
    gap = ln.top - prev.bottom
    return gap > 0.6 * max(ln.size, 1.0) or prev.text.rstrip().endswith((".", ":"))


def render_table(title: str | None, unit: str | None, header: list[str], rows: list[str]) -> str:
    parts = [p for p in (title, f"({unit})" if unit else None) if p]
    return "\n".join(parts + header + rows)


def join_continued(blocks: list[Block]) -> list[Block]:
    """Join a table that starts a page with the table that ended the previous page."""
    out: list[Block] = []
    for b in blocks:
        if b.kind == "table" and out:
            # skip "(continued)" headings between the two parts
            k = len(out) - 1
            while (
                k >= 0
                and out[k].kind == "heading"
                and out[k].page == b.page
                and (CONTINUED_RE.search(out[k].text))
            ):
                k -= 1
            prev = out[k] if k >= 0 else None
            first_on_page = all(x.page != b.page for x in out[: k + 1])
            if (
                prev is not None
                and prev.kind == "table"
                and prev.page_end == b.page - 1
                and first_on_page
                and (b.title is None or b.title == prev.title or CONTINUED_RE.search(b.title))
            ):
                del out[k + 1 :]
                new_header = [
                    h for h in b.header if h.strip() not in {x.strip() for x in prev.header}
                ]
                prev.rows.extend(new_header + b.rows)
                prev.page_end = b.page
                prev.unit = prev.unit or b.unit
                prev.text = render_table(prev.title, prev.unit, prev.header, prev.rows)
                continue
        out.append(b)
    return out
