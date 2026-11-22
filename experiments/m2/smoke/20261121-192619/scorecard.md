# Routed scorecard (20261121-192619)

Model `claude-sonnet-5-5`, top-k 5, collection `chunks`, router `claude-haiku-5-5` + document filter (rule A), JSON answers.

| Group | Number answers correct (code) | Page in chunks | Correct source cited |
|---|---|---|---|
| all | 1/2 (50%) | 2/2 (100%) | 1/2 (50%) |
| answer_source=table | 1/2 (50%) | 2/2 (100%) | 1/2 (50%) |
| category=calculate | 0/1 (0%) | 1/1 (100%) | 0/1 (0%) |
| category=find_number | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |

## Failure tags (code-marked wrong answers)

- answer_error: 1

Hand-marked (see text_answers_to_mark.md): 0

## Cost and speed

- Total cost: $0.0153
- Tokens: 9836 in, 473 out
- Time per question: median 5.87 s, max 6.77 s
- Questions with a JSON retry: 2
- Stopped by the cost limit: False
- Router cost: $0.00048; answer cost: $0.0149
- Router time: median 3.77 s

## Routes

- answer: 2

| ID | Route | Companies | Years | Doc type | Documents searched |
|---|---|---|---|---|---|
| dev_0003 | answer | MGM Resorts | [2017] |  | MGMRESORTS_2017_10K |
| dev_0032 | answer | McDonalds | [2023] |  | MCDONALDS_2023Q1_EARNINGS, MCDONALDS_2023Q2_EARNINGS, MCDONALDS_8K_dated-2023-01-06, MCDONALDS_8K_dated-2023-02-13, MCDONALDS_8K_dated-2023-08-14 |

## Per question

| ID | Mark | Tag | Page seen | Value | Gold |
|---|---|---|---|---|---|
| dev_0003 | correct |  | yes | 1499.995 USD million | 1499995.0 USD thousand |
| dev_0032 | wrong | answer_error | yes | None | 42.9 % |
