# Router check (Q109)

- Run: 20261126-093958; router model: claude-haiku-5-5; collection: chunks_v2; top k per step: 5
- Questions: 50; cost $0.0161; router time median 1.72 s
- Router JSON retries: 0; router failures: 0
- Stopped by the cost limit: False

| Check | All | One gold step | Two or more gold steps |
|---|---|---|---|
| Route correct | 45/50 (90%) | 31/35 (89%) | 14/15 (93%) |
| Steps = gold steps | 50/50 (100%) | 35/35 (100%) | 15/15 (100%) |
| Gold documents in the step documents | 44/50 (88%) | 31/35 (89%) | 13/15 (87%) |
| Gold page in the chunks of a step | 32/50 (64%) | 23/35 (66%) | 9/15 (60%) |

## By category

| Category | Route | Steps | Documents | Page |
|---|---|---|---|---|
| calculate | 9/10 (90%) | 10/10 (100%) | 9/10 (90%) | 7/10 (70%) |
| compare_companies | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 3/4 (75%) |
| compare_years | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) | 4/6 (67%) |
| explain_why | 9/10 (90%) | 10/10 (100%) | 8/10 (80%) | 6/10 (60%) |
| find_number | 17/20 (85%) | 20/20 (100%) | 17/20 (85%) | 12/20 (60%) |

## Questions with a wrong route, steps or documents

| ID | Route | Missing pairs | Extra pairs | Missing documents |
|---|---|---|---|---|
| dev_0011 | not_covered |  |  |  |
| dev_0013 | not_covered |  |  |  |
| dev_0016 | not_covered |  |  |  |
| dev_0021 | not_covered |  |  |  |
| dev_0025 | answer |  |  | MGMRESORTS_2017_10K |
| dev_0036 | not_covered |  |  |  |

## Gold page not found

- Cause: documents 1, route 5, search 12
- IDs: dev_0004, dev_0007, dev_0011, dev_0013, dev_0014, dev_0015, dev_0016, dev_0019, dev_0021, dev_0024, dev_0025, dev_0029, dev_0035, dev_0036, dev_0039, dev_0044, dev_0045, dev_0049
