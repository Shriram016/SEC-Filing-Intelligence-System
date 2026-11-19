# Spec — Ingestion pipeline

**Status:** design approved (grilling 2026-11-04 → 2026-11-19). Not built.
**Milestones:** M0 (download), M1 (few companies), M2 (all 360 PDFs).
**Sources:** `docs/V3_GRILLING_LOG.md` Q3, Q20–Q25, Q38, Q39, Q49.

## 1. Purpose

Turn the 360 FinanceBench PDFs into searchable chunks with exact metadata. Ingestion is a batch job. It runs separately from answering.

## 2. Input and output

| | Value |
|---|---|
| Input | The 360 FinanceBench PDFs (269 10-K, 30 8-K, 27 10-Q, 29 earnings, 5 annual reports; 2015–2024) and the FinanceBench document list |
| Output | Chunks in the vector store, each with an embedding and metadata. A **document catalog** (one row per PDF) for the router coverage check |

## 3. Steps

1. **Download** (M0). Download each PDF once. Store a checksum per file. Reason: the PDFs are on company websites, and links can break.
2. **Read** the PDF with the chosen PDF reader (section 4).
3. **Find the period.** Read the real period dates from the cover page (for example "fiscal year ended September 24, 2022"). Do not trust the file name: FinanceBench names have errors (misspellings, mixed case, one duplicate).
4. **Split** along the document structure: sections and headings for text; one chunk per table.
5. **Label tables.** For each table: copy it exactly (numbers, rows, columns, units), then add a 1–2 sentence search label (company, period, unit, main row names). Store the table and its label as one chunk. Search uses the label; the answer step reads the exact table.
6. **Embed** each chunk with a free local embedding model.
7. **Store** chunks + metadata in the vector store. Update the document catalog.

## 4. Key decisions

| Decision | Choice | Ref |
|---|---|---|
| Corpus | The 360 FinanceBench PDFs only. No SEC HTML, no XBRL | Q3, ADR-0001 |
| PDF reader | Chosen at build time by a test on pages that **no FinanceBench question uses**, plus a user hand-check. FinanceBench evidence pages are never used (test leakage) | Q20, Q21 |
| Table labels | Yes, one label per table chunk | Q22 |
| Who writes labels | Code template, LLM, or both: decided at build time after looking at real tables | Q23 |
| Fiscal year | Period dates from the cover page, stored on every chunk | Q25 |
| Embedding model | Free local model (for example BGE family). Exact model at build time | Q38 |
| Vector store | Chosen at build time by a test: PostgreSQL + pgvector, Qdrant, or ChromaDB. Criteria: filter quality, built-in keyword search (for BM25 later), one database for logs + eval results, ease of deploy | Q39 |
| User uploads | None. The corpus is fixed | Q49 |

## 5. Chunk metadata (minimum)

`chunk_id`, `doc_name`, `company`, `doc_type` (10-K / 10-Q / 8-K / earnings / annual report), `fiscal_year`, `fiscal_quarter` (if any), `period_start`, `period_end`, `section`, `page`, `is_table`, `text`, `table_label` (tables only).

Exact field list is fixed in M1.

## 6. Rules

- **Idempotent:** safe to re-run. Same input → same chunks, no duplicates.
- **Bad file:** skip it, log it, continue. One bad PDF never stops the run.
- **Limits:** file size and type checks before reading.
- **No AI cost** for reading, splitting and embedding, unless LLM table labels win the Q23 test. Show the cost before that run.

## 7. Tests

- Unit: splitter, period parser, table label template, metadata builder.
- Ingestion tests: broken and huge sample PDFs are skipped and logged.
- Check: chunk count per document; every chunk has period dates; no duplicate `chunk_id`.

## 8. Open at build time

PDF reader; table label method; chunk sizes; very large tables; embedding model; vector store; real chunk count (estimate 100k–300k, not measured).
