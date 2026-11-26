# Q109 results: paid router check + smoke test (2026-11-26)

## 1. Router check (50 dev questions, router calls only)

Run: `experiments/m3/router_check/20261126-093958/` (summary.md, results.json).
Command: `uv run --group embed python -m filing_rag.evaluation.router_check --allow-paid`.
Cost $0.0161 (dry run said $0.018). Router median 1.72 s. JSON retries 0, failures 0.

| Check | All | One gold step | 2+ gold steps |
|---|---|---|---|
| Route correct | 45/50 (90%) | 31/35 | 14/15 |
| Steps = gold steps | **50/50 (100%)** | 35/35 | 15/15 |
| Gold documents in step documents | 44/50 (88%) | 31/35 | 13/15 |
| Gold page in step chunks | 32/50 (64%) | 23/35 | 9/15 |

Free perfect-plan test gave 33/50 pages. The real router gives 32/50: the router plans
are all correct, the loss is in the code after the router.

### Wrong route: 5 questions, all `not_covered`, all with correct steps

Cause found from the code (`router.py` `apply_catalog`: `not_covered` when a step has
missing documents **or** `other_companies` is not empty). The run does not save
`other_companies` or `doc_type`, so causes A/B come from the step documents + logic.

| Cause | IDs | Detail |
|---|---|---|
| A. Non-company names in `other_companies` | dev_0013 (Citibank), dev_0021 (EPA), dev_0036 (UNITE HERE Health) | Every step found documents, so only `other_companies` can make the route `not_covered`. |
| B. Doc type filter too strict | dev_0011 ("annual report", Intel 2019 has a 10-K only), dev_0016 ("earnings release", Lockheed 2023 has 10-Qs, no earnings doc) | Step documents empty → missing pair. |

### Wrong documents, route correct: 1 question

- dev_0025 (MGM cash from operations 2016 vs 2015): steps 2015 + 2016 → 10-Ks 2015/2016; the
  gold page is in the 2017 10-K. Known rule A limit (later filing also holds the year).

### Page not found (18): documents 1, route 5, search 12

Search misses: dev_0004, 0007, 0014, 0015, 0019, 0024, 0029, 0035, 0039, 0044, 0045, 0049.
This is the known big-table-page problem (pending: BM25 hybrid / reranker).

## 2. Smoke test (2 questions, end to end)

Run: `experiments/m2/smoke/20261126-095032/`. Cost $0.0381 (dry run $0.028 expected,
$0.056 worst; the writer read more chunks with 2 steps). Median 5.85 s per question.

| ID | Steps | Documents | Result |
|---|---|---|---|
| dev_0037 (Apple 2019 vs 2018, % change) | Apple 2019; Apple 2018 | APPLE_2018_10K, APPLE_2019_10K | correct: -10.39% (gold -10.4%) |
| dev_0047 (Costco FY2019 vs Verizon 2018 revenue) | Costco 2019; Verizon 2018 | COSTCO_2019_10K, VERIZON_2018_10K | values correct ($152,703M vs $130,863M, diff $21,840M) |

Claims 4/4 passed the quote check. Calculator OK.

### Bug found: double unit in the sentence

dev_0047 sentence: "$152,703 million million USD". The writer wrote
`"{c1} million USD"`; `fmt_value` already renders "$152,703 million". The check
`_sentence_safe` does not catch unit words after a placeholder.

## 3. Fixes (Q110, built 2026-11-26, user decision)

1. Cause A: `other_companies` removed. The LLM sets `not_covered` for a company outside the
   list; only-mentioned parties (regulator, partner, bank, fund, union) do not count.
2. Cause B: when the named doc type gives no document, fall back to all types for that
   company + year (10-K = annual report).
3. Sentence bug: `_sentence_safe` rejects unit words after a placeholder (fall back to the
   plain sentence), plus one line in the writer prompt.
4. Router check rows save `doc_type` and the router `reason` (also in the wrong-route table).

366 tests pass.

## 4. Router check after the Q110 fixes (2026-11-26)

Run: `experiments/m3/router_check/20261126-103711/`. Cost $0.0163.

| Check | Before (Q109) | After (Q110) |
|---|---|---|
| Route correct | 45/50 | **50/50** |
| Steps = gold steps | 50/50 | 50/50 |
| Gold documents in step documents | 44/50 | **49/50** |
| Gold page in step chunks | 32/50 | **36/50** |

- All 5 wrong routes fixed (dev_0011, 0013, 0016, 0021, 0036).
- Only document miss left: dev_0025 (rule A limit, gold page in the 2017 10-K).
- Page misses: 14 = documents 1 (dev_0025) + search 13 (the 12 before + dev_0016, now routed
  but the page is not in the top 5). Next real gain is the search fix for big table pages.
