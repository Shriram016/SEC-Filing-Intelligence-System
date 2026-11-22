# Baseline scorecard (20261121-130339)

Model `claude-sonnet-5-5`, top-k 5, collection `chunks`, no company filter, JSON answers.

| Group | Number answers correct (code) | Page in chunks | Correct source cited |
|---|---|---|---|
| all | 16/35 (46%) | 24/50 (48%) | 22/50 (44%) |
| answer_source=table | 7/23 (30%) | 11/28 (39%) | 10/28 (36%) |
| answer_source=text | 9/12 (75%) | 13/22 (59%) | 12/22 (55%) |
| category=calculate | 5/10 (50%) | 6/10 (60%) | 5/10 (50%) |
| category=compare_companies | - | 0/4 (0%) | 0/4 (0%) |
| category=compare_years | 1/5 (20%) | 3/6 (50%) | 3/6 (50%) |
| category=explain_why | - | 6/10 (60%) | 5/10 (50%) |
| category=find_number | 10/20 (50%) | 9/20 (45%) | 9/20 (45%) |

## Failure tags (code-marked wrong answers)

- answer_error: 6
- search_miss: 13

Hand-marked (see text_answers_to_mark.md): 15

## Cost and speed

- Total cost: $0.3441
- Tokens: 132892 in, 7832 out
- Time per question: median 2.13 s, max 3.20 s
- Questions with a JSON retry: 0
- Stopped by the cost limit: False

## Per question

| ID | Mark | Tag | Page seen | Value | Gold |
|---|---|---|---|---|---|
| dev_0001 | wrong | search_miss | no | None | 1788.0 USD million |
| dev_0002 | wrong | search_miss | no | None | 1427.0 USD million |
| dev_0003 | wrong | search_miss | no | 208.364 USD million | 1499995.0 USD thousand |
| dev_0004 | wrong | search_miss | no | None | 46291.0 USD million |
| dev_0005 | wrong | answer_error | yes | None | 73347.0 USD million |
| dev_0006 | correct |  | yes | 17039.0 USD million | 17039.0 USD million |
| dev_0007 | wrong | search_miss | no | None | 15.48 USD |
| dev_0008 | correct |  | yes | 112.5 bps per annum | 112.5 basis points |
| dev_0009 | wrong | search_miss | no | None | 7481.0 USD million |
| dev_0010 | correct |  | yes | 76.0 USD million | 76.0 USD million |
| dev_0011 | correct |  | yes | 82.0 % | 82.0 % |
| dev_0012 | correct |  | no | 3000000000.0 shares | 3000000000.0 shares |
| dev_0013 | correct |  | yes | 15.0 business days | 15.0 business days |
| dev_0014 | correct |  | no | 850.0 USD million | 850000000.0 USD |
| dev_0015 | correct |  | no | 1359.0 stores | 1359.0 stores |
| dev_0016 | wrong | search_miss | no | 1725.0 USD million | 1.7 USD billion |
| dev_0017 | correct |  | yes | 3.2 % | 3.2 % |
| dev_0018 | wrong | answer_error | yes | 8.0 years | 23.0 years |
| dev_0019 | wrong | search_miss | no | None | 2000.0 USD |
| dev_0020 | correct |  | yes | 38.4 USD billion | 38.4 USD billion |
| dev_0021 | hand |  | yes | None | (hand) |
| dev_0022 | hand |  | yes | None | (hand) |
| dev_0023 | hand |  | yes | None | (hand) |
| dev_0024 | hand |  | no | None | (hand) |
| dev_0025 | hand |  | yes | None | (hand) |
| dev_0026 | hand |  | no | None | (hand) |
| dev_0027 | hand |  | no | None | (hand) |
| dev_0028 | hand |  | yes | None | (hand) |
| dev_0029 | hand |  | no | None | (hand) |
| dev_0030 | hand |  | yes | 87.0 % | (hand) |
| dev_0031 | correct |  | yes | 22.2 % | 22.2 % |
| dev_0032 | wrong | search_miss | no | None | 42.9 % |
| dev_0033 | correct |  | yes | 1230.8 USD million | 1230.8 USD million |
| dev_0034 | correct |  | yes | 42.93 % | 42.9 % |
| dev_0035 | wrong | search_miss | no | 8.0 % | 8.1 % |
| dev_0036 | correct |  | yes | -4.7 % | -4.7 % |
| dev_0037 | correct |  | no | -10.3 % | -10.4 % |
| dev_0038 | wrong | answer_error | yes | None | 80149.0 USD million |
| dev_0039 | wrong | search_miss | no | None | 33.6 % |
| dev_0040 | wrong | answer_error | yes | 254.0 USD million | 5.0 % |
| dev_0041 | wrong | search_miss | no | None | -11.4 % |
| dev_0042 | hand |  | yes | None | (hand) |
| dev_0043 | wrong | answer_error | yes | None | -28.5 % |
| dev_0044 | correct |  | no | 63.0 % | 63.0 % |
| dev_0045 | wrong | search_miss | no | None | 20.0 % |
| dev_0046 | wrong | answer_error | yes | 1491.0 USD million | 20.6 % |
| dev_0047 | hand |  | no | None | (hand) |
| dev_0048 | hand |  | no | None | (hand) |
| dev_0049 | hand |  | no | None | (hand) |
| dev_0050 | hand |  | no | None | (hand) |
