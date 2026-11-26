# Q111 results: reranker, free search test (2026-11-26)

Script: `experiments/m3/reranker/search_test.py`. Raw: `search_test.json`, `search_test.md`, log.
Plans: the real router steps of the Q110 router check (`experiments/m3/router_check/20261126-103711`),
no LLM call. Collection `chunks_v2`, top 5 per step + split-table parts (as in the engine).
GPU: RTX 3060, fp16.

| Config | Gold page in chunks | All gold pages | Rerank s/step (median, max) |
|---|---|---|---|
| none (today) | 36/50 | 35/50 | - |
| bge-reranker-base @20 | 38/50 | 38/50 | 0.09, 0.13 |
| bge-reranker-base @50 | 35/50 | 34/50 | 0.19, 0.24 |
| bge-reranker-base @100 | 37/50 | 36/50 | 0.35, 0.43 |
| bge-reranker-v2-m3 @20 | 38/50 | 37/50 | 0.27, 0.32 |
| bge-reranker-v2-m3 @50 | 41/50 | 39/50 | 0.59, 0.73 |
| **bge-reranker-v2-m3 @100** | **43/50** | **40/50** | 1.09, 1.34 |

Ceiling: a gold page is in the top 100 vector candidates for 49/50.

## Reading

- `bge-reranker-base` is not stable: more candidates give a worse score at 50. Not used.
- `bge-reranker-v2-m3` gains with more candidates: +5 at 50, +7 at 100.
- Gains (v2-m3 @100): dev_0004, 0014, 0015, 0016, 0024, 0029, 0044, 0045, 0049 (9).
- Losses (every reranker): dev_0001, dev_0030 (2). The vector search had them in the top 5.
- Time: about 0.6 s (50) or 1.1 s (100) per step on the GPU; a 2-step question doubles it.
  Today a question takes about 5–6 s end to end.
- Caution: 50 questions; 41 vs 43 is a difference of 2 questions.

## Decision (user, 2026-11-26)

Reranker on by default: `bge-reranker-v2-m3`, 100 candidates. No more on/off tests. Off switch:
`FILING_RAG_RERANKER_MODEL=""` (for a server without a GPU; server option decided in M5).
