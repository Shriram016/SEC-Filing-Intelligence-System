# Baseline scorecard (20261121-130306)

Model `claude-sonnet-5-5`, top-k 5, collection `chunks`, no company filter, JSON answers.

| Group | Number answers correct (code) | Page in chunks | Correct source cited |
|---|---|---|---|
| all | 0/3 (0%) | 0/3 (0%) | 0/3 (0%) |
| answer_source=table | 0/3 (0%) | 0/3 (0%) | 0/3 (0%) |
| category=find_number | 0/3 (0%) | 0/3 (0%) | 0/3 (0%) |

## Failure tags (code-marked wrong answers)

- search_miss: 3

Hand-marked (see text_answers_to_mark.md): 0

## Cost and speed

- Total cost: $0.0212
- Tokens: 8404 in, 440 out
- Time per question: median 2.13 s, max 3.52 s
- Questions with a JSON retry: 0
- Stopped by the cost limit: False

## Per question

| ID | Mark | Tag | Page seen | Value | Gold |
|---|---|---|---|---|---|
| dev_0001 | wrong | search_miss | no | None | 1788.0 USD million |
| dev_0002 | wrong | search_miss | no | None | 1427.0 USD million |
| dev_0003 | wrong | search_miss | no | 208.364 USD million | 1499995.0 USD thousand |
