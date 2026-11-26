# Routed scorecard (20261126-133536)

Model `claude-sonnet-5-5`, top-k 5, collection `chunks_v2`, router `claude-haiku-5-5` + document filter (rule A), reranker `BAAI/bge-reranker-v2-m3` over 100, JSON answers.

| Group | Number answers correct (code) | Page in chunks | Correct source cited |
|---|---|---|---|
| all | 0/2 (0%) | 1/2 (50%) | 1/2 (50%) |
| answer_source=None | 0/2 (0%) | 1/2 (50%) | 1/2 (50%) |
| category=fb_metrics | 0/2 (0%) | 1/2 (50%) | 1/2 (50%) |

## Failure tags (code-marked wrong answers)

- answer_error: 1
- search_miss: 1

Hand-marked (see text_answers_to_mark.md): 0

## Cost and speed

- Total cost: $0.0636
- Tokens: 29003 in, 2023 out
- Time per question: median 7.55 s, max 9.88 s
- Questions with a JSON retry: 0
- Stopped by the cost limit: False
- Router cost: $0.00077; answer cost: $0.0628
- Router time: median 1.87 s

## Routes

- answer: 2

| ID | Route | Steps (company year) | Doc type | Documents searched |
|---|---|---|---|---|
| fb_02608 | answer | Best Buy 2015; Best Buy 2016; Best Buy 2017 |  | BESTBUY_2015_10K, BESTBUY_2016_10K, BESTBUY_2017_10K |
| fb_06247 | answer | Walmart 2018; Walmart 2017 |  | WALMART_2017_10K, WALMART_2018_10K |

## Checked answers (Q107)

- Status: partial 1, refused 1
- Claims passed the quote check: 9/9 (100%)
- Failure reasons: calc_error 1

## Per question

| ID | Mark | Tag | Page seen | Value | Gold |
|---|---|---|---|---|---|
| fb_02608 | wrong | answer_error | yes | None | 2.8 % |
| fb_06247 | wrong | search_miss | no | None | 42.69 ratio |
