# V2 Polish — Plan & Tracker

## Goal

Make V2 **honest, measurable and checkable**, then freeze it as the tagged baseline `v2-baseline`.
`v2-baseline` is the frozen, honest final state of V2. V3 is a separate project on its own `v3` branch (see `docs/V3_DESIGN.md`) and links to this tag from its README. It is not measured against V2, because its baselines are plain-RAG and long-context.

The bar this work targets: *visible judgment under failure*:
1. failure modes designed against, not just patched
2. evaluation split by failure type, not one blended number
3. an explicit rejected alternative, backed by measured evidence
4. contact with something messier than a curated demo (real users, real data)

---

## Rules for this track

- **The pipeline's default behaviour does not change.** New switches are allowed, but their defaults must reproduce today's behaviour exactly.
- **Known bugs are documented, not fixed.** They are fixed in V3, so the fix shows up as a measured before/after.
- **The user runs every script**, in the `E:/rag_env` environment. Claude writes the code and says what to run.
- **Old eval JSON files are only moved to `evaluation/archive/`.** Never deleted or overwritten.
- One commit per stage, made only after the user approves.
- Branch: stay on `version2`. No merge to `main`.

---

## Status

| Stage | Description | Status |
|---|---|---|
| 1 | Clean-up | ✅ All 9 steps done 2026-10-08. Committed as `f59e987` on `version2` (not pushed) |
| 2 | Tests and experiments | ✅ Committed 2026-10-14 (partly): step 2.0 metrics guide, 2.1 evaluator rebuilt, 2.2 refuse queries, 32-query runs `full1` and `full2` with `evaluation/EVAL_RESULTS_LATEST.md`. **Deferred:** 2.3 reranker/prompt switches (only `ANSWER_STYLE` done), 2.4 three repeat runs, 2.5 reranker ablation, 2.6 refusal stability, 2.7 failure analysis, hand check of ~20 answers. Open changes in `docs/V2_PENDING_CHANGES.md` |
| 3 | Honest docs | ⏳ Not started |
| 4 | Put the app online | ⏳ Not started |
| 5 | Freeze (`v2-baseline` tag) | ⏳ Not started |

---

## Audit findings (2026-10-03) — why this track exists

### Claims vs evidence

| Claim | What the repo actually shows |
|---|---|
| Faithfulness 0.97, Context Precision 0.94 | These are the **single-factual** category only (6 of 21 scored queries). Overall: faithfulness **0.762**, answer relevance 0.921, precision **0.514**, recall 0.944. |
| 24-query eval results are committed | `eval_results_v2.json` holds **1 query** (overwritten by a later partial run). The published table comes from `eval_full_run_scout17b_judgefix.log`, which is gitignored. The committed checkpoint reflects a later rerun with different scores. |
| Per-combo sub-query reranking fixed multi-hop refusals | **Not supported by the logs.** Q08 at 21:03 and 21:11 on 2026-06-28 had the same model, same 20 chunks, same order and same reranker scores (top 0.170). One refused, one answered. The cause is the synthesizer prompt line *"For comparison queries, synthesize…"* or run-to-run randomness, not the reranker. Q08's top score went 0.066 → 0.170, not "0.06 → 0.58+". |
| Before/after numbers for the multi-hop fix | The "after" run changed four things at once: reranking, synthesizer prompt, model (8B → Scout 17B) and an eval-judge fix. The effect can't be credited to any single change. |
| Reranker improves context precision | Never measured with the reranker on vs off. With ≤3 combos, every chunk reaches the LLM anyway; the reranker only changes their order, and RAGAS precision rewards order. |
| Multi-hop decomposition | It's filter extraction plus one sub-query template, searched in parallel. No step depends on an earlier step's answer. |
| Conflict detector runs 200 comparisons | 200 is the number of *possible* pairs. The UI runs one company and one section on demand. No full scan was ever logged. |
| Streamlit Community Cloud app | Did not exist. `chroma_db/` and `data/processed/` are gitignored, so the app can't run from a clone. |
| 0.4 / 0.6 confidence weights | Implemented, but `config.py` still marks them "TBD — tune". Never tuned or validated. |

### Known bugs (frozen in the baseline, to be fixed in V3)

1. **The context cap drops whole combinations.** After per-combo reranking, chunks are joined combination by combination, but `synthesizer.py` keeps `chunks[:30]` as if they were sorted globally. With 4 or more combos, the last company or year is cut entirely (e.g. Q14: 40 retrieved, 30 used).
2. **The conflict detector reads only part of each section.** `MAX_WORDS_PER_YEAR = 3500`. All 25 Item 1A sections are longer (median 10,196 words; longest 30,039), and so are 21/25 Item 7 and 14/25 Item 1 sections. A risk reported as "removed" may just be past the cut-off.
3. **Refusals show high confidence.** `scorer.py` sets faithfulness = 1.0 for the refusal string, so a refusal gets one of the highest confidence scores.
4. **The refusal check is a fragile string match.** It looks for the exact refusal sentence; a reworded refusal isn't detected.

### Repo hygiene issues

- The GitHub default branch `main` is the May version (no reranker, no Langfuse).
- Stray eval files: a 1-query results JSON, `*_backup_8b.json` and `*_judgebug.json`.
- Stale docs: `EVAL_PIPELINE.md` (8B model, single merged-pool rerank); the unused `SIMILARITY_THRESHOLD` in `config.py`; a placeholder clone URL in the README.
- Only 3 of 12 test files are pytest-style. Most need the local index or a Groq key. No CI.
- `requirements.txt` isn't pinned and doesn't match the code (`ragas>=0.2.0`, but the code needs the 0.4.3 API; `langfuse>=2.0.0`, but the code uses the v4 decorator). It also lists packages that look unused (scikit-learn, langchain-groq, datasets).
- `.claude/settings.local.json` is tracked.
- The eval throws away the retrieved chunk texts, so no score can be re-checked.
- The private `INTERVIEW_PREP.md` still tells the V1 story (10 queries, 0.83/0.94, "reranker not needed").

---

## Decisions (2026-10-04)

| Question | Decision |
|---|---|
| Old eval JSON files | Move to `evaluation/archive/` with a note explaining each one |
| "Should refuse" questions | Add 6–8 in-domain unanswerable questions as a new category |
| On/off switches for experiments | Yes. Defaults = today's behaviour |
| Deploy to Streamlit Cloud | Yes, with a daily question limit |
| Private interview notes | Claude updates them at the end, after numbers are final |
| Work order | Clean-up → tests/experiments → docs → deploy → tag |
| Branch | Stay on `version2`; user switches GitHub's default branch to `version2` |
| V3 | Already designed separately in `docs/V3_DESIGN.md`. Lives on a `v3` branch. V2 polish does not touch it, and no V3 file goes in a V2 commit |
| Plan file visibility (Q1, 2026-10-08) | Keep `docs/V2_POLISH_PLAN.md` public |
| Eval judge model (Q2, 2026-10-08) | Decide later, before step 2.4 |
| Eval metrics (2026-10-08) | New step 2.0: learn the metrics and choose them per query kind before changing the eval |

---

## Stage 1 — Clean-up

| # | Step | Files | Who | Status |
|---|---|---|---|---|
| 1.1 | Pin package versions: the user runs `pip freeze` in `rag_env` and shares the output; Claude keeps only the packages the code uses | `requirements.txt` | User + Claude | ✅ 2026-10-08 (12 direct packages pinned) |
| 1.2 | Remove the unused `SIMILARITY_THRESHOLD` | `config.py` | Claude | ✅ 2026-10-08 |
| 1.3 | Stop tracking the local Claude settings file (`git rm --cached`; the file stays on disk) | `.claude/settings.local.json` | Claude | ✅ 2026-10-08 (already covered by `.gitignore`; no edit needed) |
| 1.4 | Move old result files to an archive folder, with a README saying what each was. The "before" analysis report stays in place as evidence | `evaluation/archive/` (new): `eval_results.json`, `eval_queries.json`, `eval_results_v2.json`, `eval_results_v2_backup_8b.json`, `eval_results_v2_backup_scout17b_judgebug.json`, `eval_checkpoint.json` | Claude | ✅ 2026-10-08 (git mv; README corrects misleading names: the "8b" backup is 3 Scout queries; the checkpoint holds all 24) |
| 1.5 | Convert tests to pytest; split into offline (no API key or index) and integration (needs both) | `tests/offline/`, `tests/integration/`, `tests/fixtures/`, `pytest.ini` | Claude | ✅ 2026-10-08 (scoped down): 32 offline pytest tests pass (parser, section detector, chunker, tagger, conflict analyzer; tiny fixtures/inline inputs). The 11 old script-style tests were MOVED to `tests/integration/` and are excluded from pytest collection (`conftest.py`); converting them to real pytest functions is future work, not done. Old `tests/test_conflict_analyzer.py` removed (superseded) |
| 1.6 | GitHub Actions: run offline tests on every push | `.github/workflows/ci.yml` | Claude | ✅ 2026-10-08 written (Python 3.13, CPU torch, pip cache). Not yet run on GitHub; first run happens when the branch is pushed |
| 1.7 | One script that builds everything from scratch (download → index), plus an example env file (Groq required, Langfuse optional) | `scripts/build_index.py`, `.env.example` | Claude | ✅ 2026-10-08 written; `--help` works. Full run not tested (downloads from SEC, 10–15 min); user can run it as a no-op check since all outputs exist |
| 1.8 | Save the evidence that is currently gitignored, so the published numbers and the reranker postmortem can be checked: the log behind the published table, the Q08 query logs that disprove the reranker fix (2026-06-28 12:06, 21:03, 21:11, 23:25), and the "before" full-run log | `evaluation/archive/evidence/` (new): `eval_full_run_scout17b_judgefix.log`, `eval_full_run.log`, `logs/query_20260628_120627.log`, `query_20260628_210318.log`, `query_20260628_211155.log`, `query_20260628_232534.log` | Claude | ✅ 2026-10-08 (6 logs scanned clean and copied byte-identical; README added. Finding: Q08 also refused on Scout at 23:25, and the 21:03/21:11 runs were on the 8B model) |
| 1.9 | Make sure new run logs can be committed: add a `.gitignore` exception for `evaluation/runs/**/*.log` and `evaluation/archive/evidence/*.log` (today `*.log` is ignored everywhere) | `.gitignore` | Claude | ✅ 2026-10-08 (verified: evidence logs show as new in git status; other logs still ignored) |

---

## Stage 2 — Tests and experiments

| # | Step | Files | Who | Status |
|---|---|---|---|---|
| 2.0 | **Eval learning session (do this first; it decides 2.1–2.7).** Together, one small piece at a time: (a) list the kinds of queries the system should handle (single fact, comparison, change over time, vague, should-refuse, out-of-domain); (b) learn how each RAGAS metric works, in simple words, using real examples from our own logs; (c) for each query kind, decide which metrics to use and which to drop; (d) decide what is missing (e.g. an answer-correctness check, a refusal metric, chunk-ID labels for exact precision/recall); (e) check suspicious scores (Q14 precision 0 but recall 1; Q23 relevance 0; recall always 1.0) by reading the RAGAS source and our logs. Output: a one-page table "query kind → metrics to use → why". No code is written until the table is approved | `docs/EVAL_METRICS_GUIDE.md` (new) | User + Claude | ⏳ |
| 2.1 (progress 2026-10-13) | Code written, NOT yet run against Groq: `evaluation/ragas_evaluator.py` rewritten (run folder, full record, token logging from Groq replies, FactualCorrectness in recall mode, yes/no checks, tolerant refusal check, `--dry-run`, resume) + `evaluation/eval_helpers.py` + 19 offline tests (51 pass). 3-query live test PASSED 2026-10-13 (run `test3_20261013`, cost $0.047). Models changed because Groq retired the V2 models: pipeline `qwen/qwen3.8-27b`, judge `openai/gpt-oss-120b` (new `JUDGE_MODEL`), conflict detector placeholder `qwen/qwen3.8-27b` (untested). Should-refuse passes on any decline. Full run #1 done (`full1_20261013`, $0.549). Evaluator then fixed 2026-10-14: judge sees numbered passages; `factual_correctness` replaced by `ground_truth_coverage` (see `docs/EVAL_METRICS_GUIDE.md`); per-statement verdicts saved. Next: re-score saved answers, chase odd scores, hand-check ~20 answers, 3 full runs. Original row: Eval saves the full record per query: retrieved texts, reranker scores, extracted filters, sub-query template, the app's confidence score, models and git commit. Each run gets its own folder; no overwrites | `evaluation/ragas_evaluator.py`, `evaluation/runs/<run_id>/` | Claude | ⏳ |
| 2.2 | Add 6–8 "should refuse" questions (e.g. a year not in the data, an unindexed section, numbers only in tables). Scored separately: did it refuse, and what confidence did it show? | `evaluation/eval_queries_v2.json` | Claude | ⏳ Part done 2026-10-08: 8 should-refuse queries (Q25–Q32) added after checking each against the filing text; first 24 unchanged. Q22–Q24 relabelled `conflict_triggering` → `cross_year` (cross_year now 8). Still open: make the evaluator handle the new `should_refuse` type (step 2.1) |
| 2.3 | On/off switches: reranker = `per_combo` (default) / `original` / `off`; comparison prompt line = on (default) / off | `config.py`, `retrieval/retriever.py`, `synthesis/synthesizer.py` | Claude | ⏳ |
| 2.4 | Full eval run 3 times, to measure how much scores move between runs | `evaluation/runs/` | User | ⏳ |
| 2.5 | Reranker experiment: 12 multi-hop questions (Q07–Q15, Q22–Q24) × 3 reranker settings × 3 repeats | `evaluation/experiments/rerank_ablation.py` | Claude writes, user runs | ⏳ |
| 2.6 | Refusal stability: the 6 previously refused questions (Q08, Q10, Q13, Q15, Q23, Q24) × 5 runs × prompt line on/off. No judge needed | `evaluation/experiments/refusal_stability.py` | Claude writes, user runs | ⏳ |
| 2.6b | Save all experiment results with a short summary table, so the docs in Stage 3 can quote them | `evaluation/experiments/RESULTS.md` | Claude | ⏳ |
| 2.7 | Failure-cause labels for every low-scoring answer, checked against the filing text. Causes: wrong refusal / judge error / retrieval miss / combo cut by cap / unsupported claim / wrong year attributed | `evaluation/FAILURE_ANALYSIS.md` | Claude drafts, user approves | ⏳ |

---

## Stage 3 — Honest docs

| # | Step | Files | Status |
|---|---|---|---|
| 3.1 | README: overall and per-category scores with run-to-run spread; refusal results; "Known failures" section (the 4 bugs above plus the untuned weights); honest conflict-detector description; real clone URL; live-app link | `README.md` | ⏳ |
| 3.2 | Design decisions: what was chosen, what was rejected, why, and measured evidence where Stage 2 provides it. Covers LlamaIndex, the similarity pre-filter, claim-level citations, the reranker (skipped in V1, added in V2), and per-combo vs original-question reranking | `DECISIONS.md` (new) | ⏳ |
| 3.3 | Reranker postmortem: symptom → wrong first theory → what the logs showed → what the experiments proved | `docs/RERANKER_POSTMORTEM.md` (new) | ⏳ |
| 3.4 | Bring outdated docs up to date | `evaluation/EVAL_PIPELINE.md`, `evaluation/EVAL_REPORT_V2.md` | ⏳ |
| 3.5 | Fix smaller README contradictions: "Python 3.10+" vs `requirements.txt` "Python 3.13 compatible"; "Item 8 tables planned for v2" (not done; move to a future/V3 note) | `README.md` | ⏳ |
| 3.6 | Update the private session file, which is badly out of date: the "New Session Prompt" says 8B model, 0.83 scores and "project COMPLETE"; Component 9 still says reranker skipped; the build table shows V2-1 "In Progress"; the tech stack says "No RAGAS library"; folder structure and config block are old. A new session reading it would be misled | `CLAUDE.md` (gitignored) | ⏳ |

---

## Stage 4 — Put the app online

| # | Step | Files | Who | Status |
|---|---|---|---|---|
| 4.1 | Daily question limit in the app; Groq console spending limit as a backup. The limit must also cover the Conflict Explorer, whose calls use the larger 70B model and cost the most | `ui/app.py` | Claude + user (Groq setting) | ⏳ |
| 4.1b | Langfuse in the online app: either add the keys to Streamlit secrets, or confirm the app runs fine with tracing switched off | `ui/app.py`, Streamlit secrets | Claude + user | ⏳ |
| 4.2 | Ship the search index with the repo (`chroma.sqlite3` is 46 MB, under GitHub's 100 MB file limit), plus `_sections.json` (4.5 MB) for the conflict detector | `.gitignore`, `chroma_db/`, `data/processed/*_sections.json` | Claude | ⏳ |
| 4.3 | Deploy on share.streamlit.io; Groq key in Streamlit secrets | — | User (Claude gives steps) | ⏳ |

**Risk:** Streamlit's free tier has limited memory, and the BGE embedder plus reranker need about 1.1 GB. If the app crashes, come back with options before changing anything.

---

## Stage 5 — Freeze

| # | Step | Who | Status |
|---|---|---|---|
| 5.1 | Update `INTERVIEW_PREP.md` (private) to the real numbers and the honest reranker story | Claude | ⏳ |
| 5.2 | Tag `v2-baseline` and push the tag | Claude, after user approval | ⏳ |
| 5.3 | Change GitHub's default branch to `version2` (Settings → Branches) | User | ⏳ |
| 5.4 | Correct the career notes outside this repo that repeat the overclaims (0.97/0.94 as headline numbers, "200 comparisons", "Streamlit on Community Cloud"): `PROFILE-INVENTORY.md` and the portfolio critique in `E:\Personal Learning\Personal Career Plan\` | User (Claude can draft the wording) | ⏳ |

---

## Open questions (to answer before the relevant stage)

| # | Question | Needed by |
|---|---|---|
| Q1 | ✅ Answered 2026-10-08: keep public | — |
| Q2 | (Still open, decide before 2.4) Should the eval judge switch to a non-Llama model on Groq, to reduce "same model family" bias? Trade-off: new numbers would no longer be directly comparable with the published V2 table | Before step 2.4 |

---

## Cost notes

- Most Groq usage comes from 2.4 (3 full eval runs) and 2.5 (the judge scoring multi-hop answers).
- 2.6 is cheap because it uses no judge.
- A full eval run takes about 20–30 minutes.
