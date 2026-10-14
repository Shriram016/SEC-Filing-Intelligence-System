# Latest evaluation results (V2)

**Status: current results as of 2026-10-14. A single run, to be re-validated, not final.**
Run folder: `evaluation/runs/full2_20261014/` (full record per query, token usage, cost, per-statement judge verdicts).
Metric definitions and their caveats: [`docs/EVAL_METRICS_GUIDE.md`](../docs/EVAL_METRICS_GUIDE.md).
Open changes and review notes: [`docs/V2_PENDING_CHANGES.md`](../docs/V2_PENDING_CHANGES.md).

## Setup of this run

| Item | Value |
|---|---|
| Queries | 32 (6 single fact, 8 cross-year, 4 cross-company, 3 vague, 3 invalid, 8 should-refuse) |
| Answering model | `qwen/qwen3.8-27b` (the original V2 models were retired by Groq) |
| Judge model | `openai/gpt-oss-120b` (a different model family) |
| Answer prompt | concise style (`ANSWER_STYLE="concise"`): 1-3 sentences for facts, up to 8 bullets for comparisons |
| Judge input | the same numbered passages the answering model saw |
| Ground-truth coverage | RAGAS claim splitting and checking at `atomicity="high"`, own aggregation |
| Cost | $0.45, 291 Groq calls, 806k tokens in / 165k out (prices checked 2026-10-13) |
| Errors | none; all 32 queries completed, no failed judge calls |

## Results by category

| Category | n | Faithfulness | Relevance | Precision | Recall | GT coverage |
|---|---|---|---|---|---|---|
| Single fact | 6 | 1.00 | 0.94 | 0.95 | 1.00 | 0.86 |
| Cross-year | 8 | 0.93 | 0.93 | – | 0.94 | 0.72 |
| Cross-company | 4 | 0.95 | 0.88 | – | 0.83 | 0.47 |
| Vague | 3 | 0.78 | 0.91 | – | – | – |
| **All answered** | 21 | **0.93** | **0.92** | 0.95 | **0.94** | **0.71** |
| Invalid | 3 | 3 of 3 rejected by the parser | | | | |
| Should refuse | 8 | 8 of 8 declined (4 rejected by the parser, 4 refused by the answering step) | | | | |

Precision is only computed for single-fact questions; vague questions have no ground truth.

## Results by query

| ID | Type | Words | Faith | Relev | Prec | Recall | GT cover |
|---|---|---|---|---|---|---|---|
| Q01 | single | 200 | 1.00 | 0.92 | 0.87 | 1.00 | 1.00 |
| Q02 | single | 242 | 1.00 | 0.92 | 0.81 | 1.00 | 0.38 |
| Q03 | single | 21 | 1.00 | 0.98 | 1.00 | 1.00 | 1.00 |
| Q04 | single | 55 | 1.00 | 0.90 | 1.00 | 1.00 | 0.80 |
| Q05 | single | 20 | 1.00 | 0.99 | 1.00 | 1.00 | 1.00 |
| Q06 | single | 139 | 1.00 | 0.90 | 1.00 | 1.00 | 1.00 |
| Q07 | cross-year | 357 | 0.84 | 0.94 | – | 0.50 | 0.40 |
| Q08 | cross-year | 334 | 0.95 | 0.94 | – | 1.00 | 0.50 |
| Q09 | cross-year | 117 | 0.86 | 0.89 | – | 1.00 | 1.00 |
| Q10 | cross-year | 211 | 1.00 | 0.91 | – | 1.00 | 1.00 |
| Q11 | cross-year | 288 | 0.92 | 0.85 | – | 1.00 | 0.33 |
| Q22 | cross-year | 27 | 1.00 | 0.97 | – | 1.00 | 1.00 |
| Q23 | cross-year | 230 | 1.00 | 0.97 | – | 1.00 | 0.80 |
| Q24 | cross-year | 247 | 0.85 | 1.00 | – | 1.00 | 0.70 |
| Q12 | cross-company | 331 | 1.00 | 0.82 | – | 1.00 | 0.42 |
| Q13 | cross-company | 214 | 0.91 | 0.87 | – | 1.00 | 0.33 |
| Q14 | cross-company | 95 | 0.89 | 0.90 | – | 0.33 | 0.33 |
| Q15 | cross-company | 371 | 1.00 | 0.92 | – | 1.00 | 0.78 |
| Q16 | vague | 233 | 0.49 | 1.00 | – | – | – |
| Q17 | vague | 177 | 0.88 | 0.90 | – | – | – |
| Q18 | vague | 222 | 0.96 | 0.85 | – | – | – |

## Yes/no checks

| ID | Type | Outcome | Result | App confidence |
|---|---|---|---|---|
| Q19, Q20, Q21 | invalid | rejected | pass | n/a |
| Q25, Q26, Q28, Q30 | should-refuse | rejected by the parser | pass | n/a |
| Q27 | should-refuse | refused | pass | 0.92 |
| Q29 | should-refuse | refused | pass | 0.91 |
| Q31 | should-refuse | refused | pass | 0.94 |
| Q32 | should-refuse | refused | pass | 0.92 |

The app's confidence score is about 0.91 to 0.94 for refusals, as high as for good answers (known issue).

## How to read these numbers

- **One run.** The judge is noisy (for example Q07's recall was 1.0 in one scoring pass and 0.5 here, on identical retrieved chunks). Repeat runs are needed to measure the spread, and individual values should not be over-read.
- **Compared with the earlier free-form run** (`full1_20261013`, re-scored with the fixed evaluator: faithfulness 0.97, relevance 0.95, recall 0.94, coverage 0.75, answers about twice as long), the concise prompt halved answer length and cost about 18% less, but did not raise the scores. Coverage improved on Q10, Q12, Q15, Q24 and Q04, and fell on Q02, Q07, Q11 and Q13. Q16's faithfulness fell from 0.97 to 0.49 and has not been inspected yet. The comparison is not like-for-like: the coverage scoring (finer-grained facts), the Q04 ground truth, and the Q14 question also changed.
- **Earlier published V2 numbers** (faithfulness 0.97, precision 0.94) were the single-fact category only, measured with different models, different ground truths, and a judge that could not see passage numbers. They are not comparable with this table.
- **Known limits:** answers are free-form prose (no structured output), the faithfulness check does not catch a wrong direction word (Q11 said a number "decreased" from 139 to 208 and still scored 1.0), and the judge has been checked on only a few hand-inspected cases so far.
