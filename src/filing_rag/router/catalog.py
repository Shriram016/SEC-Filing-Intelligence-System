"""Document selection for the router (docs/v3/router.md §2.2, Q104).

The router LLM gives only the companies, years and doc type that the question names. This module
chooses the **documents** to search, from the ingestion catalog (`catalog.json` in the ingest
folder, the same
`fiscal_year` that is stored on every chunk):

- year Y → documents with `fiscal_year = Y`; if none, `fiscal_year = Y+1` (option A). The next
  filing holds Y as its prior-year column. Never Y-1: an older filing cannot hold a later year.
- option B (measured alternative): always Y and Y+1.
- no year → all documents of the company; `doc_type` set → only that type.
- no company → no document filter (`None`): search everything.

Production note: the catalog would be a database table; here it is the ingestion JSON file.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from filing_rag.config import Settings

YearRule = Literal["A", "B"]


@dataclass(frozen=True)
class CatalogDoc:
    doc_name: str
    company: str
    doc_type: str
    fiscal_year: int
    fiscal_quarter: int | None = None
    period_end: str | None = None


@dataclass(frozen=True)
class Selection:
    """Result of a document selection.

    `doc_names is None` means "no filter" (no company named). An empty list never comes back
    for a covered question; `missing` lists the (company, year) pairs with no document.
    """

    doc_names: list[str] | None
    missing: list[tuple[str, int | None]] = field(default_factory=list)

    @property
    def covered(self) -> bool:
        return not self.missing


class DocCatalog:
    def __init__(self, docs: Iterable[CatalogDoc]) -> None:
        self.docs = sorted(docs, key=lambda d: d.doc_name)
        self._by_company: dict[str, list[CatalogDoc]] = {}
        for d in self.docs:
            self._by_company.setdefault(d.company, []).append(d)

    @classmethod
    def from_rows(cls, rows: Iterable[dict[str, Any]]) -> DocCatalog:
        """Build from ingestion catalog rows. Only documents with status `ok` are searchable."""
        return cls(
            CatalogDoc(
                doc_name=str(r["doc_name"]),
                company=str(r["company"]),
                doc_type=str(r["doc_type"]),
                fiscal_year=int(r["fiscal_year"]),
                fiscal_quarter=r.get("fiscal_quarter"),
                period_end=r.get("period_end"),
            )
            for r in rows
            if r.get("status", "ok") == "ok"
        )

    @classmethod
    def load(cls, path: Path) -> DocCatalog:
        return cls.from_rows(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def from_settings(cls, settings: Settings) -> DocCatalog:
        return cls.load(settings.ingest_dir / "catalog.json")

    def companies(self) -> list[str]:
        """The company names in the collection (the router's enum)."""
        return sorted(self._by_company)

    def doc_types(self) -> list[str]:
        return sorted({d.doc_type for d in self.docs})

    def documents(self, company: str, doc_type: str | None = None) -> list[CatalogDoc]:
        docs = self._by_company.get(company, [])
        return [d for d in docs if doc_type is None or d.doc_type == doc_type]

    def _for_year(self, docs: Sequence[CatalogDoc], year: int, rule: YearRule) -> list[CatalogDoc]:
        same = [d for d in docs if d.fiscal_year == year]
        nxt = [d for d in docs if d.fiscal_year == year + 1]
        if rule == "B":
            return same + nxt
        return same or nxt

    def select(
        self,
        companies: Sequence[str],
        years: Sequence[int] = (),
        doc_type: str | None = None,
        rule: YearRule = "A",
    ) -> Selection:
        """Rule A: year Y, else Y+1. A named doc type comes first; when it has no document for
        the company (and year), all types are used ("annual report" = the 10-K for most)."""
        if not companies:
            return Selection(doc_names=None)
        chosen: set[str] = set()
        missing: list[tuple[str, int | None]] = []
        for company in dict.fromkeys(companies):
            docs = self.documents(company, doc_type)
            every = self.documents(company)
            if not years:
                docs = docs or every  # named type missing → all types
                if docs:
                    chosen.update(d.doc_name for d in docs)
                else:
                    missing.append((company, None))
                continue
            for year in dict.fromkeys(years):
                picked = self._for_year(docs, year, rule) or self._for_year(every, year, rule)
                if picked:
                    chosen.update(d.doc_name for d in picked)
                else:
                    missing.append((company, year))
        return Selection(doc_names=sorted(chosen), missing=missing)
