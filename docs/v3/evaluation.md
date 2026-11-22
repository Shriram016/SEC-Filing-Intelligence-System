# Spec — Evaluation

**Status:** design approved (grilling 2026-11-04 → 2026-11-19). Not built.
**Milestones:** M0 (lock the 150, start dev set), M1 (search test + baseline + runner; the label-depth comparison of Q99 is dropped, `section` is final, Q101), M3 (locked run 1), M5 (quality gate), M6 (locked run 2).
**Sources:** `docs/V3_GRILLING_LOG.md` Q4–Q13, Q21, Q37, Q57, Q70, Q71, Q78.

## 1. Purpose

Measure V3 honestly: against a human-written benchmark, against a baseline, with failures tagged by cause.

## 2. Eval sets

| Set | Contents | Use | Ref |
|---|---|---|---|
| **Locked benchmark** | All 150 open-source FinanceBench questions | Only at M3 and M6. Never used to tune anything | Q4, Q7 |
| **Held-out behaviour subset** | A small part of the dev behaviour questions (refuse, unclear, unrelated, advice, hidden instructions), unseen until M6 | Only at M6 | Q8 |
| **Dev set** | Claude drafts questions + answers from the corpus; the user checks and confirms each one. Includes refusing, unclear, unrelated, advice, injection, multi-turn and company-comparison questions | Every day while building | Q5, Q7, Q16, Q43, Q45, Q64 |

Dev set size and categories: decided at build time. Q6.

**No-leakage rule:** no tool, setting or prompt is chosen using locked questions or their evidence pages. Q21.

## 3. Baseline

- **Plain RAG only:** split, search, one LLM answer. No router, no planner, no checks. Same documents and same answering model as V3. Q9.
- **Built (M1, Q102):** top 5 chunks, no company filter, one Claude Sonnet 5.5 call (thinking off: `between_tools`). The answer is **JSON** (`found`, `answer`, `value`, `unit`, `sources`), format enforced by the API and checked by code; one retry on a broken reply. Flag for the README: a classic plain-RAG baseline answers in free text.
- **Cost controls:** without `--allow-paid` the runner only builds the prompts and prints tokens + cost; `--limit N` for a small test; a run stops above `baseline_max_cost_usd` ($2). Each run writes a new folder `experiments/m1/baseline/<time>/` (never overwrites).
- **Search test (free, M1d):** Hit@1/5/10 and MRR@10 of the evidence page, company filter on/off (`filing_rag.evaluation.retrieval`). Results: `experiments/m1d/RESULTS_search.md`.
- Published reference points (FinanceBench paper, shared store): GPT-4-Turbo vector RAG ≈ 50%; long-context ≈ 79%. Cite these in the README. The "why not long context?" question has no measured answer in V3 (known gap; optional small long-context run if time allows).

## 4. Marking

| What | How | Ref |
|---|---|---|
| Numbers | Code: the answer's `value` + `unit` vs the dev question's `gold_value` + `gold_unit` (Q103). Units converted (thousand / million / billion, %, basis points); ±1% relative; a decrease given as a positive number counts when the answer says "decrease". Questions without `gold_value` (text answers, choices) are hand-marked | Q10, Q103 |
| Search and source (code) | Page seen: every evidence page is in the chunks given to the model. Source cited: the model's `sources` name every evidence page. Wrong code-marked answer → tag `search_miss` / `answer_error` / `broken_json` | Q11, Q103 |
| Text answers | LLM judge (an **OpenAI** model, different family from Claude), fixed rubric: correct / partly correct / wrong | Q10, Q37 |
| Judge trust | User hand-marks 30–50 answers; report judge-vs-human agreement (or Cohen's kappa). Low agreement → fix the rubric before trusting scores | Q10 |
| Citations | Code: quote exists, numbers match (`engine.md` 3.5) | Q30 |
| Refusals and questions back | Code checks the route | router.md |

## 5. Failure causes (hybrid tagging)

Each dev question also has an `answer_source` tag: `table` or `text`. Report the score per group. A clearly lower score for table questions means the table format (layout text, Q88) loses information → test Docling.


1. Code auto-tags **retrieval** (evidence page retrieved?) and **parsing** (gold number present in the parsed evidence page?).
2. An LLM reads the trace and suggests **planning / generation / reasoning**.
3. The user confirms or corrects each suggested tag. Q11.
4. **Fix the cause, not the question (Q100):** a fix must target the tagged cause (search, PDF reading, answer step) for a whole group of questions. No fix for one dev question only (for example, a prompt line about one company). A fix is kept only if the dev score improves overall; the locked set shows any over-tuning.

## 6. Repeat runs

Locked results: **3 runs**, report mean with a range. A comparison is a win only when the gap is larger than the noise. Q12.

## 7. Runs that cost money

| Run | When | Ref |
|---|---|---|
| Quality gate (~20 dev questions; fail if the score drops beyond a set margin vs the last accepted run) | Built; run **manually** for now | Q70 |
| Weekly dev eval (drift check) | Built; run **manually** for now | Q57, Q71 |
| Full dev eval, load test | On demand | — |
| Locked runs (3 × 150 + judge) | M3 and M6 only | Q12 |

**Rule:** every real-AI run is manual and shows its estimated cost first. Rough estimate for both locked runs: about $45–$135 (not measured).

## 8. Reproducibility

Each run records: code version, index version, model names, prompt versions. Prompts live in versioned files. One folder per run.

## 9. README numbers

Chosen at M7 from real results. Starting candidates: FinanceBench accuracy vs plain RAG; correct-refusal rate; citation-check pass rate. Q13, Q78.

## 10. Open at build time

Dev set size and categories; judge model; quality gate margin; dev question format.
