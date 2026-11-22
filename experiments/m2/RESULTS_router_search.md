# M2 step 5: search test with a "perfect router" (2026-11-21, free)

Script: `experiments/m2/router_search.py`. Raw results: `experiments/m2/router_search/`.
Setup: 50 dev questions (draft), collection `chunks`, k = 10. Company from the gold document;
years read from the question text by code (4-digit years, FY'22). Documents chosen by the
catalog (`src/filing_rag/router/catalog.py`), then a hard `doc_name` filter (Q104).

## Scores

| Version | Hit@1 | Hit@5 | Hit@10 | MRR@10 | Blocked |
|---|---|---|---|---|---|
| No filter (baseline) | 0.28 | 0.48 | 0.64 | 0.379 | 0 |
| Company filter only | 0.28 | 0.48 | 0.68 | 0.385 | 0 |
| **Option A: company + year Y, else Y+1** | **0.38** | **0.62** | 0.70 | **0.480** | 1 |
| Option B: company + always Y and Y+1 | 0.30 | 0.62 | 0.72 | 0.426 | 0 |
| Gold document (best possible) | 0.52 | 0.70 | 0.74 | 0.586 | 0 |

"Blocked" = the chosen documents do not include the evidence document.

## Decision

Rule set before the run: keep option A unless option B finds the page for 3 or more extra
questions in the top 5. Option B: 0 extra at top 5, and lower Hit@1 / MRR (the Y+1 document
adds noise). **Option A kept.**

The company filter alone gives nothing at top 5: the problem was the wrong year, not other
companies. The year (via the document list) gives +7 questions at top 5.

## The gap to the gold document (0.62 → 0.70), by cause

| Question | Cause | Note |
|---|---|---|
| dev_0007 FedEx EPS FY2023 | Twin documents (10-K + annual report, same year) | Rank 9; the gold page is in the annual report |
| dev_0015 Ulta Q1 fiscal 2023 | 5 Ulta documents for 2023 (10-K, 10-Qs, earnings); the quarter is not used | Rank 7. A quarter field could fix it (not built) |
| dev_0024 Walmart gift cards | No year in the question → all 11 Walmart documents | Rank 6 |
| dev_0025 MGM cash flow 2016 vs 2015 | Blocked: rule A picks the FY2015 + FY2016 10-Ks; the gold page is in the FY2017 10-K (3-year cash-flow table) | The FY2016 10-K very likely has the same numbers; a scoring gap (one gold page), not proven a real miss |

Option B helps only dev_0025 and hurts dev_0026 (Intel 2019: rank 3 → 6).

## Limits

- Best case: the real router can get the company or the years wrong. Measured later (smoke
  test now, full eval after all components).
- Draft dev set, 50 questions: one question = 2 points.
