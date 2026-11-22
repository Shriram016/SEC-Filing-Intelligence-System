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
3. **Find the period.** `fiscal_year` from the document list; exact `period_end` / `report_date` from the cover page (for example "fiscal year ended September 24, 2022"); log mismatches. Do not trust the file name: FinanceBench names have errors (misspellings, mixed case, wrong or missing year, one duplicate).
4. **Split** along the document structure (Q93, Q94): sections and headings for text; one chunk per table (row groups if large).
5. **Label tables.** For each table: copy it exactly (numbers, rows, columns, units), then add a 1–2 sentence search label (company, period, unit, main row names). Store the table and its label as one chunk. Search uses the label; the answer step reads the exact table.
6. **Embed** each chunk with a free local embedding model.
7. **Store** chunks + metadata in the vector store. Update the document catalog.

## 4. Key decisions

| Decision | Choice | Ref |
|---|---|---|
| Corpus | The 360 FinanceBench PDFs only. No SEC HTML, no XBRL | Q3, ADR-0001 |
| PDF reader | **pdfplumber first.** Tested on pages that **no FinanceBench question uses** (locked pages ±1 excluded), plus a user hand-check. Fails if < 95% of checked table cells are correct (value, row, unit) → then test Docling. Portfolio shortcut: one reader, not a comparison | Q20, Q21, Q85 |
| Table format | **Layout text** from pdfplumber: the table is copied exactly, columns aligned by spaces; the model reads it. Not a structured table. M1a test: values 100%, correct column by position 96%. Portfolio shortcut: production systems usually store structured tables (own builder, Docling or a cloud service). Revisit if table questions score clearly lower than text questions on the dev set → test Docling on the same 77 cells | Q88 |
| Section detection | **One general logic for each document**, not one rule set per company. (1) Find the Item headings with flexible rules (spaces, dots, dashes, non-breaking spaces; skip the table of contents). (2) If few Items are found (own layout, e.g. Intel 2017+, MGM 2015–18, Exhibit 13 filings): use the nearest heading on the page. (3) Log documents with few sections for review. (4) A company or document rule only after a measured failure. Store `section` (Item, if found) and `subsection` (heading or note title). Reason: templates change between years (Intel, MGM, Verizon, PG&E, Walmart 2019); only 9/40 companies use the same PDF tool every year. Check: `experiments/structure/check_10k_items.py` | Q90 |
| M1b documents | ~20 documents that cover all 5 types and the difficult layouts (own layout, Exhibit 13, annual report, large 8-K, landscape earnings, 10-Q). Only documents no locked question uses. M1b finalises the logic; M2 runs it unchanged on all 360 | Q91 |
| Text chunks | **Structure-aware split** (Items / 8-K item codes / page headings; never across a section) + recursive split (paragraph → sentence) inside long sections; join short parts of the same section. Target ~350 tokens, max 480 (bge-base tokenizer). Overlap ~50 tokens only when a section is split. Header on each chunk: see *Embedded label* (Q99). Parent-child and other sizes only on measured need | Q93 |
| Table chunks | One table = one chunk (title, unit line, column headers, rows). > 480 tokens → row groups, each repeating title + headers; all parts share `table_id` so the answer step can fetch the full table. A table continued on the next page is joined first. Small tables stay separate | Q94 |
| Table cuts and titles | **(Q106, in use since 2026-11-22: collection `chunks_v2`.)** (1) **Same-page join:** two tables on one page are one table when the gap between them is 1–2 lines with no numbers, no full stop at the end and no heading; the number columns line up; and the units are the same (or the second has none). The gap lines become a row, never the title. (2) **Lost titles:** the reader looks a few lines higher for the title; the exact rule follows a hand check of the causes. A section heading (Item) is never a title. (3) **Strict over loose:** when a case is not clear, the table stays as it is. Reason: 33% of tables (9,780 of 29,808) had no title; 3 of 13 baseline search misses were one table cut into two. Measured: table Hit@5 0.61 → 0.71 (gold document), 0.57 → 0.61 (rule A); text unchanged | Q106 |
| Table labels | Yes, one label per table chunk | Q22 |
| Embedded label | **Company, type, period + section** ("Apple 10-K FY2019 › Item 8. Financial Statements") before the chunk text; tables add unit + column headers. Subsection and minor heading are **stored, not embedded** (`context` keeps the full path for display and citations). **Rule (Q105): the embedded text = label + everything in the text the answer step reads.** So the **table title is always embedded**: it is part of the table, not a label level (until Q105 it was dropped with `label_depth=section`, while the answer text kept it). The chunker counts the title in the 480-token budget. Reason: M1b hand-check (100 chunks): company/type/year 100%, section 94%, subsection and heading 85% each, and each fix round found new rare cases. A wrong label can mislead search; the benefit of the deep levels is not measured. Setting `label_depth` = `none` / `section` (default) / `full`; M1d measures all three on the dev set, and the deep levels come back only if `full` clearly wins | Q99 |
| Who writes labels | **Code template** (company, type, year, section, table title, unit, row names, column headers). LLM labels only if table questions score clearly lower on the dev set; cost estimate + approval first | Q23, Q95 |
| Period | `fiscal_year` = year stated in the document when found ("Fiscal 2023"), else the document list year; `list_fiscal_year` keeps the list value (Q97); exact `period_end` (10-K, 10-Q) / `report_date` (8-K) from cover-page patterns; earnings fallback = list year + name quarter, `period_source = estimated`; mismatches logged. Search uses the year as a **boost, not a hard filter** (fiscal ≠ calendar year; a 10-K holds 2–3 years) | Q25, Q96, Q97 |
| Embedding model | **bge-base-en-v1.5** (768 dims, fp16, local GPU). Query prefix: "Represent this sentence for searching relevant passages: ". M1a test: tie on Hit@5 with bge-m3 and Qwen3-0.6B (52.5–57.5%); bge-base is the fastest (210 chunks/s) and smallest (0.6 GB). Input limit 512 tokens → chunks stay below 512 tokens; the code logs any chunk that is cut. Keyword search (if needed) = separate BM25 index | Q38, Q87, Q89 |
| Vector store | **Qdrant server in Docker** (`docker-compose.yml`, `localhost:6333`) (filters applied during search, built-in sparse/BM25 hybrid, snapshots). pgvector dropped. Chats, logs and eval results need a second database (decided at the API milestone) | Q39, Q86, Q92 |
| User uploads | None. The corpus is fixed | Q49 |

## 5. Chunk metadata (minimum)

`chunk_id`, `doc_name`, `company`, `doc_type` (10-K / 10-Q / 8-K / earnings / annual report), `fiscal_year`, `list_fiscal_year`, `fiscal_quarter` (if any), `period_end`, `report_date` (8-K), `period_source` (cover / estimated), `section`, `subsection`, `heading`, `context` (full path), `page`, `is_table`, `table_id` (tables only), `table_label` (tables only), `text`.

Exact field list is fixed in M1.

## 6. Rules

- **Idempotent:** safe to re-run. Same input → same chunks, no duplicates. `chunk_id` = hash of document + page + text; Qdrant point id = uuid5(`chunk_id`). A re-run deletes all points of the document, then upserts the new ones (so chunks that a code change no longer makes are removed).
- **Skip unchanged documents:** a document is skipped when its PDF `sha256`, the settings fingerprint (chunk sizes, label depth, model, `INGEST_VERSION`) and its Qdrant point count are unchanged. `--force` redoes all. Progress is saved after each document, so a stopped run continues where it stopped.
- **Parallel reading:** `--workers N` reads PDFs in N processes (CPU); embedding and storing stay in the main process (GPU). Full run: `uv run --group embed python -m filing_rag.ingest --all --workers 6`.
- **Portfolio shortcut:** delete + upsert is two steps, so a document is briefly missing during its re-run. Production: build a new collection, check it, then switch a Qdrant alias in one step (at the API milestone).
- **Bad file:** skip it, log it, continue. One bad PDF never stops the run.
- **Limits:** file size and type checks before reading.
- **No AI cost** for reading, splitting and embedding, unless LLM table labels are needed (Q95). Show the cost before that run.

## 7. Tests

- Unit: splitter, period parser, table label template, metadata builder.
- Ingestion tests: broken and huge sample PDFs are skipped and logged.
- Check: chunk count per document; every chunk has period dates; no duplicate `chunk_id`.

## 8. Known data issues (found in M1a, 2026-11-19)

| Issue | Detail | Plan |
|---|---|---|
| 2 broken PDFs in the FinanceBench source | `INTEL_2023_8K_dated-2023-02-10`: new download from `doc_link` works (214 pages) → stored in `data/financebench/pdf_overrides/`, sha256 in `eval/pdf_overrides.json`. `INTEL_2023_8K_dated-2023-08-16`: the `doc_link` copy is also truncated → **unrecoverable**, skipped and logged (M1b, 2026-11-20). No locked question uses them | Done |
| Wrong `doc_type` in the document list | `LOCKHEEDMARTIN_2023Q2_10Q` is an earnings press release, not a 10-Q (M1b) | 10-Q without "quarterly period ended" → earnings period rule; warning logged |
| Wrong `doc_type`: earnings vs 8-K | `PG_E_2023_EARNINGS-dated-2023-06-01` (106 pages) is an 8-K with debt exhibits (indenture, notary pages) (M1b) | Kept as listed; sections come from exhibit headings; logged here |
| Document list year ≠ fiscal year in the text | `ULTABEAUTY_2024Q1_EARNINGS` = "First Quarter Fiscal 2023, ended April 29, 2023"; list says 2024 (M1b) | Use the year stated in the document; keep `list_fiscal_year`; log a warning (Q97) |
| 8-K cover date ≠ file name date | `INTEL_2023_8K_dated-2023-02-10`: event date Feb 7, file name Feb 10 (filing date) | Store the cover date (event date); log the difference |
| Printed page number ≠ PDF page | Example: Walmart annual report PDF page 56 shows "54" | Store the PDF page index on every chunk. Never use the printed number |
| Short 8-Ks | Many 8-Ks are a cover page plus short notices, with no tables | Expect very few chunks per 8-K |
| `$` printed as `S` | Some fonts (ULTA earnings) map the dollar sign to "S" | Check in the reader test; normalise if needed |

## 9. Open at build time

Real chunk count (estimate 100k–300k, not measured).

## 10. Document structure by type (checked 2026-11-20)

Scripts: `experiments/structure/check_10k_items.py`, `check_other_types.py`. Corpus: 360 PDFs, 40 companies; 93% SEC filings printed from HTML, ~27 designed documents or slides, 0 scanned.

| Type | Docs | Structure | Found by simple rules | Section logic |
|---|---|---|---|---|
| 10-K | 269 | Items 1–16 (SEC rules); notes inside Item 8 | All key Items: 196/269 (first rules; format fixes pending). Own layout: Intel 2017+, MGM 2015–18; content in Exhibit 13: CVS, older Verizon | Items → fallback to page headings |
| 10-Q | 27 | Part I (Items 1–4), Part II (Items 1, 1A, 2–6) | Items 1–4: 24/27 (misses: Lockheed 2023 Q1/Q2, Foot Locker Q3) | Same as 10-K |
| 8-K | 28 (+2 broken) | Item codes (e.g. 2.02, 5.02, 8.01, 9.01) + attached exhibits | Item code: 28/28. Large 8-Ks (27–248 pages) are mostly exhibits | `section` = item code; `subsection` = exhibit heading |
| Earnings | 29 | No legal structure. Common parts: income statement (26), outlook (22), non-GAAP reconciliation (21), balance sheet (19) | — | Page headings only |
| Annual report | 5 | Designed front part (letter, highlights) + a full 10-K (5/5) | 10-K part: Items found in all 5 | Front part: page headings + two-column fix; then 10-K logic |

Rule (Q90): one general logic for all types: try Items first, fall back to page headings, log documents with few sections.
