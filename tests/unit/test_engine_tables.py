"""Split-table expansion (Q105): code adds the missing parts of a retrieved split table."""

from typing import Any

from filing_rag.engine.tables import ADDED_FLAG, expand_tables
from filing_rag.search.searcher import Hit


def text_hit(cid: str, page: int = 1) -> Hit:
    return Hit(0.8, {"chunk_id": cid, "doc_name": "A_10K", "page": page, "is_table": False})


def part(table: str, n: int, of: int, score: float = 0.5) -> Hit:
    payload: dict[str, Any] = {
        "chunk_id": f"{table}-{n}", "doc_name": "A_10K", "page": 2, "is_table": True,
        "table_id": table, "table_part": n, "table_parts": of, "text": f"{table} rows {n}",
    }  # fmt: skip
    return Hit(score, payload)


class FakeStore:
    """All parts of each table; records which tables were fetched."""

    def __init__(self, tables: dict[str, int]) -> None:
        self.tables = tables
        self.calls: list[str] = []

    def table_parts(self, table_id: str) -> list[Hit]:
        self.calls.append(table_id)
        return [
            part(table_id, n, self.tables[table_id], 0.0)
            for n in range(1, 1 + self.tables[table_id])
        ]


def ids(hits: list[Hit]) -> list[str]:
    return [h.payload["chunk_id"] for h in hits]


def test_no_split_table_means_no_change_and_no_fetch() -> None:
    hits = [text_hit("a"), part("T", 1, 1)]
    store = FakeStore({"T": 1})
    out, added = expand_tables(hits, store)
    assert ids(out) == ids(hits) and added == 0 and store.calls == []


def test_missing_parts_are_added_next_to_the_found_part_in_order() -> None:
    hits = [text_hit("a"), part("T", 2, 3), text_hit("b")]
    out, added = expand_tables(hits, FakeStore({"T": 3}))
    assert ids(out) == ["a", "T-1", "T-2", "T-3", "b"]
    assert added == 2
    flags = {h.payload["chunk_id"]: h.payload.get(ADDED_FLAG, False) for h in out}
    assert flags == {"a": False, "T-1": True, "T-2": False, "T-3": True, "b": False}


def test_parts_already_found_are_not_added_twice() -> None:
    hits = [part("T", 3, 3), text_hit("a"), part("T", 1, 3)]
    out, added = expand_tables(hits, FakeStore({"T": 3}))
    assert ids(out) == ["T-1", "T-2", "T-3", "a"]
    assert added == 1 and len(set(ids(out))) == len(out)


def test_the_cap_keeps_the_nearest_parts() -> None:
    hits = [part("T", 4, 8)]
    out, added = expand_tables(hits, FakeStore({"T": 8}), max_extra=3)
    assert added == 3
    # distance 1 (parts 3 and 5), then distance 2: part 2 before part 6 (lower part first)
    assert ids(out) == ["T-2", "T-3", "T-4", "T-5"]


def test_the_cap_is_shared_and_the_best_ranked_table_goes_first() -> None:
    hits = [part("T", 1, 3), part("U", 1, 3)]
    store = FakeStore({"T": 3, "U": 3})
    out, added = expand_tables(hits, store, max_extra=3)
    assert added == 3
    assert ids(out) == ["T-1", "T-2", "T-3", "U-1", "U-2"]


def test_cap_zero_turns_the_expansion_off() -> None:
    hits = [part("T", 1, 3)]
    store = FakeStore({"T": 3})
    out, added = expand_tables(hits, store, max_extra=0)
    assert ids(out) == ["T-1"] and added == 0 and store.calls == []


def test_each_table_is_fetched_once() -> None:
    hits = [part("T", 1, 4), part("T", 4, 4)]
    store = FakeStore({"T": 4})
    out, added = expand_tables(hits, store)
    assert store.calls == ["T"]
    assert ids(out) == ["T-1", "T-2", "T-3", "T-4"] and added == 2
