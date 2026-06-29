# SEC RAG V2 — Implementation Plan

## Current State (V1 Baseline)

| Metric | V1 Score | Status |
|---|---|---|
| Faithfulness | 0.83 | Good — should not regress |
| Answer Relevance | 0.94 | Strong — should not regress |
| Context Precision | 0.68 | Weak — primary V2 target |
| Context Recall | 0.83 | Good — no intervention needed |

Pipeline: query → Groq filter extraction → Cartesian product → ChromaDB dense retrieval → top-10 to synthesizer → scorer
Corpus: 2,835 chunks across 25 SEC 10-K filings (5 companies x 5 years)

---

## V2 Scope — 3 Items

| # | Item | Type | Target |
|---|---|---|---|
| 1 | Reranker + dynamic cap + eval rerun | Implement | Context precision 0.68 → 0.80+. Steps 1–5 done. Step 6 (eval rerun) blocked by Groq TPD limit. Detailed to-do in `V2_ITEM1_TODO.md`. |
| 2 | Langfuse instrumentation | ✅ Complete | Full observability over every LLM call. `@observe()` on all pipeline functions, `pipeline.py` wrapper, E2E test 2/2 pass. Detailed to-do in `V2_ITEM2_TODO.md`. |
| 3 | Learn-only topics (HyDE, HNSW) | Study | Document concepts and trade-offs in learning.md |
| 4 | Learn Langfuse for debugging & monitoring | Study | How to use Langfuse traces to debug bad queries, monitor pipeline health, and identify bottlenecks. Document in learning.md |

---

### Item 1 — Reranker + Dynamic Cap + Eval Rerun

All retrieval quality improvements bundled together. Detailed implementation to-do in `V2_ITEM1_TODO.md`.

**Goal:** Improve context precision from 0.68 to 0.80+

**Three sub-parts:**

**1A. Cross-Encoder Reranker**

Why: V1 uses cosine similarity only — a rough ranking that compares query and chunk as separate vectors. 32% of retrieved chunks are irrelevant (precision = 0.68). A cross-encoder reads query and chunk together as one input, producing much more accurate relevance judgments.

V1 context: Component 9 was skipped because metadata pre-filtering + BGE asymmetric retrieval produced clean pools. The 0.68 precision score proved this was insufficient.

Key design decisions:
- Reranker applies **once on the merged pool**, not per combination
- Reranker **only reorders**, does not decide how many to keep
- **TOP_K stays at 5** per combination — no pool widening
- Model: `BAAI/bge-reranker-base` (CPU, ~550MB)
- New file: `retrieval/reranker.py`

How the cross-encoder scores:
```
Input:  [CLS] query text [SEP] chunk text [SEP]
        ↓
Full transformer attention across both texts
        ↓
Output: single relevance score (raw logit, not 0–1)
        Higher = more relevant
```

**1B. Dynamic Context Cap**

Why: Synthesizer has `MAX_CONTEXT_CHUNKS = 10` hardcoded. A 6-combination query retrieves 30 chunks but only 10 reach the LLM — 4 combos get zero representation. A 1-combination query sends all 5, which is fine. Fixed cap doesn't scale with query complexity.

Design decision — two controls:
```
actual chunks sent = min(combinations × TOP_K, MAX_CONTEXT_CHUNKS)
MAX_CONTEXT_CHUNKS = 30 (hard ceiling)
```

| Query | Combos | Dynamic | Capped at 30 | Sent to LLM |
|---|---|---|---|---|
| Apple 2022 Item 1A | 1 | 5 | 5 | 5 |
| Apple vs Microsoft 2022 | 2 | 10 | 10 | 10 |
| Apple vs Microsoft 2020–2022 | 6 | 30 | 30 | 30 |
| All 5 companies × all 5 years | 25 | 125 | 30 | 30 |

30 chunks × ~280 words ≈ ~11K tokens — under 10% of llama-3.1-8b-instant's 128K context.

**1C. Re-run Evaluation Pipeline**

- Run `evaluation/ragas_evaluator.py` with reranker + dynamic cap in the pipeline
- Compare against V1 baseline
- Primary target: context precision. Secondary: no regression on other 3 metrics.
- Update `eval_results.json`, `README.md` with before/after table

**Expected outcome:**

| Metric | V1 | V2 (target) |
|---|---|---|
| Context Precision | 0.68 | 0.80+ |
| Context Recall | 0.83 | ~0.83 (no regression) |
| Faithfulness | 0.83 | >= 0.83 |
| Answer Relevance | 0.94 | >= 0.94 |

**Pipeline change:**
```
V1: query → filter extraction → Cartesian ChromaDB queries → merge by cosine → synthesizer (top-10 hardcoded)
V2: query → filter extraction → Cartesian ChromaDB queries → merge → reranker reorders → synthesizer (dynamic cap)
```

**Resume bullet target:**
> "Improved context precision from 0.68 to X.XX in SEC filing RAG system by adding cross-encoder reranker over 2,835 chunks across 25 SEC 10-K filings."

---

### Item 2 — Langfuse Instrumentation

**Goal:** Full observability over every LLM call in the pipeline.

**What to instrument:**

| LLM Call | Location | Trace Span |
|---|---|---|
| Filter extraction | `retrieval/retriever.py` | `filter_extraction` |
| Synthesis | `synthesis/synthesizer.py` | `synthesis` |
| Faithfulness judge | `scoring/scorer.py` | `faithfulness_judge` |
| Conflict analysis | `conflict/conflict_analyzer.py` | `conflict_analysis` |

**Trace structure:**
```
Root trace (one per user query)
├── filter_extraction    — prompt, response, model, tokens, latency
├── synthesis            — prompt, response, model, tokens, latency
└── faithfulness_judge   — prompt, response, model, tokens, latency
```

Conflict analysis gets its own root trace (triggered separately from query pipeline).

**What to capture per span:**
- Input prompt (full)
- Output response (full)
- Model name
- Token counts (input + output)
- Latency (ms)
- Cost (if available from Groq response)

**Integration approach:**
- Add `langfuse` to `requirements.txt`
- Initialize Langfuse client in a shared util or at the top of each instrumented file
- Wrap each Groq call with Langfuse span context
- Environment variables: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` in `.env`

**Demo deliverable:** Walk through one failed/low-scoring query trace in Langfuse UI — show how spans reveal where the pipeline lost quality (bad retrieval? unfaithful synthesis? wrong filter extraction?).

---

### Item 3 — Learn-Only Topics (No Code)

Study topics — understand the concepts and trade-offs, document learnings in `learning.md`. No implementation.

**HyDE (Hypothetical Document Embeddings):**
- Concept: generate a hypothetical answer to the query, embed that instead of the raw query, retrieve against the hypothetical embedding
- Trade-off: helps vague/exploratory queries, hurts specific factual queries (SEC queries are specific — diminishing returns after reranker)
- Why skipped for implementation: SEC filing queries are precise ("What were Apple's risk factors in 2022?"), not vague. HyDE adds latency (extra LLM call) for minimal retrieval lift on specific queries.

**HNSW Parameter Tuning:**
- Parameters: M (connections per node), ef_construction (index build quality), ef_search (search quality vs speed)
- Trade-off: tuning matters at scale (100K+ vectors). At 2,835 chunks, default HNSW parameters are already near-optimal — search is exhaustive at this scale regardless of graph structure.
- Why skipped for implementation: dataset too small for tuning to move metrics measurably.

---

### Item 4 — Learn Langfuse for Debugging & Monitoring (No Code)

**Goal:** Learn how to use the Langfuse dashboard to debug bad answers, monitor pipeline health, and spot bottlenecks. Document in `learning.md`.

**Topics to study:**

**Debugging a bad query:**
- How to find a specific trace by query text or trace ID
- Reading the span tree: which step failed? (wrong filters → bad retrieval → hallucinated answer → low faithfulness score)
- Comparing input/output at each span — did the LLM get good chunks but still hallucinate?
- Using the faithfulness_judge score to triage: low score = worth investigating the trace

**Monitoring pipeline health:**
- Filtering traces by latency, error status, or score
- Spotting patterns: are certain query types consistently slow or low-scoring?
- Token usage tracking — how many tokens per query, per step?
- Cost monitoring across Groq calls

**Identifying bottlenecks:**
- Latency breakdown: which span takes the most time? (retrieval vs synthesis vs scoring)
- Are there queries where filter_extraction returns empty filters (pure semantic search) — and do those perform worse?
- Comparing reranker impact: do reranked results lead to higher faithfulness scores?

**Langfuse features to explore:**
- Scores tab — attaching custom scores to traces
- Datasets — creating eval datasets from real traces
- Prompt management — versioning prompts in Langfuse instead of hardcoding
- Users/Sessions — grouping traces by user (relevant if deploying beyond local)

**Not implementing — just learning:** This is about understanding the dashboard and building mental models for when to use each feature. No code changes.

---

## Skipped (with reasoning)

| Item | Reason |
|---|---|
| Hybrid search (BM25 + RRF) | Context recall already 0.83 — metadata filtering + dense retrieval sufficient. BM25 adds index management complexity and RRF tuning for marginal lift on an already-good metric. |
| Vector DB swap (Qdrant/Weaviate/pgvector) | Zero retrieval quality lift at 2,835 chunks. ChromaDB works. Bundle with cloud deployment later. |
| Custom Langfuse dashboards | Built-in Langfuse UI sufficient for portfolio demonstration. |
| Alerting / PagerDuty | Production-grade concern, not needed for portfolio project. |
| Eval runs through Langfuse | Custom eval pipeline (`ragas_evaluator.py`) already exists and works. |
| HyDE implementation | Diminishing returns after reranker. SEC queries are specific, not vague. |
| HNSW tuning implementation | 2,835 chunks too small for tuning to move metrics. |

---

## Implementation Order

Build sequentially — each item completed and validated before the next begins.

| Item | Steps | Depends On |
|---|---|---|
| **Item 1** | Build reranker → integrate into retriever → dynamic context cap → test on V1 queries → re-run eval pipeline → update docs | Nothing — start here |
| **Item 2** | ✅ Complete — Langfuse v4.12.0 installed, `@observe()` on 6 functions, `pipeline.py` wrapper, `ui/app.py` updated, E2E test 2/2 pass | Item 1 (pipeline stable before adding observability) |
| **Item 3** | Study HyDE + HNSW → document in learning.md | Nothing — independent |
| **Item 4** | Study Langfuse debugging, monitoring, bottleneck analysis → document in learning.md | Item 2 complete (need working traces to study against) |

Detailed step-by-step for Item 1 in `V2_ITEM1_TODO.md`.
Detailed step-by-step for Item 2 in `V2_ITEM2_TODO.md`.

---

## Estimate

~1–1.5 weeks (reduced from original 1.5–2 weeks after dropping hybrid search)

- Reranker + dynamic cap + eval rerun: ~3–4 days
- Langfuse instrumentation: ~3–4 days
- Learn-only + documentation: ~1 day

---

## Files Changed/Added

| File | Change |
|---|---|
| `retrieval/reranker.py` | **New** — cross-encoder reranker module |
| `retrieval/retriever.py` | Modified — integrate reranker after Cartesian merge |
| `synthesis/synthesizer.py` | Modified — replace hardcoded MAX_CONTEXT_CHUNKS=10 with dynamic cap |
| `config.py` | Modified — add RERANKER_MODEL, MAX_CONTEXT_CHUNKS=30 |
| `requirements.txt` | Modified — add `langfuse` |
| `retrieval/retriever.py` | Modified — add Langfuse spans |
| `synthesis/synthesizer.py` | Modified — add Langfuse spans |
| `scoring/scorer.py` | Modified — add Langfuse spans |
| `conflict/conflict_analyzer.py` | Modified — add Langfuse spans |
| `evaluation/eval_results.json` | Modified — V2 scores |
| `learning.md` | Modified — HyDE + HNSW notes |
| `README.md` | Modified — V2 scores, before/after table |
| `CLAUDE.md` | Modified — V2 state |
| `.env` | Modified — Langfuse keys added |
