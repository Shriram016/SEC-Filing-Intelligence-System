"""Make chunks from blocks (Q93, Q94).

Text: structure-aware. A chunk never crosses a section. A new chunk starts at a heading when
the current chunk is already big enough; small parts of the same section are joined. A long
part is split at paragraphs, then sentences, then words (recursive), with an overlap of about
`overlap` tokens between the pieces of one part.

Tables: one table = one chunk. A table above the token limit is split into row groups; each
group repeats the label and column headers, and all parts share one `table_id`.

All sizes are counted with the embedding model's tokenizer on the text that is embedded
(header + body), so no chunk is cut by the 512-token input limit.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from filing_rag.ingest.blocks import Block
from filing_rag.ingest.labels import (
    DocMeta,
    LabelDepth,
    chunk_header,
    collapse,
    table_label,
)

TokenCounter = Callable[[str], int]
SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(\"“$])")
MIN_CHUNK_SHARE = 0.4  # start a new chunk at a heading once the chunk has 40% of the target


@dataclass(frozen=True)
class ChunkConfig:
    target: int = 350
    max: int = 480
    overlap: int = 50
    label_depth: LabelDepth = "section"  # Q99: what label goes into the embedded text


@dataclass(frozen=True)
class Placed:
    """A block with the section path that was current when it was read."""

    block: Block
    section: str | None
    subsection: str | None
    heading: str | None


@dataclass
class Chunk:
    chunk_id: str
    doc_name: str
    company: str
    doc_type: str
    fiscal_year: int
    list_fiscal_year: int | None
    fiscal_quarter: int | None
    period_end: str | None
    report_date: str | None
    period_source: str
    section: str | None
    subsection: str | None
    heading: str | None
    page: int
    page_end: int
    is_table: bool
    context: str  # the header line
    text: str  # what the answer step reads (tables keep their layout)
    embed_text: str  # what is embedded (header/label + collapsed text)
    n_tokens: int
    table_id: str | None = None
    table_part: int | None = None
    table_parts: int | None = None
    table_label: str | None = None
    table_title: str | None = None
    warnings: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("embed_text")
        return d


@dataclass
class _Piece:
    text: str
    page: int
    tokens: int
    heading: bool = False


def _sha(*parts: object) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:20]


class Chunker:
    def __init__(self, meta: DocMeta, count: TokenCounter, cfg: ChunkConfig | None = None):
        self.meta = meta
        self.count = count
        self.cfg = cfg or ChunkConfig()
        self.chunks: list[Chunk] = []
        self._ids: set[str] = set()
        self._buf: list[_Piece] = []
        self._ctx: Placed | None = None
        self._header_tokens = 0

    # ---------- public ----------
    def run(self, placed: list[Placed]) -> list[Chunk]:
        for item in placed:
            b = item.block
            if b.kind == "table":
                if self._buf and self._only_headings():
                    self._buf = []  # fix 6: the heading is in the table label already
                self._flush()
                self._table(item)
                continue
            if self._ctx is not None and item.section != self._ctx.section:
                self._flush()
            if b.kind == "heading":
                if self._buf_tokens() >= MIN_CHUNK_SHARE * self.cfg.target:
                    self._flush()
                self._add(item, b.text, b.page, overlap=False, heading=True)
                continue
            for piece in self._split(b.text, self._body_budget(item)):
                self._add(item, piece, b.page, overlap=self._same_part(item))
        self._flush()
        return self.chunks

    # ---------- text ----------
    def _embed_header(self, p: Placed) -> str:
        """The label that is embedded (depends on `label_depth`)."""
        return chunk_header(self.meta, p.section, p.subsection, p.heading, self.cfg.label_depth)

    def _full_path(self, p: Placed) -> str:
        """The full section path, stored as `context` for display and citations."""
        return chunk_header(self.meta, p.section, p.subsection, p.heading)

    def _body_budget(self, item: Placed) -> int:
        header = self._embed_header(item)
        return max(32, self.cfg.max - self.count(header) - 4)

    def _buf_tokens(self) -> int:
        return sum(p.tokens for p in self._buf)

    def _same_part(self, item: Placed) -> bool:
        c = self._ctx
        return c is not None and (c.section, c.subsection, c.heading) == (
            item.section,
            item.subsection,
            item.heading,
        )

    def _add(
        self, item: Placed, text: str, page: int, overlap: bool, heading: bool = False
    ) -> None:
        tokens = self.count(text)
        if not self._buf:
            self._start(item)
        elif self._header_tokens + self._buf_tokens() + tokens > self.cfg.target and not (
            self._only_headings()
            and self._header_tokens + self._buf_tokens() + tokens <= self.cfg.max
        ):
            tail = self._overlap_tail() if overlap else []
            self._flush()
            self._start(item)
            for t in tail:
                self._buf.append(t)
        self._buf.append(_Piece(text, page, tokens, heading))

    def _only_headings(self) -> bool:
        """A heading is never left alone: it stays with the text that follows it."""
        return all(p.heading for p in self._buf)

    def _start(self, item: Placed) -> None:
        self._ctx = item
        header = self._embed_header(item)
        self._header_tokens = self.count(header)

    def _overlap_tail(self) -> list[_Piece]:
        """Last sentences of the buffer, about `overlap` tokens, carried into the next chunk."""
        if not self._buf or self.cfg.overlap <= 0:
            return []
        last = self._buf[-1]
        sentences = SENTENCE_RE.split(last.text)
        tail: list[str] = []
        total = 0
        for s in reversed(sentences):
            n = self.count(s)
            if total + n > self.cfg.overlap and tail:
                break
            if n > self.cfg.overlap * 2:
                break
            tail.insert(0, s)
            total += n
        if not tail or (len(tail) == len(sentences) and len(self._buf) == 1):
            return []
        text = " ".join(tail)
        return [_Piece(text, last.page, self.count(text))]

    def _split(self, text: str, budget: int) -> list[str]:
        """Recursive split: whole paragraph → sentences → word windows."""
        if self.count(text) <= budget:
            return [text]
        out: list[str] = []
        cur = ""
        for s in SENTENCE_RE.split(text):
            if self.count(s) > budget:
                if cur:
                    out.append(cur)
                    cur = ""
                out.extend(self._split_words(s, budget))
                continue
            cand = f"{cur} {s}".strip()
            if self.count(cand) > budget and cur:
                out.append(cur)
                cur = s
            else:
                cur = cand
        if cur:
            out.append(cur)
        return out

    def _split_words(self, text: str, budget: int) -> list[str]:
        words = text.split()
        out: list[str] = []
        start = 0
        while start < len(words):
            end = min(len(words), start + max(1, int(budget * 0.7)))
            while end > start + 1 and self.count(" ".join(words[start:end])) > budget:
                end = start + max(1, int((end - start) * 0.85))
            piece = " ".join(words[start:end])
            if end == start + 1 and self.count(piece) > budget:
                out.extend(self._split_chars(piece, budget))  # one "word" longer than a chunk
            else:
                out.append(piece)
            start = end
        return out

    def _split_chars(self, word: str, budget: int) -> list[str]:
        """Cut a string without spaces (e.g. a long URL or dotted line) by length."""
        out: list[str] = []
        size = max(8, budget * 2)
        start = 0
        while start < len(word):
            end = min(len(word), start + size)
            while end > start + 1 and self.count(word[start:end]) > budget:
                end = start + max(1, int((end - start) * 0.8))
            out.append(word[start:end])
            start = end
        return out

    def _flush(self) -> None:
        if not self._buf or self._ctx is None:
            self._buf = []
            return
        ctx = self._ctx
        body = "\n".join(p.text for p in self._buf)
        self._emit_text(ctx, body, self._buf[0].page, self._buf[-1].page)
        self._buf = []

    def _emit_text(self, ctx: Placed, body: str, page: int, page_end: int) -> None:
        header = self._embed_header(ctx)
        embed = "\n".join(p for p in (header, collapse(body)) if p)
        n = self.count(embed)
        if n > self.cfg.max:  # safety net: never exceed the limit
            budget = max(32, self.cfg.max - self.count(header) - 4)
            for piece in self._split_words(body, budget):
                self._emit_text(ctx, piece, page, page_end)
            return
        self._append(
            Chunk(
                chunk_id=self._new_id(page, body),
                **self._meta_fields(),
                section=ctx.section,
                subsection=ctx.subsection,
                heading=ctx.heading,
                page=page,
                page_end=page_end,
                is_table=False,
                context=self._full_path(ctx),
                text=body,
                embed_text=embed,
                n_tokens=n,
            )
        )

    # ---------- tables ----------
    def _table(self, item: Placed) -> None:
        b = item.block
        header = self._embed_header(item)
        # Q105: the title is part of the table (the answer text shows it), so it is always
        # embedded, whatever the label depth. Rule: embedded text = label + the answer text.
        title = b.title
        label = table_label(header, title, b.unit, b.header)
        fixed = label
        fixed_tokens = self.count(fixed)
        warnings: list[str] = []
        if fixed_tokens > self.cfg.max // 2:  # huge label/header: keep the label short
            label = table_label(header, title, b.unit, [])
            fixed, fixed_tokens = label, self.count(label)
            warnings.append("column headers left out of the label (too long)")
        budget = self.cfg.max - fixed_tokens - 4
        groups: list[list[str]] = []
        cur: list[str] = []
        cur_tokens = 0
        for row in b.rows:
            n = self.count(collapse(row)) + 1
            if n > budget:  # a single giant row: cut it
                row = " ".join(row.split()[: max(1, int(budget * 0.6))])
                n = self.count(collapse(row)) + 1
                warnings.append("a table row was cut to fit the limit")
            if cur and cur_tokens + n > budget:
                groups.append(cur)
                cur, cur_tokens = [], 0
            cur.append(row)
            cur_tokens += n
        if cur:
            groups.append(cur)
        if not groups:
            return
        table_id = _sha(self.meta.doc_name, b.page, b.title, b.rows[0] if b.rows else "")
        for i, rows in enumerate(groups, start=1):
            display = "\n".join(
                p for p in (b.title, f"({b.unit})" if b.unit else None, *b.header, *rows) if p
            )
            embed = f"{fixed}\n" + collapse("\n".join(rows))
            n = self.count(embed)
            self._append(
                Chunk(
                    chunk_id=self._new_id(b.page, display),
                    **self._meta_fields(),
                    section=item.section,
                    subsection=item.subsection,
                    heading=item.heading,
                    page=b.page,
                    page_end=b.page_end,
                    is_table=True,
                    context=self._full_path(item),
                    text=display,
                    embed_text=embed,
                    n_tokens=n,
                    table_id=table_id,
                    table_part=i,
                    table_parts=len(groups),
                    table_label=label,
                    table_title=b.title,
                    warnings=list(dict.fromkeys(warnings)),
                )
            )

    # ---------- helpers ----------
    def _meta_fields(self) -> dict[str, Any]:
        m = self.meta
        return {
            "doc_name": m.doc_name,
            "company": m.company,
            "doc_type": m.doc_type,
            "fiscal_year": m.fiscal_year,
            "list_fiscal_year": m.list_fiscal_year or m.fiscal_year,
            "fiscal_quarter": m.fiscal_quarter,
            "period_end": m.period_end.isoformat() if m.period_end else None,
            "report_date": m.report_date.isoformat() if m.report_date else None,
            "period_source": m.period_source,
        }

    def _new_id(self, page: int, text: str) -> str:
        """Same document + page + text → same id (idempotent re-runs)."""
        base = _sha(self.meta.doc_name, page, text)
        cid, k = base, 1
        while cid in self._ids:
            k += 1
            cid = f"{base}-{k}"
        self._ids.add(cid)
        return cid

    def _append(self, chunk: Chunk) -> None:
        self.chunks.append(chunk)
