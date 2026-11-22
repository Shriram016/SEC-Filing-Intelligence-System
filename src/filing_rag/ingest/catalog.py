"""Document catalog: one row per PDF, built from the FinanceBench document list.

Company, type and year come from the document list, not from the file name (Q90): file names
have spelling errors, mixed case, wrong or missing years. A PDF in the override folder replaces
a broken file from the pinned commit (see `eval/pdf_overrides.json`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from filing_rag.config import Settings
from filing_rag.data.financebench import DOC_INFO_FILENAME, read_jsonl, sha256_file

DOC_TYPES = {
    "10k": "10-K",
    "10q": "10-Q",
    "8k": "8-K",
    "earnings": "earnings",
    "10k_annualreport": "annual report",
}
PDF_MAGIC = b"%PDF-"


class DocumentError(Exception):
    """A document cannot be ingested. The pipeline skips it and logs the reason."""


@dataclass(frozen=True)
class DocInfo:
    doc_name: str
    company: str
    doc_type: str  # one of DOC_TYPES values
    fiscal_year: int
    sector: str
    doc_link: str


@dataclass
class CatalogRow:
    doc_name: str
    company: str
    doc_type: str
    fiscal_year: int
    sector: str
    status: str = "pending"  # ok | skipped
    source: str = "financebench"  # financebench | override
    pdf_path: str = ""
    sha256: str = ""
    pages: int = 0
    list_fiscal_year: int = 0
    fiscal_quarter: int | None = None
    period_end: str | None = None
    report_date: str | None = None
    period_source: str | None = None
    sections_found: int = 0
    toc_pages: list[int] = field(default_factory=list)
    chunks: int = 0
    table_chunks: int = 0
    rejected_headings: int = 0
    label_flags: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    ingest_fingerprint: str = ""  # settings fingerprint of the run that made the chunks

    @classmethod
    def from_info(cls, info: DocInfo) -> CatalogRow:
        return cls(
            doc_name=info.doc_name,
            company=info.company,
            doc_type=info.doc_type,
            fiscal_year=info.fiscal_year,
            sector=info.sector,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalise_doc_type(raw: str) -> str:
    key = raw.strip().lower()
    if key not in DOC_TYPES:
        raise ValueError(f"unknown doc_type: {raw!r}")
    return DOC_TYPES[key]


def load_document_list(settings: Settings) -> dict[str, DocInfo]:
    """Read the document list. The first row wins for a duplicate name (FOOTLOCKER, see M0)."""
    rows = read_jsonl(settings.financebench_dir / DOC_INFO_FILENAME)
    docs: dict[str, DocInfo] = {}
    for r in rows:
        name = str(r["doc_name"])
        if name in docs:
            continue
        docs[name] = DocInfo(
            doc_name=name,
            company=str(r["company"]),
            doc_type=normalise_doc_type(str(r["doc_type"])),
            fiscal_year=int(r["doc_period"]),
            sector=str(r.get("gics_sector", "")),
            doc_link=str(r.get("doc_link", "")),
        )
    return docs


def resolve_pdf(settings: Settings, doc_name: str) -> tuple[Path, str]:
    """Return (path, source). An override replaces the pinned file."""
    override = settings.pdf_override_dir / f"{doc_name}.pdf"
    if override.exists():
        return override, "override"
    return settings.pdf_dir / f"{doc_name}.pdf", "financebench"


def check_pdf_file(path: Path, max_bytes: int) -> None:
    """Size and type checks before any parsing (spec §6, Limits)."""
    if not path.exists():
        raise DocumentError(f"file not found: {path}")
    size = path.stat().st_size
    if size == 0:
        raise DocumentError("empty file")
    if size > max_bytes:
        raise DocumentError(f"file too large: {size} bytes > {max_bytes}")
    with path.open("rb") as f:
        if f.read(len(PDF_MAGIC)) != PDF_MAGIC:
            raise DocumentError("not a PDF (bad header)")


def file_checksum(path: Path) -> str:
    return sha256_file(path)


def write_catalog(settings: Settings, rows: list[CatalogRow]) -> Path:
    """Merge rows into the catalog file (one row per document; a re-run replaces the row)."""
    path = settings.ingest_dir / "catalog.json"
    existing: dict[str, Any] = {}
    if path.exists():
        existing = {r["doc_name"]: r for r in json.loads(path.read_text(encoding="utf-8"))}
    for row in rows:
        existing[row.doc_name] = row.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [existing[k] for k in sorted(existing)]
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return path
