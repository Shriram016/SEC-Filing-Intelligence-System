import json
from pathlib import Path

from filing_rag.router.catalog import CatalogDoc, DocCatalog


def _cat() -> DocCatalog:
    return DocCatalog(
        [
            CatalogDoc("APPLE_2021_10K", "Apple", "10-K", 2021),
            CatalogDoc("APPLE_2022_10K", "Apple", "10-K", 2022),
            CatalogDoc("APPLE_2023_10Q", "Apple", "10-Q", 2023, fiscal_quarter=2),
            CatalogDoc("FEDEX_2023_10K", "FedEx", "10-K", 2023),
            CatalogDoc("FEDEX_2023_annualreport", "FedEx", "annual report", 2023),
            CatalogDoc("COSTCO_2024_10K", "Costco", "10-K", 2024),
        ]
    )


def test_companies_sorted_unique() -> None:
    assert _cat().companies() == ["Apple", "Costco", "FedEx"]


def test_year_exists_gives_only_that_year() -> None:
    s = _cat().select(["Apple"], [2022])
    assert s.doc_names == ["APPLE_2022_10K"]
    assert s.covered


def test_year_missing_uses_next_year() -> None:
    s = _cat().select(["Costco"], [2023])
    assert s.doc_names == ["COSTCO_2024_10K"]
    assert s.covered


def test_never_previous_year() -> None:
    s = _cat().select(["Costco"], [2025])
    assert s.doc_names == []
    assert s.missing == [("Costco", 2025)]
    assert not s.covered


def test_both_missing_not_covered() -> None:
    s = _cat().select(["Apple"], [2019])
    assert not s.covered
    assert s.missing == [("Apple", 2019)]


def test_rule_b_takes_year_and_next() -> None:
    s = _cat().select(["Apple"], [2021], rule="B")
    assert s.doc_names == ["APPLE_2021_10K", "APPLE_2022_10K"]
    s_a = _cat().select(["Apple"], [2021], rule="A")
    assert s_a.doc_names == ["APPLE_2021_10K"]


def test_no_year_gives_all_company_documents() -> None:
    s = _cat().select(["Apple"])
    assert s.doc_names == ["APPLE_2021_10K", "APPLE_2022_10K", "APPLE_2023_10Q"]


def test_two_companies_two_years_union() -> None:
    s = _cat().select(["Apple", "FedEx"], [2022, 2023])
    # Apple 2022 → 2022; Apple 2023 → the 10-Q; FedEx 2022 → 2023 docs (Y+1); FedEx 2023 → same
    assert s.doc_names == [
        "APPLE_2022_10K",
        "APPLE_2023_10Q",
        "FEDEX_2023_10K",
        "FEDEX_2023_annualreport",
    ]
    assert s.covered


def test_doc_type_filter() -> None:
    s = _cat().select(["Apple"], [2023], doc_type="10-Q")
    assert s.doc_names == ["APPLE_2023_10Q"]
    s2 = _cat().select(["Apple"], [2022], doc_type="10-Q")
    # no 10-Q for 2022, the 2023 10-Q is Y+1
    assert s2.doc_names == ["APPLE_2023_10Q"]
    s3 = _cat().select(["Costco"], doc_type="8-K")
    assert not s3.covered
    assert s3.missing == [("Costco", None)]


def test_twin_documents_both_kept() -> None:
    s = _cat().select(["FedEx"], [2023])
    assert s.doc_names == ["FEDEX_2023_10K", "FEDEX_2023_annualreport"]


def test_no_company_means_no_filter() -> None:
    s = _cat().select([], [2022])
    assert s.doc_names is None
    assert s.covered


def test_unknown_company_not_covered() -> None:
    s = _cat().select(["Tesla"], [2022])
    assert not s.covered


def test_duplicates_in_input_are_ignored() -> None:
    s = _cat().select(["Apple", "Apple"], [2022, 2022])
    assert s.doc_names == ["APPLE_2022_10K"]
    assert s.missing == []


def test_load_skips_documents_not_ok(tmp_path: Path) -> None:
    rows = [
        {"doc_name": "A", "company": "X", "doc_type": "10-K", "fiscal_year": 2020, "status": "ok"},
        {
            "doc_name": "B",
            "company": "X",
            "doc_type": "8-K",
            "fiscal_year": 2020,
            "status": "skipped",
        },
    ]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    cat = DocCatalog.load(path)
    assert [d.doc_name for d in cat.docs] == ["A"]
    assert cat.doc_types() == ["10-K"]
