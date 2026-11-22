# Routed scorecard (20261122-142929)

Model `claude-sonnet-5-5`, top-k 5, collection `chunks_v2`, router `claude-haiku-5-5` + document filter (rule A), JSON answers.

| Group | Number answers correct (code) | Page in chunks | Correct source cited |
|---|---|---|---|
| all | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) |
| answer_source=table | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) |
| category=calculate | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |
| category=find_number | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |

## Failure tags (code-marked wrong answers)

- none

Hand-marked (see text_answers_to_mark.md): 0

## Cost and speed

- Total cost: $0.0206
- Tokens: 10786 in, 831 out
- Time per question: median 5.19 s, max 5.45 s
- Questions with a JSON retry: 0
- Stopped by the cost limit: False
- Router cost: $0.00049; answer cost: $0.0201
- Router time: median 1.63 s

## Routes

- answer: 2

| ID | Route | Companies | Years | Doc type | Documents searched |
|---|---|---|---|---|---|
| dev_0005 | answer | Apple | [2023] |  | APPLE_2023Q3_10Q |
| dev_0038 | answer | Apple | [2023] |  | APPLE_2023Q3_10Q |

## Checked answers (Q107)

- Status: answer 2
- Claims passed the quote check: 3/3 (100%)
- Failure reasons: none

## Per question

| ID | Mark | Tag | Page seen | Value | Gold |
|---|---|---|---|---|---|
| dev_0005 | correct |  | yes | 73347.0 USD million | 73347.0 USD million |
| dev_0038 | correct |  | yes | 80149.0 USD million | 80149.0 USD million |
