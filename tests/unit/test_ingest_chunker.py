import re

import pytest

from filing_rag.ingest.blocks import Block
from filing_rag.ingest.chunker import Chunk, ChunkConfig, Chunker, Placed
from filing_rag.ingest.labels import DocMeta, chunk_header, period_label
from tests.unit.ingest_helpers import word_count

META = DocMeta("ADOBE_2018_10K", "Adobe", "10-K", 2018)
CFG = ChunkConfig(target=60, max=80, overlap=10)


def sentences(n: int, prefix: str = "Word") -> str:
    return " ".join(f"{prefix} number {i} is in this sentence." for i in range(n))


def placed(block: Block, section: str | None = "Item 7", sub: str | None = None) -> Placed:
    return Placed(block, section, sub, None)


def run(items: list[Placed], cfg: ChunkConfig = CFG) -> list[Chunk]:
    return Chunker(META, word_count, cfg).run(items)


def test_header_and_period_label() -> None:
    assert chunk_header(META, "Item 8", "Note 12 Income Taxes", None) == (
        "Adobe 10-K FY2018 › Item 8 › Note 12 Income Taxes"
    )
    q = DocMeta("X", "Ulta", "earnings", 2023, fiscal_quarter=1)
    assert period_label(q) == "FY2023 Q1"


def test_no_chunk_exceeds_the_limit_and_long_text_is_split_with_overlap() -> None:
    chunks = run([placed(Block("text", 1, sentences(40)))])
    assert len(chunks) > 3
    assert all(c.n_tokens <= CFG.max for c in chunks)
    # overlap: the start of chunk 2 repeats the end of chunk 1
    last_sentence = chunks[0].text.split(". ")[-1].strip(".")
    assert last_sentence in chunks[1].text
    assert chunks[0].embed_text.startswith("Adobe 10-K FY2018 › Item 7\n")


def test_chunks_never_cross_sections() -> None:
    items = [
        placed(Block("text", 1, "Short text in item seven."), "Item 7"),
        placed(Block("heading", 2, "Item 8. Financial Statements", level=1), "Item 8"),
        placed(Block("text", 2, "Short text in item eight."), "Item 8"),
    ]
    chunks = run(items)
    assert [c.section for c in chunks] == ["Item 7", "Item 8"]
    assert chunks[1].text.startswith("Item 8. Financial Statements")


def test_small_parts_are_joined_and_heading_stays_with_text() -> None:
    items = [
        placed(Block("heading", 1, "Liquidity", level=2)),
        placed(Block("text", 1, sentences(1))),
        placed(Block("heading", 1, "Capital Resources", level=2)),
        placed(Block("text", 1, sentences(1))),
    ]
    chunks = run(items)
    assert len(chunks) == 1
    assert "Liquidity" in chunks[0].text and "Capital Resources" in chunks[0].text


def test_heading_is_not_left_alone_before_a_long_paragraph() -> None:
    items = [
        placed(Block("heading", 1, "Item 7. Management's Discussion", level=1)),
        placed(Block("text", 1, sentences(8))),
    ]
    chunks = run(items)
    assert chunks[0].text.startswith("Item 7. Management's Discussion\n")
    assert len(chunks[0].text.split()) > 10


def test_no_overlap_across_a_heading() -> None:
    items = [
        placed(Block("text", 1, sentences(6, "Alpha")), sub="A"),
        placed(Block("heading", 1, "New Topic", level=2), sub="B"),
        placed(Block("text", 1, sentences(6, "Beta")), sub="B"),
    ]
    chunks = run(items)
    topic = next(c for c in chunks if "New Topic" in c.text)
    assert topic.text.startswith("New Topic")
    assert "Alpha" not in topic.text


def test_large_table_becomes_row_groups_with_shared_id_and_header() -> None:
    rows = [f"Row label {i}      {i},000      {i},500" for i in range(40)]
    table = Block(
        "table", 9, "", title="Net sales by segment", unit="in millions",
        header=["          2019        2018"], rows=rows,
    )  # fmt: skip
    chunks = run([placed(table, "Item 8", "Note 11 Segments")])
    assert len(chunks) > 1
    assert len({c.table_id for c in chunks}) == 1
    assert [c.table_part for c in chunks] == list(range(1, len(chunks) + 1))
    for c in chunks:
        assert c.is_table and c.n_tokens <= CFG.max
        assert "2019" in c.text and "Net sales by segment" in c.text
        assert "Unit: in millions" in c.embed_text
    all_rows = "\n".join(c.text for c in chunks)
    assert all(r in all_rows for r in rows)


def test_chunk_ids_are_stable_and_unique() -> None:
    items = [placed(Block("text", 1, "Same text.")), placed(Block("text", 2, sentences(20)))]
    a = [c.chunk_id for c in run(items)]
    b = [c.chunk_id for c in run(items)]
    assert a == b
    assert len(set(a)) == len(a)


def test_heading_directly_before_a_table_is_not_its_own_chunk() -> None:
    table = Block("table", 3, "", title="Revenue by region", header=["  2019"], rows=["US  1,000"])
    items = [placed(Block("heading", 3, "Revenue by region", level=2)), placed(table)]
    chunks = run(items)
    assert len(chunks) == 1 and chunks[0].is_table


def test_label_depth_sets_the_embedded_label_and_context_keeps_the_full_path() -> None:
    text = placed(Block("text", 3, sentences(2)), "Item 8", "Note 9 Debt")
    rows = ["Term loan      100      90"]
    table = Block("table", 3, "", title="Debt maturities", unit="in millions", rows=rows)
    tab = placed(table, "Item 8", "Note 9 Debt")
    full_path = "Adobe 10-K FY2018 › Item 8 › Note 9 Debt"

    for depth, head in [
        ("section", "Adobe 10-K FY2018 › Item 8\n"),
        ("full", full_path + "\n"),
    ]:
        cfg = ChunkConfig(target=60, max=80, overlap=10, label_depth=depth)  # type: ignore[arg-type]
        c = run([text], cfg)[0]
        assert c.embed_text.startswith(head)
        assert c.context == full_path
        t = run([tab], cfg)[0]
        assert "Table: Debt maturities." in t.embed_text  # Q105: title at every depth
        assert t.table_title == "Debt maturities" and t.context == full_path

    cfg = ChunkConfig(target=60, max=80, overlap=10, label_depth="none")
    c = run([text], cfg)[0]
    assert c.embed_text.startswith("Word number 0")
    t = run([tab], cfg)[0]
    assert t.embed_text.startswith("Table: Debt maturities. Unit: in millions.")


# ---------- Q105: embedded text = label + everything in the answer text ----------

WORD_RE = re.compile(r"[A-Za-z0-9$%][A-Za-z0-9$%,.\-]*")


def words(text: str) -> set[str]:
    """Words without the punctuation that the label adds or removes ("(in millions)")."""
    return {w.rstrip(".,") for w in WORD_RE.findall(text)}


def table_block(n_rows: int = 3, title: str | None = "Key financial metrics") -> Block:
    rows = [f"Operating income {i}      2,{i}47      2,{i}34" for i in range(n_rows)]
    return Block(
        "table", 2, "", title=title, unit="in millions",
        header=["          Q1 2023        Q1 2022"], rows=rows,
    )  # fmt: skip


@pytest.mark.parametrize("depth", ["none", "section", "full"])
def test_every_word_of_the_answer_text_is_in_the_embedded_text(depth: str) -> None:
    cfg = ChunkConfig(target=60, max=80, overlap=10, label_depth=depth)  # type: ignore[arg-type]
    items = [
        placed(Block("text", 1, sentences(12)), "Item 7", "Results"),
        placed(table_block(n_rows=3), "Item 7", "Results"),
        placed(table_block(n_rows=40), "Item 8", "Note 2"),  # split into row groups
    ]
    chunks = run(items, cfg)
    assert any(c.is_table for c in chunks) and any(not c.is_table for c in chunks)
    for c in chunks:
        missing = words(c.text) - words(c.embed_text)
        assert not missing, f"{'table' if c.is_table else 'text'} chunk: {missing}"


def test_title_is_embedded_in_every_part_of_a_split_table() -> None:
    chunks = run([placed(table_block(n_rows=40), "Item 8")])
    assert len(chunks) > 1
    for c in chunks:
        assert c.embed_text.startswith("Adobe 10-K FY2018 › Item 8. Table: Key financial metrics.")
        assert c.text.startswith("Key financial metrics")


def test_a_long_title_still_keeps_every_chunk_under_the_limit() -> None:
    title = " ".join(f"Title{i}" for i in range(20))  # 20 tokens of the 80-token limit
    chunks = run([placed(table_block(n_rows=40, title=title), "Item 8")])
    assert len(chunks) > 1
    assert all(c.n_tokens <= CFG.max for c in chunks)
    assert all(title in c.embed_text for c in chunks)
    assert chunks[0].n_tokens == word_count(chunks[0].embed_text)


def test_a_table_without_title_has_a_plain_table_label() -> None:
    c = run([placed(table_block(title=None), "Item 7")])[0]
    assert "Adobe 10-K FY2018 › Item 7. Table. Unit: in millions." in c.embed_text


def test_a_word_longer_than_a_chunk_is_cut_by_length() -> None:
    def chars(text: str) -> int:  # 1 token per 4 characters
        return len(text) // 4 + 1

    long_word = "x" * 2000  # about 500 tokens, no spaces
    chunks = Chunker(META, chars, CFG).run([placed(Block("text", 1, f"Start {long_word} end."))])
    assert all(c.n_tokens <= CFG.max for c in chunks)
    assert sum(c.text.count("x") for c in chunks) >= 2000  # nothing lost (overlap may repeat)
    assert chunks[-1].text.endswith("end.")
