from filing_rag.ingest.blocks import Block
from filing_rag.ingest.chunker import Chunk, Chunker, Placed
from filing_rag.ingest.label_checks import check_labels, summarise
from filing_rag.ingest.labels import DocMeta
from tests.unit.ingest_helpers import word_count

META = DocMeta("X_2019_10K", "Co", "10-K", 2019)


# each text is ~200 tokens, so every item becomes its own chunk
def chunks(items: list[tuple[str | None, str | None, int]]) -> list[Chunk]:
    placed = [
        Placed(Block("text", page, f"Text {i}. " + "word " * 200), sec, sub, None)
        for i, (sec, sub, page) in enumerate(items)
    ]
    return Chunker(META, word_count).run(placed)


def rules(flags: list[dict[str, object]]) -> set[object]:
    return {f["rule"] for f in flags}


def test_clean_labels_have_no_flags() -> None:
    cs = chunks([("Item 7. MD&A", None, 20), ("Item 8. Statements", "Note 1 – Basis", 40),
                 ("Item 8. Statements", "Note 2 – Revenue", 42)])  # fmt: skip
    assert check_labels("10-K", cs) == []


def test_flags_each_rule() -> None:
    cs = chunks(
        [
            ("Item 8. Statements", "Note 3 – Debt", 40),
            ("Item 8. Statements", "Note 2 – Revenue", 41),  # note backwards
            ("Item 7. MD&A", "Note 5 – Leases", 42),  # item backwards + note outside
            ("Item 9A. Controls", "Service cost 251 288 268", 50),  # heading shape
        ]
    )
    found = rules(check_labels("10-K", cs))
    assert {"note_backwards", "item_backwards", "note_outside_financial", "heading_shape"} <= found


def test_long_span_and_summary() -> None:
    cs = chunks([("Item 8. Statements", "Note 1 – Basis", 40), ("Item 8. Statements",
                 "Note 1 – Basis", 90)])  # fmt: skip
    flags = check_labels("10-K", cs)
    assert "long_span" in rules(flags)
    assert summarise(flags)["long_span"]["count"] == 1
