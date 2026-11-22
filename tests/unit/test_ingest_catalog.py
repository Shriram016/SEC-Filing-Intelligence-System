import json
from pathlib import Path

import pytest

from filing_rag.config import Settings
from filing_rag.ingest.catalog import (
    CatalogRow,
    DocumentError,
    check_pdf_file,
    load_document_list,
    normalise_doc_type,
    resolve_pdf,
    write_catalog,
)


def write_doc_list(settings: Settings, rows: list[dict[str, object]]) -> None:
    settings.financebench_dir.mkdir(parents=True, exist_ok=True)
    with (settings.financebench_dir / "document_information.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def row(name: str, doc_type: str = "10k", year: int = 2019) -> dict[str, object]:
    return {"doc_name": name, "company": "Co", "doc_type": doc_type, "doc_period": year}


def test_normalise_doc_type() -> None:
    assert normalise_doc_type("10k") == "10-K"
    assert normalise_doc_type("Earnings") == "earnings"
    assert normalise_doc_type("10k_annualreport") == "annual report"
    with pytest.raises(ValueError):
        normalise_doc_type("20-F")


def test_load_document_list_first_row_wins(settings: Settings) -> None:
    write_doc_list(settings, [row("A_2019_10K"), row("A_2019_10K", year=2020), row("B", "8k")])
    docs = load_document_list(settings)
    assert set(docs) == {"A_2019_10K", "B"}
    assert docs["A_2019_10K"].fiscal_year == 2019
    assert docs["B"].doc_type == "8-K"


def test_resolve_pdf_prefers_override(settings: Settings) -> None:
    path, source = resolve_pdf(settings, "X")
    assert source == "financebench" and path == settings.pdf_dir / "X.pdf"
    settings.pdf_override_dir.mkdir(parents=True)
    (settings.pdf_override_dir / "X.pdf").write_bytes(b"%PDF-1.7")
    path, source = resolve_pdf(settings, "X")
    assert source == "override" and path.parent == settings.pdf_override_dir


def test_check_pdf_file(tmp_path: Path) -> None:
    with pytest.raises(DocumentError, match="not found"):
        check_pdf_file(tmp_path / "missing.pdf", 100)
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(DocumentError, match="empty"):
        check_pdf_file(empty, 100)
    html = tmp_path / "page.pdf"
    html.write_bytes(b"<html>not a pdf</html>")
    with pytest.raises(DocumentError, match="not a PDF"):
        check_pdf_file(html, 100)
    big = tmp_path / "big.pdf"
    big.write_bytes(b"%PDF-" + b"0" * 200)
    with pytest.raises(DocumentError, match="too large"):
        check_pdf_file(big, 100)
    check_pdf_file(big, 1000)  # no error


def test_write_catalog_merges_rows(settings: Settings) -> None:
    a = CatalogRow("A", "Co", "10-K", 2019, "IT", status="ok", chunks=3)
    b = CatalogRow("B", "Co", "8-K", 2023, "IT", status="skipped")
    write_catalog(settings, [a, b])
    a.chunks = 5
    path = write_catalog(settings, [a])
    data = {r["doc_name"]: r for r in json.loads(path.read_text())}
    assert data["A"]["chunks"] == 5
    assert data["B"]["status"] == "skipped"
