from datetime import date

from filing_rag.ingest.period import find_period, parse_date


def test_parse_date_variants() -> None:
    assert parse_date("ended September 24, 2022") == date(2022, 9, 24)
    assert parse_date("ENDED JANUARY 31,2023") == date(2023, 1, 31)
    assert parse_date("Sept. 3 2021") == date(2021, 9, 3)
    assert parse_date("no date here") is None
    assert parse_date("February 30, 2023") is None  # invalid day


def test_10k_cover_date() -> None:
    p = find_period(
        "10-K",
        "APPLE_2019_10K",
        2019,
        "FORM 10-K\n(Mark One)\nANNUAL REPORT ... For the fiscal year ended September 28, 2019",
    )
    assert p.period_end == date(2019, 9, 28)
    assert p.source == "cover"
    assert p.warnings == []


def test_10k_year_mismatch_is_a_warning() -> None:
    p = find_period("10-K", "X_2020_10K", 2020, "For the fiscal year ended December 31, 2019")
    assert p.period_end == date(2019, 12, 31)
    assert p.fiscal_year == 2020  # list year is kept
    assert any("not in document list year" in w for w in p.warnings)


def test_10k_without_date() -> None:
    p = find_period("10-K", "X_2020_10K", 2020, "nothing useful")
    assert p.period_end is None
    assert p.source == "estimated"
    assert p.warnings


def test_10q_cover_and_name_quarter() -> None:
    p = find_period("10-Q", "APPLE_2023Q3_10Q", 2023, "For the quarterly period ended July 1, 2023")
    assert p.period_end == date(2023, 7, 1)
    assert p.fiscal_quarter == 3


def test_10q_that_is_an_earnings_release_uses_the_earnings_rule() -> None:
    text = "Lockheed Martin Reports Second Quarter 2023 Financial Results ... ended June 25, 2023"
    p = find_period("10-Q", "LOCKHEEDMARTIN_2023Q2_10Q", 2023, text)
    assert p.period_end == date(2023, 6, 25)
    assert p.fiscal_quarter == 2
    assert any("earnings rule used" in w for w in p.warnings)


def test_8k_date_after_and_before_label() -> None:
    after = "Date of Report (Date of earliest event reported): February 7, 2023"
    p = find_period("8-K", "INTEL_2023_8K_dated-2023-02-10", 2023, after)
    assert p.report_date == date(2023, 2, 7)
    assert any("differs from file name" in w for w in p.warnings)
    before = "May 25, 2023\nDate of Report (Date of earliest event reported)"
    p2 = find_period("8-K", "LM_2023_8K_dated-2023-05-25", 2023, before)
    assert p2.report_date == date(2023, 5, 25)
    assert p2.warnings == []


def test_8k_falls_back_to_file_name_date() -> None:
    p = find_period("8-K", "MCDONALDS_8K_dated-2023-01-06", 2023, "no cover date")
    assert p.report_date == date(2023, 1, 6)
    assert p.source == "name"


def test_earnings_cover_and_year_mismatch() -> None:
    text = (
        "Ulta Beauty Announces First Quarter Fiscal 2023 Results ... results for the "
        "thirteen-week period (first quarter) ended April 29, 2023."
    )
    p = find_period("earnings", "ULTABEAUTY_2024Q1_EARNINGS", 2024, text)
    assert p.period_end == date(2023, 4, 29)
    assert p.fiscal_quarter == 1
    assert any("differs from document list" in w for w in p.warnings)
    assert p.fiscal_year == 2023  # the year in the document wins (Q97)
    assert p.list_fiscal_year == 2024


def test_earnings_without_end_date_is_estimated() -> None:
    text = "FOR IMMEDIATE RELEASE 2023 First-Quarter reported sales growth of 5.6%"
    p = find_period("earnings", "JOHNSON_JOHNSON_2023Q1_EARNINGS", 2023, text)
    assert p.period_end is None
    assert p.source == "estimated"
    assert p.fiscal_quarter == 1
    assert not any("differs from document list" in w for w in p.warnings)


def test_annual_report_finds_the_10k_cover_inside() -> None:
    text = (
        "Dear shareholders ... (long letter) ... FORM 10-K For the fiscal year ended May 31, 2023"
    )
    p = find_period("annual report", "FEDEX_2023_annualreport", 2023, text)
    assert p.period_end == date(2023, 5, 31)
