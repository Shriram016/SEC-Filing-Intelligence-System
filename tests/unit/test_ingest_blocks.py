import pytest

from filing_rag.ingest.blocks import (
    Block,
    find_tables,
    is_heading,
    is_row,
    is_year_header,
    join_continued,
    page_blocks,
)
from filing_rag.ingest.layout import Line
from tests.unit.ingest_helpers import line, page_of, text_line


def test_is_row_and_year_header() -> None:
    assert is_row(line((50, "Net sales"), (300, "$ 260,174"), (400, "265,595")))
    assert is_row(line((50, "Effective tax rate"), (300, "15.9%"), (400, "(18.3)")))
    assert not is_row(text_line("Total net sales decreased 2% or $5.4 billion during 2019.", 100))
    years = line((300, "2019"), (400, "2018"), (500, "2017"))
    assert is_year_header(years) and not is_row(years)
    sentence = text_line(
        "Provision for income taxes and the effective tax rate for 2019, 2018 and 2017 "
        "were as follows in the table below with more words here",
        100,
    )
    assert not is_year_header(sentence)


def test_is_heading_levels() -> None:
    body = 10.0
    assert is_heading(text_line("Item 7. Management's Discussion", 100), body) == 1
    assert is_heading(text_line("LONG-TERM DEBT", 100, bold=True), body) == 1
    assert is_heading(text_line("JOLIE FRANSHESA OCAMP", 100), body) == 2  # caps only
    assert is_heading(text_line("Fiscal 2019 Highlights", 100, bold=True), body) == 2
    assert is_heading(text_line("Note 3 – Financial Instruments", 100, bold=True), body) == 1
    assert is_heading(text_line("Bigger title", 100, size=14.0), body) == 1
    assert is_heading(text_line("• IOTG", 100, bold=True), body) == 0
    assert is_heading(text_line("A normal sentence in body text.", 100), body) == 0
    long_bold = "This bold sentence is long enough to be a run-in paragraph and not a heading."
    assert is_heading(text_line(long_bold, 100, bold=True), body) == 0


def table_lines(top: float = 200.0) -> list[Line]:
    return [
        line((300, "2019"), (400, "2018"), top=top),
        line((50, "Current assets:"), top=top + 12),
        line((60, "Cash"), (300, "48,844"), (400, "25,913"), top=top + 24),
        line((60, "Receivables"), (300, "22,926"), (400, "23,186"), top=top + 36),
        line((60, "Total current assets"), (300, "162,819"), (400, "131,339"), top=top + 48),
    ]


def test_find_tables_includes_header_and_lead_label() -> None:
    lines = [text_line("Some paragraph text before the table here.", 150), *table_lines()]
    tables = find_tables(lines)
    assert tables == [(1, 2, 6)]


def test_item_heading_is_never_a_table_header() -> None:
    lines = [
        line((18, "Item 8."), (58, "Financial Statements and Supplementary Data"), top=100),
        line((18, "Consolidated Statements of Operations"), (570, "29"), top=112),
        line((18, "Consolidated Balance Sheets"), (570, "31"), top=124),
    ]
    assert find_tables(lines)[0][0] == 1


def test_page_blocks_table_with_title_and_unit() -> None:
    lines = [
        text_line("CONSOLIDATED BALANCE SHEETS", 100),
        text_line("(In millions)", 112),
        *table_lines(130),
        text_line("The accompanying notes are an integral part of these statements.", 260),
    ]
    blocks = page_blocks(page_of(lines), body_size=10.0)
    kinds = [b.kind for b in blocks]
    assert kinds == ["heading", "table", "text"]
    table = blocks[1]
    assert table.title == "CONSOLIDATED BALANCE SHEETS"
    assert table.unit == "In millions"
    assert any("2019" in h for h in table.header)
    assert len(table.rows) == 4  # label + 3 numeric rows
    assert "48,844" in table.text


def test_paragraphs_split_at_gaps() -> None:
    lines = [
        text_line("First paragraph line one continues", 100),
        text_line("first paragraph line two ends here.", 112),
        text_line("Second paragraph starts after a gap", 140),
    ]
    blocks = page_blocks(page_of(lines), body_size=10.0)
    assert [b.kind for b in blocks] == ["text", "text"]
    assert blocks[0].text.endswith("ends here.")


def test_join_continued_table_across_pages() -> None:
    a = Block("table", 5, "", title="Balance Sheet", header=["  2019  2018"], rows=["Cash 1 2"])
    head = Block("heading", 6, "Balance Sheet (continued)", level=1)
    b = Block("table", 6, "", title=None, header=["  2019  2018"], rows=["Debt 3 4"])
    out = join_continued([a, head, b])
    assert len(out) == 1
    assert out[0].rows == ["Cash 1 2", "Debt 3 4"]
    assert out[0].page_end == 6


def test_tables_on_far_pages_are_not_joined() -> None:
    a = Block("table", 5, "", rows=["Cash 1 2"])
    b = Block("table", 7, "", rows=["Debt 3 4"])
    assert len(join_continued([a, b])) == 2


def test_column_header_cell_is_part_of_the_table() -> None:
    lines = [
        line((420, "Pension and"), top=100),
        line((300, "Foreign"), (420, "Postretirement"), top=112),
        line((60, "Balance, December 31, 2015"), (300, "(165)"), (420, "(186)"), top=124),
        line((60, "Other comprehensive income"), (300, "(41)"), (420, "12"), top=136),
    ]
    assert find_tables(lines) == [(0, 2, 4)]


def test_sentence_before_a_table_becomes_its_title() -> None:
    lines = [
        text_line("Future minimum payments under noncancelable agreements as of", 100),
        text_line("September 28, 2019, are as follows (in millions):", 112),
        line((60, "2020"), (400, "$ 1,306"), top=140),
        line((60, "2021"), (400, "1,276"), top=152),
        line((60, "2022"), (400, "1,137"), top=164),
    ]
    blocks = page_blocks(page_of(lines), body_size=10.0)
    table = next(b for b in blocks if b.kind == "table")
    assert table.title is not None and table.title.startswith("Future minimum payments")
    assert table.unit == "in millions"
    assert table.header == []


def test_note_line_is_not_a_table_header() -> None:
    lines = [
        text_line("NOTE 6 : CONTRACT LIABILITIES", 100, bold=True),
        line((300, "Dec 28,"), (400, "Dec 29,"), top=112),
        line((60, "Prepaid supply agreements"), (300, "1,234"), (400, "2,345"), top=124),
        line((60, "Other"), (300, "100"), (400, "200"), top=136),
    ]
    blocks = page_blocks(page_of(lines), body_size=10.0)
    assert blocks[0].kind == "heading" and blocks[0].text.startswith("NOTE 6")
    assert blocks[1].kind == "table" and blocks[1].title == "NOTE 6 : CONTRACT LIABILITIES"


def test_column_header_and_noise_lines_are_not_headings() -> None:
    assert is_heading(line((300, "(Unaudited)"), (400, "(Unaudited)"), (500, "Assets")), 10.0) == 0
    assert is_heading(text_line("INTEL CORPORATION", 100, bold=True), 10.0) == 0
    assert is_heading(text_line("CONDENSED CONSOLIDATED STATEMENT OF INCOME", 100), 10.0) == 1


def test_run_in_headings_are_split() -> None:
    from filing_rag.ingest.blocks import split_run_in

    got = split_run_in(text_line("12. Electronic Delivery and Acceptance. The Company may", 100))
    assert got is not None and got[0] == "12. Electronic Delivery and Acceptance"
    assert got[1] is not None and got[1].text.startswith("The Company")
    assert split_run_in(text_line("1. The company has an agreement with the bank.", 100)) is None
    bold_start = line((50, "Derivatives. The Company uses forward contracts"), top=100)
    for w in bold_start.words[:1]:
        object.__setattr__(w, "bold", True)
    got2 = split_run_in(bold_start)
    assert got2 is not None and got2[0] == "Derivatives"


def test_table_title_prefers_statement_heading_over_short_label() -> None:
    lines = [
        text_line("CONSOLIDATED STATEMENTS OF CASH FLOWS", 100, bold=True),
        text_line("OPERATING ACTIVITIES", 114, bold=True),
        line((60, "Net income"), (300, "3,972"), (400, "1,286"), top=128),
        line((60, "Depreciation"), (300, "4,176"), (400, "3,970"), top=140),
    ]
    blocks = page_blocks(page_of(lines), body_size=10.0)
    table = next(b for b in blocks if b.kind == "table")
    assert table.title == "CONSOLIDATED STATEMENTS OF CASH FLOWS"
    assert table.rows[0] == "OPERATING ACTIVITIES"


def test_bad_titles_rejected() -> None:
    from filing_rag.ingest.blocks import title_shape_ok

    assert not title_shape_ok("Exhibit 4.1)")
    assert not title_shape_ok("• Environmental, Social and Governance Report")
    assert title_shape_ok("Net sales by segment (in millions)")


def test_bold_numbered_title_is_a_major_heading_and_unit_line_is_not() -> None:
    assert is_heading(text_line("1 Significant Accounting Policies", 100, bold=True), 10.0) == 1
    assert is_heading(text_line("In millions", 100, bold=True), 10.0) == 0


def test_long_item_lines_are_headings() -> None:
    body = 10.0
    costco = (
        "Item 7—Management's Discussion and Analysis of Financial Conditions and Results of "
        "Operations (amounts in millions, except per share,"
    )
    assert is_heading(text_line(costco, 100), body) == 1
    item_502 = (
        "Item 5.02. Departure of Directors or Certain Officers; Election of Directors; "
        "Appointment of Certain Officers; Compensatory"
    )
    assert is_heading(text_line(item_502, 100), body) == 1
    prose = "Item 7 of this report describes the results of operations in more detail, as below."
    assert is_heading(text_line(prose, 100), body) == 0


def test_bare_item_line_needs_heading_style() -> None:
    body = 10.0
    assert is_heading(text_line("Item 8", 100), body) == 0  # end of a wrapped sentence
    assert is_heading(text_line("Item 8", 100, bold=True), body) == 1
    assert is_heading(text_line("ITEM 8", 100), body) == 1


# ---------- Q106: a long row name does not cut a table in two ----------

RIGHT = (340.0, 440.0)  # right edges of the two number columns


def num_row(
    label: str, *values: str, top: float, x: float = 60.0, right: tuple[float, float] = RIGHT
) -> Line:
    """A table row whose numbers are right-aligned at `right` (as in a real statement)."""
    segs: list[tuple[float, str]] = [(x, label)]
    segs += [(r - len(v) * 5.0, v) for v, r in zip(values, right, strict=True)]
    return line(*segs, top=top)


LONG_NAME = "Change in unrealized gains/losses on marketable debt securities, net of tax:"


def apple_like(gap: list[Line], right2: tuple[float, float] = RIGHT) -> list[Line]:
    """Apple 10-Q p5 shape: rows, then a long row name, then more rows."""
    top = 100.0
    out = [line((300, "2023"), (400, "2022"), top=top)]
    out += [num_row("Net income", "19,881", "19,442", top=top + 12)]
    out += [num_row("Total change on derivative instruments", "612", "973", top=top + 24)]
    for k, g in enumerate(gap):
        g.words = [w.__class__(w.text, w.x0, w.x1, top + 36 + 12 * k, top + 46 + 12 * k,
                               w.size, w.bold) for w in g.words]  # fmt: skip
    out += gap
    base = top + 36 + 12 * len(gap)
    out += [num_row("Change in fair value", "(340)", "(3,150)", top=base, right=right2)]
    out += [num_row("Total comprehensive income", "19,826", "16,639", top=base + 12, right=right2)]
    return out


def test_long_row_name_inside_a_table_keeps_one_table() -> None:
    lines = apple_like([line((35, LONG_NAME))])
    assert len(LONG_NAME.split()) > 10  # longer than a short label: the old rule cut here
    assert find_tables(lines) == [(0, 1, 6)]


def test_two_long_row_names_keep_one_table() -> None:
    gap = [line((35, "Adjustments to reconcile net income to cash generated by")),
           line((35, "operating activities and other items:"))]  # fmt: skip
    assert find_tables(apple_like(gap)) == [(0, 1, 7)]


def test_long_row_name_after_a_single_row_keeps_the_top_row() -> None:
    """Ulta p7 shape: 1 row above the long name was lost (a table needs 2 rows)."""
    name = "Adjustments to reconcile net income to net cash provided by operating activities:"
    lines = [
        num_row("Net income", "347,051", "331,395", top=100),
        line((60, name), top=112),
        num_row("Depreciation and amortization", "57,949", "62,839", top=124, x=71),
        num_row("Non-cash lease expense", "75,478", "72,192", top=136, x=71),
    ]
    assert find_tables(lines) == [(0, 0, 4)]


@pytest.mark.parametrize(
    "gap",
    [
        pytest.param(["The following table shows the changes in the fair value of plan assets."],
                     id="sentence-with-full-stop"),
        pytest.param(["Changes in the fair value of the plan assets of the pension plans",
                      "and of the other postretirement benefit plans of the company and its",
                      "subsidiaries during the year were as shown in the table below:"],
                     id="three-long-lines"),
        pytest.param(["Fair value changes of the plan assets by type (in millions):"], id="unit"),
        pytest.param(["Item 8. Financial Statements and Supplementary Data of the company"],
                     id="item-heading"),
        pytest.param(["Changes in the fair value of plan assets during fiscal 2023:"], id="year"),
    ],
)  # fmt: skip
def test_two_different_tables_stay_separate(gap: list[str]) -> None:
    lines = apple_like([line((35, g)) for g in gap])
    assert len(find_tables(lines)) == 2


def test_tables_whose_columns_do_not_line_up_stay_separate() -> None:
    lines = apple_like([line((35, LONG_NAME))], right2=(250.0, 520.0))
    assert len(find_tables(lines)) == 2


def test_page_blocks_long_row_name_is_a_row_not_a_title() -> None:
    lines = [text_line("CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME", 80, bold=True)]
    lines += apple_like([line((35, LONG_NAME))])
    tables = [b for b in page_blocks(page_of(lines), 10.0) if b.kind == "table"]
    assert len(tables) == 1
    assert tables[0].title == "CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME"
    assert any(LONG_NAME in r for r in tables[0].rows)


# ---------- Q106: lost table titles ----------


def tables_of(lines: list[Line]) -> list[Block]:
    return [b for b in page_blocks(page_of(lines), 10.0) if b.kind == "table"]


def test_as_follows_sentence_with_two_numbers_is_still_a_title() -> None:
    """Microsoft: "... for less than 12 months and 12 months or greater were as follows:"."""
    sentence = "Debt investments with losses for less than 12 months and 12 months or greater:"
    lines = [text_line(sentence, 80)]
    lines += [line((300, "2022"), (400, "2021"), top=100)]
    lines += [num_row("U.S. government securities", "59,092", "2,210", top=112)]
    lines += [num_row("Corporate notes and bonds", "11,623", "102", top=124)]
    assert tables_of(lines)[0].title == sentence.rstrip(":") + ":"


def test_mostly_numbers_line_is_not_a_title() -> None:
    from filing_rag.ingest.blocks import mostly_numbers

    assert mostly_numbers("Total 1,234 5,678 9,012")
    assert not mostly_numbers("Debt investments for less than 12 months and 12 months or greater")


def jnj_like(above: list[Line]) -> list[Line]:
    """J&J earnings p8 shape: loose header lines above rows with no header of their own."""
    return above + [
        num_row("U.S.", "1,735", "1,557", top=200, x=190),
        num_row("International", "2,117", "2,029", top=212, x=190),
        num_row("Worldwide", "3,852", "3,586", top=224, x=190),
    ]


def test_title_above_loose_header_lines_is_found() -> None:
    lines = jnj_like([
        text_line("Supplementary Sales Data", 100, bold=True),
        text_line("(Unaudited; Dollars in Millions) FIRST QUARTER", 140),
        text_line("segment of business Consumer Health", 180),
    ])  # fmt: skip
    blocks = page_blocks(page_of(lines), 10.0)
    tables = [b for b in blocks if b.kind == "table"]
    assert len(tables) == 1
    t = tables[0]
    assert t.title == "Supplementary Sales Data"
    assert t.unit is not None and "Millions" in t.unit
    assert any("segment of business" in h for h in t.header)
    # the loose lines moved into the table: no text block keeps them (no double text)
    assert not any(b.kind == "text" and "segment of business" in b.text for b in blocks)
    assert "Supplementary Sales Data" in t.text and "segment of business" in t.text


def test_no_heading_above_means_no_title_and_no_change() -> None:
    lines = jnj_like([text_line("segment of business Consumer Health", 180)])
    blocks = page_blocks(page_of(lines), 10.0)
    assert [b.title for b in blocks if b.kind == "table"] == [None]
    assert any(b.kind == "text" and "segment of business" in b.text for b in blocks)


def test_a_paragraph_stops_the_title_search() -> None:
    lines = jnj_like([
        text_line("Supplementary Sales Data", 100, bold=True),
        text_line("Sales grew in all regions during the quarter, as the table shows.", 140),
        text_line("segment of business Consumer Health", 180),
    ])  # fmt: skip
    assert [b.title for b in tables_of(lines)] == [None]


def ulta_like(label_bold: bool) -> list[Line]:
    """Ulta p7 shape: title, unit, column header, a bold section label, then rows."""
    return [
        text_line("Consolidated Statements of Cash Flows", 60, bold=True),
        line((280, "(In thousands)"), top=72),
        line((300, "2023"), (400, "2022"), top=84),
        line((60, "Operating activities"), top=96, bold=label_bold),
        num_row("Net income", "347,051", "331,395", top=108),
        num_row("Depreciation and amortization", "57,949", "62,839", top=120),
    ]


def test_bold_section_label_under_a_column_header_is_in_the_table() -> None:
    lines = ulta_like(label_bold=True)
    assert find_tables(lines) == [(1, 3, 6)]
    t = tables_of(lines)[0]
    assert t.title == "Consolidated Statements of Cash Flows"
    assert t.unit == "In thousands"
    assert any("Operating activities" in r for r in t.rows)


def test_plain_short_label_is_not_taken_as_a_section_label() -> None:
    lines = ulta_like(label_bold=False)
    assert find_tables(lines) == [(4, 4, 6)]
