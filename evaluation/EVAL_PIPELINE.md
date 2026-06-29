# Evaluation Pipeline — Design & Status

## Goal

Measure whether V2 changes (cross-encoder reranker + dynamic context cap) improved retrieval and answer quality over V1 baseline.

**Primary target:** Context Precision 0.68 → 0.80+
**Secondary:** No regression on other 3 metrics.

---

## V1 Baseline Scores (Custom Eval)

| Metric | V1 Score | Method |
|---|---|---|
| Faithfulness | 0.83 | Custom LLM judge, single 1-5 rubric, normalised (raw-1)/4 |
| Answer Relevance | 0.94 | Custom LLM judge, single 1-5 rubric |
| Context Precision | 0.68 | Custom LLM judge, flat YES/NO per chunk, fraction relevant (NOT rank-aware) |
| Context Recall | 0.83 | Custom LLM judge, single YES/PARTIAL/NO verdict |

All V1 metrics used `llama-3.1-8b-instant` via Groq, one LLM call per metric per query.

---

## What We Are Testing

10 predefined queries in `evaluation/eval_queries.json`, each with a human-written ground truth answer extracted from actual `_sections.json` filing text.

| Query types | Count |
|---|---|
| Single company factual (AAPL, MSFT, AMZN, META) | 4 |
| Cross-year comparison (2020→2023, 2022→2023) | 3 |
| Cross-company comparison (AAPL vs MSFT) | 1 |
| Invalid (weather — should be rejected) | 1 |
| Conflict-triggering (META Reality Labs) | 1 |

Q09 (invalid) is excluded from scoring — only checks retriever rejection. **9 queries produce metric scores.**

---

## Ground Truth

Ground truth is a **human-written answer string** per query — NOT a set of correct chunk IDs.

Example (Q03):
> "Amazon's total consolidated net sales for 2021 were $469,822 million ($469.8 billion), a 22% increase compared to 2020. AWS revenue was $62,202 million ($62.2 billion) in 2021, representing 37% growth over the prior year."

Each answer was written by reading the actual `_sections.json` filing text and extracting specific facts (exact numbers, exact claims). Not LLM-generated.

**How ground truth is used by each metric:**

| Metric | Uses ground truth? | Purpose |
|---|---|---|
| Faithfulness | No | Checks generated answer against retrieved chunks |
| Answer Relevancy | No | Checks generated answer against the question |
| Context Precision | Yes | Judges each chunk's relevance against ground truth |
| Context Recall | Yes | Decomposes ground truth into claims, checks if chunks cover them |

---

## 4 Metrics — RAGAS Library (V2)

V2 switched from custom eval functions to the **RAGAS 0.4.3 library** for more rigorous, industry-standard evaluation.

### 1. Faithfulness (0–1)
**Question:** Is the generated answer making stuff up, or is everything backed by the retrieved chunks?

**How RAGAS calculates it (multi-step):**
1. LLM decomposes the generated answer into atomic statements
2. For each statement, NLI judge checks if it's entailed by retrieved context (1=supported, 0=not)
3. Score = `supported statements / total statements`

**Inputs:** `user_input` (query), `response` (generated answer), `retrieved_contexts` (chunk texts)

### 2. Answer Relevancy (0–1)
**Question:** Does the answer actually address the question?

**How RAGAS calculates it:**
1. LLM generates N hypothetical questions from the answer
2. Embed generated questions + original question
3. Score = mean cosine similarity between generated question embeddings and original question embedding

**Inputs:** `user_input` (query), `response` (generated answer)

### 3. Context Precision (0–1) — PRIMARY V2 TARGET
**Question:** Are the retrieved chunks relevant, and are relevant ones ranked at the top?

**How RAGAS calculates it (rank-aware):**
1. LLM judges each chunk: useful (1) or not useful (0) against ground truth
2. Compute Precision@k at each rank position
3. Score = Average Precision: `AP = Σ(P@k × vₖ) / total_relevant`

**Key difference from V1:** RAGAS version is **rank-aware** — relevant chunks ranked higher score better. V1 was a flat fraction (rank didn't matter). This means the reranker's reordering directly improves this metric.

**Inputs:** `user_input` (query), `retrieved_contexts` (chunk texts), `reference` (ground truth)

### 4. Context Recall (0–1)
**Question:** Do the retrieved chunks contain all the facts needed to produce the correct answer?

**How RAGAS calculates it:**
1. LLM decomposes ground truth into atomic claims
2. For each claim, check if any retrieved chunk supports it (1=found, 0=not)
3. Score = `found claims / total claims`

**Inputs:** `user_input` (query), `retrieved_contexts` (chunk texts), `reference` (ground truth)

---

## Key Difference: Custom Eval vs RAGAS Library

| Aspect | V1 Custom Eval | V2 RAGAS Library |
|---|---|---|
| Faithfulness | Single 1-5 rubric, one LLM call | Multi-step: decompose answer → per-claim NLI |
| Answer Relevancy | Single 1-5 rubric, one LLM call | Generate hypothetical questions → cosine similarity |
| Context Precision | Flat YES/NO fraction, NOT rank-aware | Rank-aware Average Precision |
| Context Recall | Single YES/PARTIAL/NO verdict | Decompose ground truth → per-claim attribution |
| LLM calls per query | ~4 (one per metric) | ~8-12 (multi-step decomposition) |
| Tokens per query | ~3K-5K | ~15K-25K |
| Designed for | Groq free tier constraints | GPT-4 class APIs with high limits |

---

## V2 Pipeline Being Evaluated

```
V1: query → filter extraction → Cartesian ChromaDB queries → merge by cosine → synthesizer (hardcoded top-10)
V2: query → filter extraction → Cartesian ChromaDB queries → merge → reranker reorders → synthesizer (dynamic cap, ceiling 30)
```

**V2 changes:**
- **Reranker:** `BAAI/bge-reranker-base` cross-encoder applied once on merged pool after all Cartesian queries
- **Dynamic cap:** Synthesizer uses `MAX_CONTEXT_CHUNKS=30` from config instead of hardcoded 10

---

## Models Used

| Component | Model | Purpose |
|---|---|---|
| Query filter extraction | `llama-3.1-8b-instant` (GROQ_MODEL) | Parse query → extract tickers/years/sections |
| Answer synthesis | `llama-3.1-8b-instant` (GROQ_MODEL) | Generate grounded answer from chunks |
| RAGAS judge (V2) | `llama-3.3-70b-versatile` (CONFLICT_MODEL) | Score all 4 evaluation metrics |
| Embeddings (retrieval) | `BAAI/bge-base-en` | Query + chunk embeddings for ChromaDB |
| Embeddings (RAGAS) | `BAAI/bge-base-en` | Answer relevancy cosine similarity |
| Reranker | `BAAI/bge-reranker-base` | Cross-encoder relevance scoring |

---

## Groq Free Tier Limits

| Model | TPM (tokens/min) | TPD (tokens/day) | RPM (requests/min) |
|---|---|---|---|
| `llama-3.1-8b-instant` | 6,000 | 500,000 | 30 |
| `llama-3.3-70b-versatile` | 12,000 | 100,000 | 30 |

**TPM = single request limit.** A single API call's input + output tokens cannot exceed TPM. This is the binding constraint for RAGAS, which generates verbose structured JSON responses.

---

## Rate Limit Issues Hit During Development

| Attempt | Model | Failure | Root Cause |
|---|---|---|---|
| 1 | 8b | 429 rate limit (TPM) | No delays between RAGAS metric calls |
| 2 | 8b | Truncated JSON | `max_tokens=1024` too small for RAGAS's verbose decomposition output |
| 3 | 8b | 413 request too large | 10 chunks → 7,380 tokens in one call, exceeds 6K TPM |
| 4 | 8b | 429 daily limit (TPD) | Previous failed runs burned through 500K daily budget |
| 5 | 70b | Truncation + retry explosion | RAGAS retries include previous failed response in prompt, request grows each retry |
| 6 | 70b | 429 daily limit (TPD) | 100K daily budget exhausted after scoring 4.5 queries |

**Root cause analysis:**
- RAGAS generates multi-step structured JSON with `statement`, `reason`, `verdict` per claim
- A detailed answer (like Q03 Amazon financials) decomposes into 50+ atomic statements
- Each statement gets a verbose JSON verdict → response easily exceeds 4,096 tokens
- Groq free tier TPM (6K-12K) is 1000x smaller than what RAGAS was designed for (OpenAI 10M+ TPM)
- 100K TPD on 70b model only enough for ~4-5 queries with RAGAS's token appetite

**Mitigations applied:**
- `MAX_JUDGE_CHUNKS = 5` — cap chunks sent to RAGAS judges (reduces input tokens)
- `max_tokens = 4096` — allow longer structured responses
- Switched RAGAS judge to `llama-3.3-70b-versatile` (12K TPM vs 6K)
- Added delays: `RAGAS_METRIC_DELAY = 10s`, `RAGAS_QUERY_DELAY = 20s`

---

## Partial Results (from successful 70b run)

Scored 4 out of 9 queries before hitting daily limit:

| Query | Type | Faithfulness | Relevancy | Precision | Recall |
|---|---|---|---|---|---|
| Q01 | single_factual | 1.0 | 0.998 | 0.917 | 1.0 |
| Q02 | single_factual | 1.0 | 0.996 | 1.0 | 1.0 |
| Q03 | single_factual | 1.0 | 1.0 | 1.0 | 1.0 |
| Q04 | cross_year | 0.385 | 0.970 | 1.0 | 0.5 |
| Q05 | cross_year | 0.647 | 0.997 | — | — |
| Q06–Q10 | — | — | — | — | — |

**Early observations:**
- Context precision looking strong (0.917–1.0) — reranker is working
- Q04 faithfulness low (0.385) — cross-year comparison answer may contain claims not in top-5 chunks
- Q04 recall 0.5 — ground truth about COVID→macro shift only partially covered in 5 chunks

---

## Evaluator Code Structure

**File:** `evaluation/ragas_evaluator.py`

**Two phases:**
1. **Phase 1 — Pipeline run:** For each query, run retriever (filter + ChromaDB + reranker) → synthesizer (dynamic cap). Collect answer + chunk texts. Uses `GROQ_MODEL` (8b).
2. **Phase 2 — RAGAS scoring:** For each query's output, run 4 RAGAS metrics via `ascore()`. Uses `CONFLICT_MODEL` (70b).

**Constants (top of file):**
```python
PIPELINE_QUERY_DELAY = 10    # seconds between pipeline queries (Phase 1)
PIPELINE_REJECT_DELAY = 5    # seconds after a rejected query (Phase 1)
RAGAS_METRIC_DELAY = 10      # seconds between each RAGAS metric call (Phase 2)
RAGAS_QUERY_DELAY = 20       # seconds between queries in RAGAS scoring (Phase 2)
MAX_JUDGE_CHUNKS = 5         # max chunks sent to RAGAS judges
```

**Output:** `evaluation/eval_results.json` — per-query scores + aggregate averages.

**Old V1 custom judge functions are preserved as comments in the file for reference.**

---

## Next Steps

- [ ] Complete RAGAS eval for remaining 5 queries (Q05–Q10) — requires daily token budget reset
- [ ] Add checkpointing — save partial results, skip already-scored queries on retry
- [ ] Compare V2 aggregates against V1 baseline
- [ ] Update `README.md` with before/after table
- [ ] Update `CLAUDE.md` with V2 state
