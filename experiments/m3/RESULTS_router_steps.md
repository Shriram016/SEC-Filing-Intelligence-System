# Router steps (Q109): build and free tests

Run 2026-11-23. No LLM call. Collection `chunks_v2`, top 5 per step, split-table parts (max 3) per step.

## What was built

- Router JSON: `steps` (`company`, `year`, `search`) replace `companies` and `years`; prompt rules for year ranges, "year-ago", "N years ended", forecast years; at most 4 steps (more → `unclear`, nothing dropped).
- Code: catalog selection per step; one filtered search per step; merge in step order without duplicates; one writer call. One step → search with the standalone question (M2 behaviour).
- Logs: steps in the API log line and in the runner rows / scorecard.
- Dev set: `gold_steps` for all 50 answerable questions (35 one step, 15 two steps), written from the question text, status draft. Backup: `experiments/m3/router_steps/dev_set_before_gold_steps.jsonl`. Script: `add_gold_steps.py` (checks companies and coverage).
- Router check: `src/filing_rag/evaluation/router_check.py` (route, steps, documents, gold page; router calls only).
- Tests: 357 pass (341 + 16 new), ruff, mypy clean.

## Free test 1: gold steps against the catalog

All gold companies are in the catalog. One coverage difference: dev_0025 asks "2016 vs 2015", evidence is the 2017 10-K; the steps search the 2015 and 2016 10-Ks (they hold those years too). Not a gold error.

## Free test 2: "perfect plan" search (`perfect_steps.py`)

The gold steps go to the search with the question text as search text (so only the effect of one search per step is measured).

| Questions | Any gold page: M2 → Q109 | All gold pages: M2 → Q109 | Chunks per question: M2 → Q109 |
|---|---|---|---|
| All 50 | 34 → 34 | 32 → 33 | 5.3 → 7.0 |
| 1 step (35) | 26 → 26 | 26 → 26 | 5.2 → 5.2 |
| 2 steps (15) | 8 → 8 | 6 → 7 | 5.7 → 11.3 |

- Gain: dev_0047 (Costco vs Verizon) — M2 found only one company's page; steps find both.
- No loss on any question. One-step questions are unchanged (same search).
- Cost: two-step questions send about 2× the chunks to the writer.
- Why the gain is small: 11 of the 15 two-step questions have both years in one filing, so one search already reaches it. The misses are ranking misses inside the right filing (known: "table pages rank low").
- Not measured here: the router's own search text per step (needs router calls).

## Paid test (waiting for approval)

Router check, 50 questions, router calls only: dry run estimate **$0.018** (worst case $0.035, limit $0.10).
