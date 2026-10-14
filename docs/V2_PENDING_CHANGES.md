# V2 pending changes (batch list)

Rule: do **not** rerun the full 32 queries after each small change (about $0.55 and 35 minutes each time).
Collect changes here while reviewing individual questions, settle the list, then rerun once.
Baseline for comparison: `evaluation/runs/full1_20261013` re-scored with the fixed evaluator
(`rescored.json`, `summary_rescored.json`), answers produced by the original free-form prompt.

## Status (2026-10-14)

**Applied for the next full run (`full2_20261014`):** 1 and 5 (retuned concise prompt: 1-3 sentences for facts, up to 8 bullets for
comparisons, say what changed and what stayed the same, only passage facts, no "all companies" unless supported, no passage numbers),
2 (Q14 now asks how headcount changed), 3 (coverage uses `atomicity="high"`), 4 (Q04 ground truth uses the filing's definition of Google Cloud).
**Not applied:** 6 (needs the context-cap bug fixed first). Bugs 1, 3, 4 not chosen yet.
Baseline for comparison: `full1_20261013` re-scored (`rescored.json`) with the earlier scoring, free-form prompt, old Q14 and Q04 keys;
differences in scoring (atomicity, Q04 key) and the Q14 question mean those rows are not strictly like-for-like.

## Changes

| # | Change | Status | Evidence |
|---|---|---|---|
| 1 | **Concise answer style** (`ANSWER_STYLE` in `config.py`, rules in `synthesis/synthesizer.py`) | In code, **needs tuning before the rerun** | Q14: 600 words down to 106, same faithfulness and relevance. Q12: 720 words down to 137, but the model dropped AI, the main difference between the companies, so GT coverage fell 0.20 to 0.00, faithfulness 0.89 to 0.78, and it added an outside-knowledge claim ("a model Apple itself employs"). The cap "5 sentences or 6 bullets" is too tight for comparisons. Proposed: single-fact 1-3 sentences, comparisons up to 8 short bullets covering each company or year. |
| 2 | **Q14 question wording**: "How did Meta's and Microsoft's headcount change in 2023?" (keeps the verified ground truth) | Proposed, not applied | Q14 asks to "describe" the workforce; the parser routes to Item 1 (human capital) while the ground truth is headcount change from Item 7. Recall and coverage are 0.00 because the answer key fits a different question. |
| 3 | **Ground-truth coverage with finer facts** (`atomicity="high"` in the RAGAS claim splitter) so partly covered bundles earn partial credit | Proposed, to test on saved answers first (about $0.03) | Q12: the judge splits the ground truth into 5 bundled facts and fails a whole bundle if one piece is missing (one fully supported bundle gives 0.20; a fair reading is about 0.6). |

| 4 | **Q04 ground truth**: drop the marketing phrase "provides the most advanced computing infrastructure and expands access to Google's latest AI models"; keep the Vertex AI facts | Proposed, not applied | Q04: the answer defines Google Cloud correctly (a segment earning consumption-based fees and subscriptions) and fully covers the Vertex AI facts, but coverage is 0.50 because the ground truth picked one slogan-style description and the judge also nitpicked "advanced". A valid alternative description is penalised. |

| 5 | **Prompt rule against over-generalising** ("say 'all companies' only if every company's passages support it; name only the companies shown") added to the concise rules (part of change 1) | Proposed | Q18: 6 of 33 faithfulness statements failed, all of the form "all three companies..." when the Meta passages did not support the claim. The judge is right here. |
| 6 | **Per-company retrieval for queries about "companies" in general** (no company named: retrieve for each of the 5 companies instead of one pure semantic search) | Optional, behaviour change in the retriever | Q18: no company or year was extracted, so one semantic search over all 2,835 chunks returned 10 chunks: Google 5, Microsoft 4, Meta 1, none for Apple or Amazon, yet the answer says "companies". |

## Observed, no action decided

- Q18 (vague: "What do companies say about artificial intelligence?"): no ground truth, so only faithfulness (0.82) and relevance (0.86). The score is a **real signal**: the answer overgeneralises from uneven evidence (see changes 5 and 6). It never says that only 3 of the 5 companies were covered.
- Q15 (business descriptions): the answer is accurate but 647 words, drifted into competition, IP and workforce (not "business description"), and was **cut off by the 1,024-token limit mid-sentence**. Coverage 0.50: it missed Amazon's "Earth's most customer-centric company" line, "employees" in Amazon's customer list, and Google's mission statement, all from the opening of each business description. Ground truth is fine. This supports change 1 (stay on the question asked, shorter), with the Q12 warning that the length cap must not force dropping key points.
- Q12 ground truth lists specific details for an open-ended question ("compare competitive risks"); a good answer can pick other valid emphases.
- Faithfulness depends on how the judge splits the answer; repeat runs will show the spread.

- Q24 (Microsoft AI risk 2022 vs 2024): strong answer that correctly says the 2022 filing already had AI risk text and that 2024 expanded it. Coverage 0.56 (5 of 9 facts). One real omission (copyright claims over AI training and output). The other misses are partial: "ineffective AI practices cause harm" and "significant costs of AI infrastructure" and "execution risks" are each half-covered, but the judge fails a fact if any piece is absent. The ground truth bundles many items, so finer-grained facts (change 3) would give fair partial credit. One faithfulness miss: the opening "position changed" statement, which the judge reads as "more detail, not a changed position" (borderline). No ground-truth change needed.

- Q10 (Amazon business description 2020 vs 2024): coverage 0.67 (2 of 3). The answer found both changes (advertisers and employees added to the customer list; AI tools added as a competitive dimension) but never says the three-segment structure stayed the same, which is the third ground-truth fact. It is 630 words and spends most of them on trivia (executive officers, board members, Prime details, headcount), then is cut off mid-sentence in the board section. Ground truth is fine. Supports change 1, with the Q12 caution: a stricter length limit must still leave room for "what did not change". Questions of the "how did X change" type need both what changed and what stayed the same.

- Q11 (Google market risk 2021 vs 2024): coverage 0.67 (2 of 3). It has both key facts (the three risk types; the $285M to $135M change) but omits that the hedged currencies stayed the same (again a "what did not change" fact). It is 539 words with about 20 figures. **It contains a wording error the judge missed:** "The VaR decreased from $139 million in 2021 to $208 million in 2024" (139 to 208 is an increase). Faithfulness still scored 1.0, because each number appears in the passages and the judge checks support, not whether the direction word fits the numbers. This is a real limit of the faithfulness metric and a reason for the hand check of about 20 answers.

## Known V2 bugs from the audit (documented; fix only if chosen)

| Bug | Short fix | Chosen? |
|---|---|---|
| 1. Context cap drops whole companies or years | Keep every filter combination under the cap | not yet |
| 3. Refusals get confidence ~0.92 | Low or n/a confidence for refusals | not yet |
| 4. Fragile refusal string match | Tolerant check inside the pipeline | not yet |

## Review queue (low scores in the re-scored full1)

All seven reviewed: Q14, Q12, Q04, Q15, Q24, Q10, Q11, Q18.
