# Evaluation archive

Old evaluation files, kept for the record and moved here during the V2 polish
(see `docs/V2_POLISH_PLAN.md`, step 1.4). Nothing was edited or deleted.
**Do not quote numbers from these files as V2 results.**
File names are not always accurate, so this table says what each file really holds.

| File | What it is |
|---|---|
| `eval_results.json` | V1 run: 10 queries, `llama-3.1-8b-instant`, 2026-05-03. |
| `eval_queries.json` | The V1 question set (10 queries). V2 uses `evaluation/eval_queries_v2.json` (24 queries). |
| `eval_results_v2.json` | A partial run with **1 query** only (2026-06-29 00:08), Scout 17B pipeline. It overwrote the full results file, so this is **not** the 24-query result. Identical to the judgebug backup below. |
| `eval_results_v2_backup_scout17b_judgebug.json` | Copy of the same 1-query run, saved before the eval-judge fix. |
| `eval_results_v2_backup_8b.json` | Despite the name, this is **3 queries** on the Scout 17B model (2026-06-28 23:16), not an 8B run. |
| `eval_checkpoint.json` | All 24 queries from the latest full run. It holds scores only, not the retrieved texts, so scores cannot be re-checked. It comes from a later rerun, so its numbers differ from the table in `evaluation/EVAL_REPORT_V2.md`. |

The published V2 table in `EVAL_REPORT_V2.md` comes from the log
`eval_full_run_scout17b_judgefix.log`, which step 1.8 saves under `archive/evidence/`.
