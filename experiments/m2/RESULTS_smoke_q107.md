# Smoke test: checked answers (Q107)

Run: `experiments/m2/smoke/20261122-142929` (2026-11-22). Cost **$0.0206** (dry-run estimate $0.0261).

Command:

```bash
uv run --group embed python -m filing_rag.evaluation.baseline --router --ids dev_0005,dev_0038 --allow-paid --max-cost 0.10
```

## Result

| ID | Test | Status | Claims passed | Value | Gold | Mark |
|---|---|---|---|---|---|---|
| dev_0005 | plain number | answer | 1/1 | 73,347 USD million | 73,347 | correct |
| dev_0038 | free cash flow (calculator) | answer | 2/2 | 80,149 USD million | 80,149 | correct |

- Router: Apple, 2023 → `APPLE_2023Q3_10Q` for both. Gold page in the chunks for both.
- No JSON retry. No check failure. No split-table parts added.

## Answers shown to the user

- dev_0005: "Apple's total comprehensive income for the nine months ended July 1, 2023 was $73,347 million. Source: Apple 10-Q (period ended 01 Jul 2023)."
- dev_0038: "Apple free cash flow, nine months ended July 1, 2023 (operating cash flow plus negative capex): $80,149 million. Computed: … = 88,945 + -8,796 = $80,149 million. Source: Apple 10-Q (period ended 01 Jul 2023)."

## Findings

1. The quote check and the calculator worked on real model output. The model gave capex as -8,796 (printed "(8,796)") and used `add`; the result is correct.
2. dev_0038 shows the code-written line, not the model's sentence. The run did not save the model's sentence, so the reason is not known. Probably the sentence had a number of its own.
3. The formula "88,945 + -8,796" is hard to read.

## Fixes after the run (free, 321 tests)

- The results rows now save `model_sentence` and `sentence_used`. The next paid run shows why code replaced a sentence.
- A negative input is now shown in parentheses: "88,945 + (-8,796)".
