# Routed scorecard (20261126-133953)

Model `claude-sonnet-5-5`, top-k 5, collection `chunks_v2`, router `claude-haiku-5-5` + document filter (rule A), reranker `BAAI/bge-reranker-v2-m3` over 100, JSON answers.

| Group | Number answers correct (code) | Page in chunks | Correct source cited |
|---|---|---|---|
| all | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |
| answer_source=None | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |
| category=fb_metrics | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |

## Failure tags (code-marked wrong answers)

- none

Hand-marked (see text_answers_to_mark.md): 0

## Cost and speed

- Total cost: $0.0395
- Tokens: 16670 in, 1338 out
- Time per question: median 8.28 s, max 8.28 s
- Questions with a JSON retry: 0
- Stopped by the cost limit: False
- Router cost: $0.00038; answer cost: $0.0392
- Router time: median 1.77 s

## Routes

- answer: 1

| ID | Route | Steps (company year) | Doc type | Documents searched |
|---|---|---|---|---|
| fb_02608 | answer | Best Buy 2015; Best Buy 2016; Best Buy 2017 |  | BESTBUY_2015_10K, BESTBUY_2016_10K, BESTBUY_2017_10K |

## Checked answers (Q107)

- Status: answer 1
- Claims passed the quote check: 6/6 (100%)
- Failure reasons: none

## Per question

| ID | Mark | Tag | Page seen | Value | Gold |
|---|---|---|---|---|---|
| fb_02608 | correct |  | yes | 2.8157815935649118 % | 2.8 % |
