# Routed scorecard (20261126-095032)

Model `claude-sonnet-5-5`, top-k 5, collection `chunks_v2`, router `claude-haiku-5-5` + document filter (rule A), JSON answers.

| Group | Number answers correct (code) | Page in chunks | Correct source cited |
|---|---|---|---|
| all | 1/1 (100%) | 2/2 (100%) | 2/2 (100%) |
| answer_source=table | 1/1 (100%) | 2/2 (100%) | 2/2 (100%) |
| category=calculate | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |
| category=compare_companies | - | 1/1 (100%) | 1/1 (100%) |

## Failure tags (code-marked wrong answers)

- none

Hand-marked (see text_answers_to_mark.md): 1

## Cost and speed

- Total cost: $0.0381
- Tokens: 19868 in, 1066 out
- Time per question: median 5.85 s, max 6.65 s
- Questions with a JSON retry: 0
- Stopped by the cost limit: False
- Router cost: $0.00065; answer cost: $0.0375
- Router time: median 1.69 s

## Routes

- answer: 2

| ID | Route | Steps (company year) | Doc type | Documents searched |
|---|---|---|---|---|
| dev_0037 | answer | Apple 2019; Apple 2018 |  | APPLE_2018_10K, APPLE_2019_10K |
| dev_0047 | answer | Costco 2019; Verizon 2018 |  | COSTCO_2019_10K, VERIZON_2018_10K |

## Checked answers (Q107)

- Status: answer 2
- Claims passed the quote check: 4/4 (100%)
- Failure reasons: none

## Per question

| ID | Mark | Tag | Page seen | Value | Gold |
|---|---|---|---|---|---|
| dev_0037 | correct |  | yes | -10.386910142831313 % | -10.4 % |
| dev_0047 | hand |  | yes | 21840.0 USD million | (hand) |
