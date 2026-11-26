# Router check (Q109)

- Run: 20261126-103711; router model: claude-haiku-5-5; collection: chunks_v2; top k per step: 5
- Questions: 50; cost $0.0163; router time median 1.63 s
- Router JSON retries: 0; router failures: 0
- Stopped by the cost limit: False

| Check | All | One gold step | Two or more gold steps |
|---|---|---|---|
| Route correct | 50/50 (100%) | 35/35 (100%) | 15/15 (100%) |
| Steps = gold steps | 50/50 (100%) | 35/35 (100%) | 15/15 (100%) |
| Gold documents in the step documents | 49/50 (98%) | 35/35 (100%) | 14/15 (93%) |
| Gold page in the chunks of a step | 36/50 (72%) | 26/35 (74%) | 10/15 (67%) |

## By category

| Category | Route | Steps | Documents | Page |
|---|---|---|---|---|
| calculate | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) | 8/10 (80%) |
| compare_companies | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 3/4 (75%) |
| compare_years | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) | 4/6 (67%) |
| explain_why | 10/10 (100%) | 10/10 (100%) | 9/10 (90%) | 7/10 (70%) |
| find_number | 20/20 (100%) | 20/20 (100%) | 20/20 (100%) | 14/20 (70%) |

## Questions with a wrong route, steps or documents

| ID | Route | Missing pairs | Extra pairs | Missing documents | Doc type | Router reason |
|---|---|---|---|---|---|---|
| dev_0025 | answer |  |  | MGMRESORTS_2017_10K |  | A factual question about MGM Resorts' cash flow in filings, with both years named. |

## Gold page not found

- Cause: documents 1, search 13
- IDs: dev_0004, dev_0007, dev_0014, dev_0015, dev_0016, dev_0019, dev_0024, dev_0025, dev_0029, dev_0035, dev_0039, dev_0044, dev_0045, dev_0049
