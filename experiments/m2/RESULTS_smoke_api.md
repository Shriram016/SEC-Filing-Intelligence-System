# Smoke test: API service (Q108)

Run 2026-11-22, local server in paid mode (`FILING_RAG_ALLOW_PAID=true`), script `experiments/m2/api_smoke/smoke.py`, events with times in `experiments/m2/api_smoke/results_20261122.json`. Cost **$0.0164** (estimate $0.02–0.03).

## Result

| # | Question | Events | Status | Value | Time | Cost |
|---|---|---|---|---|---|---|
| 1 | dev_0005: Apple total comprehensive income, 9 months to 1 Jul 2023 | 4 progress → answer → done | answer, correct | $73,347 million | 4.3 s | $0.0088 |
| 2 | Follow-up: "And what was its net income for the same period?" (with history) | 4 progress → answer → done | refused | — | 4.9 s | $0.0076 |

Event times (question 1): routing 0.32 s, searching 1.93 s, answering 2.32 s, checking + answer + done 4.64 s. First event after 0.3 s.

Citation of question 1: `APPLE_2023Q3_10Q` page 5, quote "Total comprehensive income $ 19,826 $ 16,639 $ 73,347 $ 69,622".

## What worked

- `/ready` in paid mode: catalog, Qdrant collection and key all true.
- SSE order and data as in `api.md` §3; citation with the quote; `done` cost matches the runner (dev_0005 $0.0088 in both).
- Follow-up: the router used the history (company Apple, document `APPLE_2023Q3_10Q`).
- No unchecked number reached the user: question 2 was refused, not guessed.

## What failed: question 2 (search miss, not an API problem)

- Free check: 5 chunks of `APPLE_2023Q3_10Q` hold the "Net income" row (pages 4, 5, 7, 8, 9: income statement, comprehensive income, equity, cash flow, EPS). None was in the top 5 for "Apple's net income for the nine months ended July 1, 2023"; the search returned net sales tables (pages 10, 16, 19) and text.
- Same cause as M1d ("table pages rank low"): statement tables with many rows embed poorly for a one-row question. Candidate fixes are on the pending list (BM25 / hybrid search, reranker).

## Fix after the run (free)

The log line did not show why a question was refused. It now also has `search_question`, `pages`, `writer_found`, `claims_total`, `claims_passed` and `check_failures`. 341 tests pass.
