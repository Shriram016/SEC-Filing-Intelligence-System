# Evidence logs

Copies of run logs that git ignores (`*.log`), saved so the published numbers and the
reranker story can be checked. Originals are untouched. Copied during V2 polish step 1.8.
No secrets or personal data were found in these files (scanned before copying).

## Full evaluation runs (24 queries, RAGAS 0.4.3)

| File | What it is |
|---|---|
| `eval_full_run.log` | Earlier full run. Overall: faithfulness 0.456, relevance 0.860, precision 0.592, recall 0.528. |
| `eval_full_run_scout17b_judgefix.log` | The run behind the published table in `evaluation/EVAL_REPORT_V2.md`. Overall: faithfulness **0.762**, relevance 0.921, precision **0.514**, recall 0.944. Single-factual only: faithfulness 0.972, precision 0.935. The headline 0.97 / 0.94 numbers are that one category, not the overall result. |

## Query Q08 logs ("How did Microsoft's risk factor disclosures around AI evolve from 2022 to 2023?")

| File | Model | Reranking | Outcome |
|---|---|---|---|
| `query_20260628_120627.log` | llama-3.1-8b-instant | one merged-pool rerank (before the fix) | Refused. Top reranker score 0.0658. |
| `query_20260628_210318.log` | llama-3.1-8b-instant | per-combo sub-query rerank | Refused. Top reranker score 0.1700. |
| `query_20260628_211155.log` | llama-3.1-8b-instant | per-combo sub-query rerank | Answered. Same top score 0.1700. |
| `query_20260628_232534.log` | llama-4-scout-17b | per-combo sub-query rerank | Refused. Top reranker score 0.1700. |

The 21:03 and 21:11 runs have the same model, the same reranker scores and the same chunk
order, yet one refused and one answered. So the per-combo reranker alone does not explain
the change from refusing to answering. Run-to-run randomness or the synthesizer prompt line
("For comparison queries, synthesize...") are the candidates. Steps 2.5 and 2.6 of
`docs/V2_POLISH_PLAN.md` test this directly.
