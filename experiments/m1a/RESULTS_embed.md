# M1a step 5 — embedding model test (2026-11-19)

Corpus: all 493 pages of the 5 test documents (Adobe 10-K, JPMorgan 10-Q, Lockheed 8-K, Ulta earnings, Walmart annual report). None is used by a locked question. Text: pdfplumber layout text, spaces collapsed.
Chunks: "small" = 1,276 chunks of ~280 words; "page" = 493 chunks, one per page (median ~700 tokens).
Questions: 40 (20 table, 15 text, 5 hard paraphrase), written by Claude, frozen before any run (sha256 `0277b248…60acf9`). Hit = a top-k chunk contains the answer text (and is on the given page, if set).
Search: exact cosine in numpy (no vector store). GPU: RTX 3060, fp16. Scripts: `build_chunks.py`, `test_embed.py`.

## Scores (search over all 5 documents)

| Model | Chunks | Hit@1 | Hit@5 | Hit@10 | MRR@10 |
|---|---|---|---|---|---|
| bge-base-en-v1.5 | small | 30.0% | 55.0% | 67.5% | 0.420 |
| bge-base-en-v1.5 | page | 30.0% | 55.0% | 72.5% | 0.442 |
| bge-m3 | small | 35.0% | 55.0% | 67.5% | 0.440 |
| bge-m3 | page | 35.0% | **57.5%** | 67.5% | **0.453** |
| Qwen3-Embedding-0.6B | small | 30.0% | 52.5% | 60.0% | 0.379 |
| Qwen3-Embedding-0.6B | page | 32.5% | 55.0% | 65.0% | 0.413 |

Hit@5 by question type (small / page chunks):

| Model | Table | Text | Hard |
|---|---|---|---|
| bge-base | 55 / 50 | 47 / 53 | 80 / 80 |
| bge-m3 | 55 / 60 | 47 / 47 | 80 / 80 |
| Qwen3-0.6B | 60 / 65 | 33 / 40 | 80 / 60 |

The company filter changed nothing: every question names the company, so search already stays in the right document.

## Cost to run

| Model | Vector size | GPU memory | Speed (small chunks) | Speed (page chunks) | Est. full corpus ¹ | Chunks cut by input limit |
|---|---|---|---|---|---|---|
| bge-base | 768 | 0.6 GB | 210 /s | 178 /s | ~10 min | 71 of 1,276 small; **388 of 493 pages** (limit 512 tokens) |
| bge-m3 | 1,024 | 1.9 GB | 63 /s | 28 /s | ~30 min | 0 |
| Qwen3-0.6B | 1,024 | 3.9 GB | 15 /s | 8 /s | ~2 h | 0 |

¹ Rough: ~100k small chunks for 360 documents (not measured).

## Findings

1. **No clear winner.** All models score 52.5–57.5% Hit@5. With 40 questions, one question = 2.5 points, so these gaps are within noise.
2. **The scores are low for all models, and part of the cause is not the model:**
   - *Strict hit rule / unclear questions:* at least 2 misses are acceptable answers in other words (x11: Adobe "Competition" section; t02: Walmart International sales for "revenue outside the US").
   - *Two-column pages:* x08 (Walmart transfer agent) and x10 (JPMorgan new TDRs) sit on pages where layout text mixes the two columns, so the passage is broken. Same issue as in the reader test.
   - *Neighbouring pages:* e.g. t07 finds the tax note on page 85; the table is on page 86. A table split from its title/explanation is hard to find.
   - *Questions about a number in a big table:* the number itself is not in the question, so search depends on row and header words.
3. **Long input matters for bge-base:** with one chunk per page it cuts 79% of pages (only the first 512 tokens are seen). bge-m3 and Qwen3 cut nothing.
4. **Speed and size differ a lot:** bge-base is ~14× faster than Qwen3 and uses ~7× less GPU memory. bge-m3 is in the middle.
5. **Qwen3 is weakest on text questions** (33–40%) in this test, although it is the strongest on public benchmarks. Benchmarks ≠ our documents.
6. **Not tested here:** bge-m3 sparse vectors (hybrid search), a reranker, the real chunk method (M1b), table labels. These are likely to matter more than the choice between these 3 models.

## Limits of this test

40 questions, 5 documents, questions written by Claude (who had seen the pages). Good enough to reject a clearly bad model; not good enough to rank close models. The M1c dev set (user-confirmed) is the stronger check.
