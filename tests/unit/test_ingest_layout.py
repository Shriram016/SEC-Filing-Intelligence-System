from filing_rag.ingest.layout import (
    Line,
    Word,
    find_gutter,
    fix_word,
    group_lines,
    order_columns,
    strip_repeating,
)
from tests.unit.ingest_helpers import line, page_of, text_line


def test_fix_word_dollar_printed_as_s() -> None:
    assert fix_word("S1,579,406", None) == "$1,579,406"
    assert fix_word("S2.6", None) == "$2.6"
    assert fix_word("S", "1,234") == "$"
    assert fix_word("S", "Corporation") == "S"
    assert fix_word("SEC", None) == "SEC"


def test_group_lines_by_vertical_position() -> None:
    words = [
        Word("World", 60, 85, 100.5, 110, 10, False),
        Word("Hello", 10, 35, 100, 110, 10, True),
        Word("Next", 10, 30, 115, 125, 10, False),
    ]
    lines = group_lines(words, page=3)
    assert [ln.text for ln in lines] == ["Hello World", "Next"]
    assert lines[0].page == 3
    assert not lines[0].bold  # only part of the line is bold


def test_segments_split_at_big_gaps() -> None:
    ln = line((50, "Net sales"), (300, "1,234"), (400, "1,100"))
    assert [t for _, t in ln.segments()] == ["Net sales", "1,234", "1,100"]
    assert "Net sales" in ln.aligned(5.0)


def two_column_lines() -> list[Line]:
    lines = []
    for i in range(16):
        top = 100 + i * 12
        lines.append(
            line((40, f"left column words here number {i}"), (330, f"right side text goes {i}"),
                 top=top)
        )  # fmt: skip
    return lines


def test_find_gutter_on_two_text_columns() -> None:
    gutter = find_gutter(two_column_lines(), 612)
    assert gutter is not None
    assert 220 < gutter < 330


def test_tables_are_not_two_columns() -> None:
    lines = [line((40, f"Revenue line item {i}"), (400, "1,234"), (480, "5,678"), top=100 + i * 12)
             for i in range(16)]  # fmt: skip
    assert find_gutter(lines, 612) is None


def test_order_columns_left_then_right_and_keeps_full_width_lines() -> None:
    lines = two_column_lines()
    heading = line((40, "A FULL WIDTH HEADING THAT CROSSES THE MIDDLE OF THE PAGE"), top=99)
    gutter = find_gutter(lines, 612)
    assert gutter is not None
    out = order_columns([heading, *lines], gutter)
    texts = [ln.text for ln in out]
    assert texts[0].startswith("A FULL WIDTH")
    assert texts[1].startswith("left column") and texts[16].startswith("left column")
    assert texts[17].startswith("right side")


WORDS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
]


def test_strip_repeating_headers_footers_and_page_numbers() -> None:
    pages = []
    for n in range(1, 7):
        pages.append(
            page_of(
                [
                    text_line("Apple Inc. | 2019 Form 10-K", 20),
                    text_line(f"Body text {WORDS[n]} on this page", 100),
                    text_line(f"More words {WORDS[n + 6]} here", 120),
                    text_line(str(n), 760),
                ],
                number=n,
            )
        )
    removed = strip_repeating(pages)
    assert removed == 12
    assert all(len(p.lines) == 2 for p in pages)
    assert pages[0].lines[0].text.startswith("Body text")
