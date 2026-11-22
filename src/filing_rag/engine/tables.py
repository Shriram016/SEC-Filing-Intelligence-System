"""Split-table expansion (Q105, engine.md §3.2). Code only, no LLM.

A table above the token limit is stored as row groups ("parts") that share one `table_id`.
The search can return part 1 while the needed row is in part 2. So, after the search, code
adds the missing parts of each retrieved table:

- nearest parts first (part 2 before part 5 when part 1 was found);
- at most `max_extra` added chunks per question, so the answer prompt stays small;
- the parts of one table are put together, in part order, where the first part was found.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from filing_rag.search.searcher import Hit

ADDED_FLAG = "added_table_part"  # payload key on an added chunk (not found by the search)


class TablePartsFetch(Protocol):
    def table_parts(self, table_id: str) -> list[Hit]: ...


def _key(h: Hit) -> str:
    return str(h.payload.get("chunk_id") or (h.doc_name, h.page, h.payload.get("table_part")))


def _is_split(h: Hit) -> bool:
    return bool(h.payload.get("is_table")) and int(h.payload.get("table_parts") or 1) > 1


def _part(h: Hit) -> int:
    return int(h.payload.get("table_part") or 1)


def expand_tables(
    hits: Sequence[Hit], fetch: TablePartsFetch, max_extra: int = 3
) -> tuple[list[Hit], int]:
    """Return (hits with the added parts, number of added chunks)."""
    if max_extra <= 0 or not any(_is_split(h) for h in hits):
        return list(hits), 0
    present = {_key(h) for h in hits}
    added: dict[str, list[Hit]] = {}  # table_id -> added parts
    budget = max_extra
    for h in hits:  # rank order: the best-ranked table gets its parts first
        table_id = h.payload.get("table_id")
        if budget == 0 or not _is_split(h) or not table_id or table_id in added:
            continue
        found = [_part(x) for x in hits if x.payload.get("table_id") == table_id]
        missing = [p for p in fetch.table_parts(str(table_id)) if _key(p) not in present]
        missing.sort(key=lambda p: (min(abs(_part(p) - f) for f in found), _part(p)))
        take = missing[:budget]
        added[str(table_id)] = [Hit(0.0, {**p.payload, ADDED_FLAG: True}) for p in take]
        budget -= len(take)

    out: list[Hit] = []
    placed: set[str] = set()
    for h in hits:
        table_id = h.payload.get("table_id")
        if table_id and str(table_id) in added:
            if table_id in placed:
                continue
            placed.add(str(table_id))
            parts = [x for x in hits if x.payload.get("table_id") == table_id]
            out.extend(sorted(parts + added[str(table_id)], key=_part))
        else:
            out.append(h)
    return out, sum(len(v) for v in added.values())
