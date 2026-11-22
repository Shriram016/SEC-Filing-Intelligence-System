# Full ingestion: all 360 documents (2026-11-20)

Command: `uv run --group embed python -m filing_rag.ingest --all --workers 6` (6 parallel PDF readers, GPU embedding).
Qdrant collection `chunks` (clean start), `label_depth = section`. No AI cost.

| | Run 1 | Run 2 (after fixes) |
|---|---|---|
| Time | 38 min | ~38 min |
| Documents OK | 358 / 360 | **359 / 360** |
| Skipped | Intel 8-K 2023-08-16 (broken PDF, known); McDonald's Q4 2022 earnings (crash) | Intel 8-K 2023-08-16 only |
| Chunks (tables) | 189,671 (33,181) | 189,504 (33,177) |
| Tokens median / max / over 480 | 239 / 480 / 0 | 239 / 480 / 0 |
| Duplicate chunk IDs | 0 | 0 |
| `item_backwards` flags | 10,064 | **1,181** |
| Chunks without a section | 13,042 | 13,377 |
| Qdrant points | 189,671 | 189,504 |

## Causes found in run 1 and fixes (general rules, not per document)

| Cause | Documents | Fix |
|---|---|---|
| Table of contents without page numbers not detected | PG&E 10-Ks, Pfizer 10-Q, Intel 2021 index | 5+ Items and ≥ 85% short lines (≤ 14 words) = TOC. Probe: TOC pages 93–100% short lines, body pages with 5 Items ≤ 65% (`toc_probe.py`) |
| Prose after "Item N" taken as a section ("Item 1. , “Business” of our …", "Item 8. , Financial Statements … of this Annual Report", "Item 8. )") | Pfizer, Best Buy, Kraft Heinz, Netflix, PG&E | A title that starts with `, ; : )` or has no letters is prose |
| Bare "Item 8" at the end of a wrapped sentence | PG&E, Microsoft | A bare Item line needs heading style (bold, capitals or larger text) |
| Web-link line "Item 8. …" on the cover page | Activision | Items on page 1 of a 10-K / 10-Q are ignored |
| Item lists inside attached exhibits (annual report in Exhibit 13) | Pfizer, Walmart | After Item 15/16 and an Exhibit heading, Item lines are ignored |
| Crash: a "word" without spaces longer than a chunk (1,402 tokens) | McDonald's Q4 2022 earnings | Such a string is cut by length |

Check: section of every page saved before the fixes and compared after (`section_diff_fix1.txt`): 1,364 pages in 53 documents changed; the changes looked at were all corrections.

## Known, accepted

- **No Items by design** (page headings used): Intel 10-K 2017–2021 (index only at the end), McDonald's 10-K 2022 (index only), Lockheed Martin 10-Q Q1/Q2 2023 (earnings layout).
- **`item_backwards` left (1,181):** mostly eBay 10-Ks (1,122): financial statements printed after Item 16 are labelled Item 8, which is correct. The check rule flags them; the label is right.
- Activision 2015: the Item 1 heading is not found (mid-page on p4), so pages 1–15 have no section (blank, not wrong).
- Walmart 2015–2017: the annual report after Exhibit 12.1 has no whole-line "Exhibit 13" heading, so it is labelled Exhibit 12.1.
- 3M 2019 p13: wrapped line "Exhibit 95 to this annual report." starts a section (1 chunk).
- 17 earnings documents: period end estimated from the document list.
- 2 small 8-Ks (2–3 pages) give 4 chunks each: correct.

Locked set: documents used by locked questions are part of the corpus and were ingested; no check looked at their evidence pages.
