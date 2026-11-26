# FB-dev study: what the 50 questions need (Q112 step 2, 2026-11-26)

Free study, no LLM call. IDs and tags only; the FinanceBench text stays in `data/fb_dev/`.
Full table: `STUDY_TABLE.md`. Code facts: `study_facts.py`; my tags: `study_tags.py`.

## Facts (code)

- All 50 evidence documents are in the collection; every evidence page has chunks.
- Every question uses **one document**. 11 questions need **2+ pages** of that document
  (mostly two statements: income + balance sheet, or income + cash flow).
- 23 questions have a split table on the evidence page; 12 have a table without a title.

## What the questions ask (my tags)

| Answer type | Count | | Calculation | Count |
|---|---|---|---|---|
| one number | 21 | | none (look up) | 23 |
| yes/no + reason | 10 | | one operation | 7 |
| pick one item (row, segment, region) | 6 | | several operations | 8 |
| short text / list | 6 | | average of 2–3 values | 6 |
| "none / 0 / not relevant" | 4 | | rank rows of a table | 6 |
| two or more numbers | 3 | | | |

- 18 use analyst words that differ from the filing line item (capex vs "Purchases of
  property, plant and equipment", net AR vs "Trade receivables, net", COGS vs "Total cost of
  revenue", unadjusted EBITDA = operating income + D&A from the cash flow statement).
- 12 depend on a quarter or a date inside the year (10-Q, earnings release, 8-K).
- 7 need a fixed number in the formula (average = /2 or /3, DPO = 365 × ..., retention =
  1 − payout).
- 6 need knowledge or a threshold the filing does not state (a bank has no gross margin,
  "capital intensive", "consistent within 2%").

## Top 5 risks (ranked by questions affected)

| # | Risk | Questions | Why it fails today |
|---|---|---|---|
| 1 | **Calculator gaps** | 7 sure (constant/average), up to 13 with multi-step | Inputs must be quoted values; no average, no multiply, no fixed numbers (2, 3, 365, 1). |
| 2 | **Analyst words vs filing words** | 18 | Search and the writer must map "capex" to the filing line item. Reranker helps search; the writer must know the definitions. |
| 3 | **Quarter / several documents in one year** | 12 | The router has no quarter; the filter holds all 10-Qs, 8-Ks and earnings of the year (twin documents). One case (fb_00603) also has a fiscal-year naming gap ("FY2023" = the company's fiscal 2022). |
| 4 | **Two statements, one company-year** | 11 | One router step = one search = top 5 chunks; both statements must be in the same top 5. |
| 5 | **"None / 0 / not relevant" and judgement answers** | 4 + 6 | The checked answer refuses when it has no checked fact; "no acquisitions", "state 0" or "gross margin is not relevant for a bank" have no number to quote. |

Also for marking: gold values are rounded (ROA "0.01", ratios to 2 decimals, % to 1
decimal), so the number match must accept a value that rounds to the gold.

## Generic fixes to consider (Q100: causes, not single questions). Not built.

1. **Calculator:** add `average` and `multiply`, and allow fixed numbers from the question or
   the formula as inputs (2, 3, 365, 1), checked by code.
2. **Router search text:** write the filing words for the metric (for example "Purchases of
   property, plant and equipment" for capex) and allow 2 search steps for one company-year
   when the question names two statements or two metrics.
3. **Quarter:** add `quarter` to the router step and filter the catalog by `fiscal_quarter`
   (the pending "twin documents" item).
4. **Answer types:** allow an answer without a number when a quote supports it ("no
   acquisitions", "not reported = 0", "not a relevant metric for a bank"), and yes/no answers.
5. **Marking:** a rounding-aware number match (round the answer to the gold's decimals).

12 questions look fine for today's system (simple look-ups and one-step ratios).
