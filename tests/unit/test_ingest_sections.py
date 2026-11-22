from filing_rag.ingest.sections import SectionTracker, is_toc_page, match_item, match_item_8k


def test_match_item_flexible_formats() -> None:
    assert match_item("Item 7. Management's Discussion") == ("7", "Management's Discussion")
    assert match_item("ITEM 1A—RISK FACTORS") == ("1A", "RISK FACTORS")
    assert match_item("Item 2.Properties") == ("2", "Properties")
    assert match_item("Item\xa01B. Unresolved Staff Comments") == (
        "1B",
        "Unresolved Staff Comments",
    )
    assert match_item("Item 8") == ("8", "")


def test_match_item_rejects_prose_and_8k_codes() -> None:
    assert match_item("Item 7 of this report discusses") is None
    assert match_item("Item 2.02 Results of Operations") is None
    assert match_item("Item 42. Not an item") is None
    prose = "Item 1A. Risk Factors in this Form 10-Q and Part I, Item 1A of the 2020 Form 10-K"
    assert match_item(prose) is None
    assert match_item_8k("Item 2.02 Results of Operations and Financial Condition") == (
        "2.02",
        "Results of Operations and Financial Condition",
    )


def test_toc_page_detected() -> None:
    toc = [f"Item {n}. Something {p}" for n, p in [("1", 3), ("1A", 8), ("2", 16), ("3", 17),
                                                   ("7", 20), ("8", 30)]]  # fmt: skip
    assert is_toc_page(["Table of Contents", *toc])


def test_short_items_on_one_page_are_not_a_toc() -> None:
    # CVS p40: Items 7A, 8, 9, 9A, 9B on one page, each "incorporated by reference" (no pages);
    # the real page has 32% short lines
    lines = [
        "Item 7A. Quantitative and Qualitative Disclosures about Market Risk",
        "The information is incorporated by reference to our Annual Report.",
        "The information required by this item is included in the section of our Annual Report",
        "to Stockholders for the fiscal year ended December 31, 2017, which is filed as an exhibit",
        "Item 8. Financial Statements and Supplementary Data",
        "The financial statements and notes required by this item are incorporated by reference",
        "to the pages of our Annual Report to Stockholders listed in the index at Item 15 below,",
        "Item 9. Changes in and Disagreements with Accountants",
        "Item 9A. Controls and Procedures",
        "Item 9B. Other Information",
    ]
    assert not is_toc_page(lines)


def test_note_index_is_a_toc() -> None:
    lines = [f"Note {i}: Topic number {i} {70 + i}" for i in range(1, 9)]
    assert is_toc_page(lines)


def test_tracker_10k_items_notes_and_headings() -> None:
    t = SectionTracker("10-K")
    t.update("Item 8. Financial Statements and Supplementary Data", 1)
    assert t.section == "Item 8. Financial Statements and Supplementary Data"
    t.update("Note 12 – Income Taxes", 2)
    assert t.subsection == "Note 12 – Income Taxes"
    t.update("Unrecognized Tax Benefits", 2)
    assert t.heading == "Unrecognized Tax Benefits"
    t.update("Item 9A. Controls and Procedures", 1)
    assert t.subsection is None and t.heading is None
    assert t.items_found == {"8", "9A"}


def test_tracker_10q_part_prefix() -> None:
    t = SectionTracker("10-Q")
    t.update("PART II — OTHER INFORMATION", 1)
    t.update("Item 1A. Risk Factors", 1)
    assert t.section == "Part II, Item 1A. Risk Factors"


def test_tracker_8k_items_and_exhibits() -> None:
    t = SectionTracker("8-K")
    t.update("Item 2.02 Results of Operations and Financial Condition", 1)
    assert t.section == "Item 2.02 Results of Operations and Financial Condition"
    t.update("Exhibit 99.1", 1)
    assert t.section == "Exhibit 99.1"
    t.update("PRESS RELEASE", 1)
    assert t.subsection == "PRESS RELEASE"
    assert t.items_found == {"2.02"}


def test_tracker_without_items_uses_headings() -> None:
    t = SectionTracker("earnings")
    t.update("FINANCIAL HIGHLIGHTS", 1)
    assert t.section is None and t.subsection == "FINANCIAL HIGHLIGHTS"


def test_backwards_item_is_rejected_but_part_ii_restarts() -> None:
    t = SectionTracker("10-K")
    t.update("Item 8. Financial Statements", 1)
    t.update("Item 3. Legal Proceedings", 1)  # a cross-reference later in the document
    assert t.section == "Item 8. Financial Statements"
    assert t.rejected and "backwards" in t.rejected[0]
    q = SectionTracker("10-Q")
    q.update("PART I", 1)
    q.update("Item 4. Controls and Procedures", 1)
    q.update("PART II", 1)
    q.update("Item 1. Legal Proceedings", 1)
    assert q.section == "Part II, Item 1. Legal Proceedings"
    assert q.rejected == []


def test_note_outside_financial_statements_is_rejected() -> None:
    t = SectionTracker("10-K")
    t.update("Item 7. Management's Discussion", 1)
    t.update("Note 12 – Income Taxes", 1)
    assert t.subsection is None
    assert "note outside" in t.rejected[0]
    t.update("Item 8. Financial Statements", 1)
    t.update("Note 12 – Income Taxes", 1)
    assert t.subsection == "Note 12 – Income Taxes"


def test_bad_heading_shape_is_left_out() -> None:
    t = SectionTracker("earnings")
    t.update("Revenue", 1)
    t.update("Net periodic benefit cost 251 288 268", 2)
    assert t.subsection == "Revenue" and t.heading is None
    assert "bad heading shape" in t.rejected[0]


def test_row_like() -> None:
    from filing_rag.ingest.sections import row_like

    assert row_like("Service cost $ 251 $ 288")
    assert not row_like("Future payments as of September 28, 2019")


def test_noise_is_never_a_heading() -> None:
    from filing_rag.ingest.sections import heading_shape_ok, is_noise

    for t in [
        "Registrant’s telephone number, including area code: 425-313-8100",
        "CUSIP [•]",
        "FOR IMMEDIATE RELEASE FOR MORE INFORMATION CONTACT",
        "COMPUTERSHARE TRUST COMPANY, NATIONAL",
        "INTEL CORPORATION",
        "S   P   A   F   -Y   S   F   A",
        "of operations, financial position and liquidity",
        "SECURITIES AND EXCHANGE COMMISSION",
    ]:
        assert is_noise(t), t
        assert not heading_shape_ok(t), t
    for t in ["LIQUIDITY AND CAPITAL RESOURCES", "Note 6 – Contract Liabilities", "Revenue"]:
        assert not is_noise(t), t


def test_exhibit_heading_is_a_whole_line() -> None:
    from filing_rag.ingest.sections import EXHIBIT_RE

    assert EXHIBIT_RE.match("Exhibit 99.1")
    assert EXHIBIT_RE.match("EXHIBIT 13")
    assert EXHIBIT_RE.match("Exhibit 10.1 – Credit Agreement")
    assert not EXHIBIT_RE.match("Exhibit 4.1)")
    assert not EXHIBIT_RE.match("Exhibit 4.1 (incorporated by reference to the Form 8-K)")


def test_8k_items_in_documents_listed_as_earnings() -> None:
    t = SectionTracker("earnings")
    t.update("Item 8.01 Other Events", 1)
    assert t.section == "Item 8.01 Other Events"


def test_long_item_titles_and_bracket_notes_are_accepted() -> None:
    costco = (
        "Item 7—Management's Discussion and Analysis of Financial Conditions and Results of "
        "Operations (amounts in millions, except per share,"
    )
    got = match_item(costco)
    assert got is not None and got[0] == "7"
    assert got[1].endswith("Results of Operations")
    item_502 = (
        "Item 5.02. Departure of Directors or Certain Officers; Election of Directors; "
        "Appointment of Certain Officers; Compensatory Arrangements of Certain Officers."
    )
    assert match_item_8k(item_502) is not None


def test_exhibit_heading_with_footnote_number() -> None:
    t = SectionTracker("10-K")
    t.update("Item 16. Form 10-K Summary", 1)
    t.update("Exhibit 10.5(40)", 1)
    assert t.section == "Exhibit 10.5"
    t.update("Exhibit 4.1)", 1)  # a list entry, not a heading
    assert t.section == "Exhibit 10.5"


def test_item_followed_by_prose_is_not_a_heading() -> None:
    assert match_item("Item 9A. , management excluded from its assessment of the controls") is None
    assert match_item("Item 9A, management excluded from its assessment") is None
    assert match_item("Item 9A. Controls and Procedures") == ("9A", "Controls and Procedures")


def test_item_with_punctuation_or_no_letters_is_prose() -> None:
    assert match_item("Item 1. , “Business” of our 2019 Form 10-K") is None
    assert match_item("Item 8. )") is None
    assert match_item("Item 8") == ("8", "")


def test_items_on_the_cover_page_and_inside_exhibits_are_rejected() -> None:
    t = SectionTracker("10-K")
    t.update("Item 8. Financial Statements and Supplementary Data", 1, page=1)  # web link line
    assert t.section is None
    t.update("Item 1. Business", 1, page=4)
    t.update("Item 15. Exhibits and Financial Statement Schedules", 1, page=90)
    t.update("Exhibit 13", 1, page=100)
    t.update("Item 2. Management's Discussion and Analysis", 1, page=120)  # inside the exhibit
    assert t.section == "Exhibit 13"
    assert any("exhibit" in r for r in t.rejected)


def test_exhibit_before_the_last_item_does_not_block_items() -> None:
    t = SectionTracker("10-K")
    t.update("Exhibit 13", 1, page=2)  # a cover mention of the annual report exhibit
    t.update("Item 1. Business", 1, page=5)
    assert t.section == "Item 1. Business"


def test_toc_without_page_numbers_is_found() -> None:
    toc = [
        "Contents",
        "PART I",
        "ITEM 1. BUSINESS",
        "Regulatory Environment",
        "ITEM 1A. RISK FACTORS",
        "ITEM 2. PROPERTIES",
        "ITEM 3. LEGAL PROCEEDINGS",
        "PART II",
        "ITEM 5. MARKET FOR EQUITY",
        "ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS",
    ]
    assert is_toc_page(toc)
    ref = (
        "The information required by this item is incorporated by reference to our proxy "
        "statement for the annual meeting."
    )
    body = [
        "ITEM 10. DIRECTORS, EXECUTIVE OFFICERS AND CORPORATE GOVERNANCE",
        ref,
        "ITEM 11. EXECUTIVE COMPENSATION",
        ref,
        "ITEM 12. SECURITY OWNERSHIP",
        ref,
        "ITEM 13. CERTAIN RELATIONSHIPS",
        "ITEM 14. PRINCIPAL ACCOUNTANT FEES",
        ref,
    ]
    assert not is_toc_page(body)
