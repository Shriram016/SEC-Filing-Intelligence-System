# Evaluation metrics guide (V2)

How the V2 evaluation scores answers, which metric applies to which kind of question, and why one
metric is not the stock RAGAS number. Code: `evaluation/ragas_evaluator.py`, `evaluation/eval_helpers.py`.

## What is evaluated

32 queries in 6 categories (`evaluation/eval_queries_v2.json`):

| Category | n | Kind of question |
|---|---|---|
| single_factual | 6 | One fact or topic from one filing |
| cross_year | 8 | Change over time for one company |
| cross_company | 4 | Compare companies in one year |
| vague | 3 | Broad question, no ground truth |
| should_refuse | 8 | In the domain, but the data cannot answer it |
| invalid | 3 | Not about SEC filings at all |

**Ground truths** were checked against the filing text. Rule: a ground truth contains only what the
question asks for, as the filing states it, with no interpretation. Three were rewritten after the audit
(Q08, Q24: the old text wrongly said Microsoft's 2022 filing had no AI risk section; Q14: one fact was
outside the indexed section) and seven were trimmed to the question's scope.

## Which metric for which category

| Category | Faithfulness | Answer relevance | Context precision | Context recall | Ground-truth coverage | Yes/no check |
|---|---|---|---|---|---|---|
| single_factual | yes | yes | yes | yes | yes | |
| cross_year | yes (read with care) | yes | no | yes | yes | |
| cross_company | yes (read with care) | yes | no | yes | yes | |
| vague | yes | yes | no | no | no | |
| should_refuse | no | no | no | no | no | declined? |
| invalid | no | no | no | no | no | rejected? |

Precision is skipped for comparisons because retrieval fetches 10 chunks per year or company and only a
few matter, so the score is low by design. Vague questions have no ground truth.

## The metrics

| Metric | Question it answers | How it is computed |
|---|---|---|
| **Faithfulness** (RAGAS) | Is every claim in the answer backed by the retrieved passages? | A judge LLM splits the answer into statements and checks each against the passages. Score = supported statements / all statements. |
| **Answer relevance** (RAGAS) | Is the answer on topic? | The judge writes questions the answer could be replying to; score = similarity (BGE embeddings) with the real question. A vague or refusing answer scores 0. It does **not** check correctness. |
| **Context precision** (RAGAS, with reference) | Are the useful chunks ranked first? | The judge marks each retrieved chunk useful or not, in rank order; rank-aware average precision. |
| **Context recall** (RAGAS) | Did retrieval fetch everything needed? | Share of ground-truth statements that can be found in the retrieved passages. |
| **Ground-truth coverage** (RAGAS claim checking, our aggregation) | Does the answer contain the ground-truth facts? | See below. |
| **Yes/no checks** (plain code) | Did the system decline when it should? | See below. |

The judge is shown the **same numbered passages the answering model saw** (`[1] Meta | 2023 | MD&A`
followed by the text). Answers often cite "Passage [2]"; without the numbers the judge cannot verify
those statements and faithfulness drops for reasons unrelated to answer quality.

## Ground-truth coverage (why it is not RAGAS FactualCorrectness)

**Definition:** split the ground truth into small facts; for each fact ask the judge whether the answer
supports it; score = supported facts / all facts. RAGAS's own claim-splitting and checking prompts are
used (`FactualCorrectness._decompose_and_verify_claims`, a private method, so `ragas` is pinned to 0.4.3).
Only the final arithmetic is ours.

**Why not the stock number.** RAGAS `FactualCorrectness(mode="recall")` computes
`TP / (TP + FN)`, where TP = the *answer's* claims supported by the ground truth and
FN = ground-truth claims the answer misses. When the answer is more precise than a short ground truth
(for example "$134,902 million (or $134.90 billion)" against "$134.90 billion"), the judge can mark every
answer claim unsupported. TP is then 0, FN is 0, and the score is 0 / 0 = **0.0 even though every
ground-truth fact is covered**.

**Evidence (Q05, Meta revenue and net income, same answer, same judge):**

| Attempt | Answer claims vs ground truth (TP) | Ground-truth facts found in answer | RAGAS recall | Coverage |
|---|---|---|---|---|
| 1 | 0 of 2 supported | 2 of 2 | 0.00 | 1.00 |
| 2 | 2 of 2 supported | 2 of 2 | 1.00 | 1.00 |

Coverage was stable; the stock score flipped between 0.0 and 1.0. The per-fact verdicts are saved in
`results.json` (`metric_details`) so any score can be re-checked.

**Limits:** a wrong extra claim in the answer is not penalised here (faithfulness covers invented claims),
and the score depends on how the judge splits the ground truth.

## Yes/no checks (should_refuse and invalid)

RAGAS metrics score a good answer built from retrieved text; a correct refusal has none, so they do not
apply. Instead:

- **invalid:** pass if the query parser rejected it.
- **should_refuse:** pass on any decline, either the synthesizer's refusal or a parser rejection (for
  example "Year 2019 is not available"). The outcome (`refused` / `rejected` / `answered`) is recorded.
- **Refusal detection:** the pipeline's exact sentence, plus tolerant wording ("cannot answer",
  "not mentioned in the provided context", ...). Answers that refuse and then keep talking are flagged
  `with_extra_text` for a manual read. The 8 should-refuse answers are read by hand once after the final run.
- The app's **confidence score** is recorded for every answered query, including refusals.

**Evidence for the numbered passages (Q05, same answer, three attempts after the change):** faithfulness was
1.00 every time, even when the judge split the answer into 8 or 6 statements (including the "Passage [N]
states..." ones). Before the change the same answer scored 1.00 on one attempt and 0.33 on another. The
number of facts the judge extracts from the ground truth can still vary (2, 2, 1 here), but coverage stayed 1.00.

## Judge setup and reliability

- Pipeline model `qwen/qwen3.8-27b`; judge `openai/gpt-oss-120b` (a different model family). Groq retired
  the original V2 models, so earlier V2 numbers cannot be reproduced.
- LLM judges are noisy. Same input, same judge, different run: Q05 faithfulness was 2/2 on one attempt and
  2/6 on the next, because the judge sometimes turned the answer's "Passage [2] states..." lines into
  extra statements. Mitigations: numbered passages for the judge, three repeat runs to measure spread,
  and a hand check of about 20 answers against the judge.
- Counts and individual values are reported next to means; with 3 to 8 queries per category a mean alone
  is not meaningful.

## Known limits

- Answers are free-form prose; the prompt asks for no format, length, or citations (V3 item: structured output).
- Faithfulness weighs every statement equally and depends on how the judge splits the answer.
- Scores are from an LLM judge validated on a small hand-checked sample, not a large labelled set.
