# M1d search test: results (collection `chunks`, label depth `section`)

Date: 2026-11-21. Cost: zero (local embedding model + Qdrant). Dev set: 50 draft questions.
Run: `uv run --group embed python -m filing_rag.evaluation.retrieval --collection chunks`.
Detail files: `search_chunks_filter.{md,json}`, `search_chunks_nofilter.{md,json}`, `diagnose_chunks.json`.

**Shortcut (flagged):** the company comes from the evidence document (perfect router).

## 1. Scores (company filter on)

| Group | n | Hit@1 | Hit@5 | Hit@10 | MRR@10 |
|---|---|---|---|---|---|
| all | 50 | 0.28 | 0.48 | 0.68 | 0.385 |
| table | 28 | 0.25 | 0.39 | 0.54 | 0.325 |
| text | 22 | 0.32 | 0.59 | 0.86 | 0.461 |
| compare_companies | 4 | 0.00 | 0.00 | 0.25 | 0.042 |
| compare_years | 6 | 0.00 | 0.50 | 0.50 | 0.172 |

No filter: Hit@5 0.48, Hit@10 0.64. The filter adds little, because the question text names
the company and the search already stays inside that company.

## 2. Diagnosis (`diagnose.py`)

| Run | Hit@5 all | table | text |
|---|---|---|---|
| Company filter (now) | 24/50 | 11/28 | 13/22 |
| Doc filter (correct document only, oracle) | 35/50 | 17/28 | 18/22 |

**Cause 1: wrong document of the same company (11 questions).** 61% of the top-5 chunks come
from another document of the same company: another year (JPMorgan 2022/2023 for a 2021
question; Walmart 2018-2022 for fiscal 2023) or a duplicate filing (FEDEX_2023_10K vs
FEDEX_2023_annualreport, WALMART_2023_10K vs WALMART_2023_annualreport hold the same pages).
Same-text boilerplate repeats every year, so the vectors cannot tell the years apart.
Fix direction: the period boost of Q100 (year / quarter from the question), not built yet.
Duplicate filings: the same page in a twin document is a correct source; the test counts it
as a miss (scoring gap to fix).

**Cause 2: correct document, wrong page (15 questions).** Mostly table questions. Examples:
the 3M pension table p91 (the note text p89-90 ranks higher), Apple services revenue,
Lockheed and McDonald's statement tables. Several are found on the next page (+-1).
Number-heavy table chunks match a natural-language question poorly.
Fix directions (on measured need, Q26/Q27): BM25 keyword search (hybrid) and/or a reranker;
the label-depth test (`full` puts the table title into the vector).

**Cause 3: compare-companies questions.** One query names two companies and two metrics; its
vector matches neither page well. In the engine, the planner splits it into one step per
company ("find Costco total revenue fiscal 2019"), so this test is pessimistic for this type.

## 3. Next

1. Label-depth test: ingest `chunks_none` and `chunks_full`, run the same test.
2. Decide the fixes in order of measured gain: period boost (cause 1), then hybrid BM25 or a
   reranker (cause 2). Each with a before/after run on this test.
