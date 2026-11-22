# Q106: PDF reader fixes, tables cut in two and lost titles (2026-11-22, free)

Code: `src/filing_rag/ingest/blocks.py` (`_row_label_gap`, `columns_line_up`, `_is_section_label`,
`mostly_numbers`, `title_from_header_zone`), `layout.py` (`Line.spans`). `INGEST_VERSION =
m2-tables`. 284 unit tests (17 new: cut joins, tables that must stay separate, title rules).

## The fixes

1. **Long row name inside a table** (Apple 10-Q p5/p8, Ulta p7, most cash-flow statements):
   "Adjustments to reconcile net income to cash ... activities:" has no numbers and more than
   10 words, so the table ended there. Now 1-2 such lines stay in the table when the next line
   is a row and the number columns line up (right edges). Not when the line ends with a full
   stop, has a unit, a digit, or is an Item heading.
2. **"... as follows:" title with two numbers** ("less than 12 months and 12 months or
   greater"): rejected only when most words are numbers.
3. **Title above loose header lines** (J&J "Supplementary Sales Data"): for a table with no
   title, walk up the short blocks on the same page; the highest heading is the title, the short
   blocks move into the table header.
4. **Bold section label** ("Operating activities") under a column header is part of the table,
   so the header lines and the title above are found.

## Count (41 documents: 21 dev + 20 random, `experiments/m2/table_reader/count.py`)

| | Before | After |
|---|---|---|
| Tables | 2,821 | 2,749 |
| Untitled | 972 (34%) | 893 (32%) |
| Probable cuts A (long row name between two tables) | 68 | 20 |
| Probable cuts B (1 row lost above a long row name) | 35 | 4 |

Cut detector check (20 marked, before): 18 real cuts, 1 real new table (FedEx, gap with a unit,
the fix does not join it), 1 exhibit list.

**Untitled causes (30 sampled, before):** 13 not financial tables (exhibit lists, footnotes,
people, broken layouts); 6 title sentence already in the chunk as a header line; 5 real title
lost (fixed by 2-4); 4 no title near the table in the PDF; 2 second half of a cut table.
So most "untitled" tables were harmless.

## Hand check: 20 changed tables (old `v3_t105` vs new `v3_t106`)

14 better (cash-flow statements one table with the right title; "The following table ..."
titles found), 4 same quality, 2 lost a fake title (JPMorgan "Loan delinquency (a)", "VIE
program type": row-group labels, now inside the table), **0 wrong joins**.

## Search, gold document (21 dev documents, `chunks_t106` vs `chunks`, k = 10)

| Group | Hit@5 old → Q105 → Q106 | Hit@10 old → Q106 | MRR old → Q106 | Value@5 old → Q106 |
|---|---|---|---|---|
| all (50) | 0.70 → 0.70 → **0.76** | 0.74 → 0.84 | 0.586 → 0.598 | 0.65 → 0.75 |
| table (28) | 0.607 → 0.607 → **0.714** | 0.643 → 0.821 | 0.477 → 0.499 | 0.60 → 0.80 |
| text (22) | 0.818 → 0.818 → 0.818 | 0.864 → 0.864 | 0.725 → 0.725 | 0.70 → 0.70 |

Better: dev_0009 (J&J MedTech, miss → 3), dev_0047 (miss → 3), dev_0048 (miss → 2), dev_0044
(7 → 3), dev_0005 (Apple comprehensive income: gold number now in the rank-1 chunk). Worse:
dev_0050 (2 → 7; the top 5 holds other CVS tables with the same numbers, strict page score),
dev_0037 (6 → 9), dev_0032 (2 → 3, still top 5).

**Verdict: go** (rule set before the run: table Hit@5 up from 0.607, text not down) → full
re-ingest into `chunks_v2` (folder `data/v3_v2`); `chunks` kept for rollback.

## Full collection `chunks_v2` (all 360 documents, 2026-11-22)

Ingest: 359/360 OK (same broken source PDF as before), 188,159 chunks (`chunks`: 189,504), 0
over the limit, 0 duplicate ids. Log `experiments/m2/table_reader/ingest_all_v2.log`.

| Rule A (production document choice) | `chunks` | `chunks_v2` |
|---|---|---|
| all Hit@1 / @5 / @10 | 0.38 / 0.62 / 0.70 | 0.36 / 0.64 / 0.78 |
| table Hit@5 / @10 | 0.571 / 0.607 | 0.607 / 0.750 |
| text Hit@5 / @10 | 0.682 / 0.818 | 0.682 / 0.818 |
| Value@5 all / table | 0.50 / 0.40 | 0.65 / 0.70 |

Gold document: same as the small test. **Not worse → switched** (`config.py`:
`qdrant_collection = "chunks_v2"`, `ingest_dir_name = "v3_v2"`). Rollback: set both back to
`chunks` / `v3`. Output: `experiments/m2/table_titles/full_v2/`.

## Still open

- 20 type-A cuts left: gap lines with digits or footnote marks (JPMorgan VaR "(44) (a) NM").
- Computed metrics (operating margin) and the strict page score (one number on several pages).
