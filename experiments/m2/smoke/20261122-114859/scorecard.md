# Routed scorecard (20261122-114859)

Model `claude-sonnet-5-5`, top-k 5, collection `chunks_v2`, router `claude-haiku-5-5` + document filter (rule A), JSON answers.

| Group | Number answers correct (code) | Page in chunks | Correct source cited |
|---|---|---|---|
| all | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) |
| answer_source=table | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) |
| category=find_number | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) |

## Failure tags (code-marked wrong answers)

- none

Hand-marked (see text_answers_to_mark.md): 0

## Cost and speed

- Total cost: $0.0150
- Tokens: 9707 in, 498 out
- Time per question: median 4.36 s, max 4.87 s
- Questions with a JSON retry: 0
- Stopped by the cost limit: False
- Router cost: $0.00050; answer cost: $0.0145
- Router time: median 2.09 s

## Routes

- answer: 2

| ID | Route | Companies | Years | Doc type | Documents searched |
|---|---|---|---|---|---|
| dev_0005 | answer | Apple | [2023] |  | APPLE_2023Q3_10Q |
| dev_0009 | answer | Johnson & Johnson | [2023] |  | JOHNSON_JOHNSON_2023Q1_EARNINGS, JOHNSON_JOHNSON_2023Q2_EARNINGS, JOHNSON_JOHNSON_2023_8K_dated-2023-08-23, JOHNSON_JOHNSON_2023_8K_dated-2023-08-30 |

## Per question

| ID | Mark | Tag | Page seen | Value | Gold |
|---|---|---|---|---|---|
| dev_0005 | correct |  | yes | 73347.0 USD million | 73347.0 USD million |
| dev_0009 | correct |  | yes | 7481.0 USD million | 7481.0 USD million |
