# M2 router smoke test (2026-11-21, paid, approved)

Run: `experiments/m2/smoke/20261121-192619/`. Questions: dev_0003, dev_0032 (both baseline search
misses; both fixed by the year filter in the free test). Setup: router Claude Haiku 5.5 (effort
low, adaptive thinking) → catalog document list (rule A) → filtered search top 5 → Sonnet 5.5
JSON answer.

Cost: $0.0153 (router $0.00048, answer $0.0149). Estimate was $0.017. Time: 5.0 s and 6.8 s
per question (router 2.7 s and 4.8 s).

| Question | Router output | Documents searched | Result |
|---|---|---|---|
| dev_0003 MGM cash, end of 2017 | MGM Resorts, [2017], route answer | MGMRESORTS_2017_10K | **Correct**: $1,499,995 thousand, cites page 66 (baseline: search miss) |
| dev_0032 McDonald's operating margin Q1 2023 | McDonalds, [2023], route answer | 5 McDonald's 2023 documents (Q1 + Q2 earnings, three 8-Ks) | **Wrong**: "not found". Page 2 was in the top 5 (two chunks), but not the "Key financial metrics" table chunk that holds operating income and revenue |

## Findings

1. The router works: valid JSON both times, correct company, correct year, correct route, no retry.
2. The filter works: dev_0003 is fixed.
3. dev_0032 shows two known causes:
   - **Right page, wrong chunk:** page 2 has 6 chunks; the needed table chunk ranked low. Same
     cause as the 3 "table cut" baseline errors. The page-level "page in chunks" check
     overstates here.
   - **The quarter is not used:** "first quarter of 2023" gave 5 documents; a quarter field would
     give only the Q1 release. Same cause as dev_0015 in the free test.
4. Router time (2.7–4.8 s) is longer than expected for Haiku with low effort. Measure on more
   questions before tuning (later eval).

Note: the scorecard of this run says "JSON retry: 2". That count was wrong (it counted router +
answer as two calls). Fixed in the runner after the run; there were no retries. The run files
were not changed.
