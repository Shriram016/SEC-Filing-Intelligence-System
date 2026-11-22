# M1 plain-RAG baseline: first dev scorecard (2026-11-21)

Run: `experiments/m1/baseline/20261121-130339/` (3-question test run: `20261121-130306/`).
Setup: top 5 chunks, no company filter, Claude Sonnet 5.5 (thinking off), JSON answers.
Cost: $0.344 for 50 questions (+ $0.021 test); median 2.1 s per question; 0 JSON retries.
Dev set status: draft (not yet checked by the user).

## Scores

| Group | Numbers correct (code) | Page in chunks | Source cited |
|---|---|---|---|
| all | 16/35 (46%) | 24/50 (48%) | 22/50 (44%) |
| table | 7/23 (30%) | 11/28 (39%) | 10/28 (36%) |
| text | 9/12 (75%) | 13/22 (59%) | 12/22 (55%) |

15 answers wait for hand marking (`text_answers_to_mark.md`).

## Why the 19 code-marked answers are wrong (checked by reading each one)

| Cause | Count | Questions | Part to fix |
|---|---|---|---|
| Search miss: the evidence page was not in the 5 chunks | 13 | 0001-04, 0007, 0009, 0016, 0019, 0032, 0035, 0039, 0041, 0045 | Search (M2 router: company + year boost; then hybrid) |
| Table cut: the page was seen, but only the first part of a split table (the needed rows were in another part) | 3 | 0005, 0038, 0043 | Chunking / retrieval of table parts |
| Question or scoring: the model gave the change in USD with the correct numbers; the gold is the % change | 2 | 0040, 0046 | Dev-set wording or accept both forms |
| Model reading: picked a nearby number (8 years, interest rate hedges, vs 23 years) | 1 | 0018 | Answer step (or question wording) |

Model behaviour: when the page was missing, it said "not found" and did not guess (no invented
numbers seen in the 19). Five answers were correct without the evidence page (the same fact is
on another page).

## Main finding

The search is the main cause (13 of 19). Fix order for M2: router + year boost, then table-part
retrieval, then hybrid keyword search only if needed.
