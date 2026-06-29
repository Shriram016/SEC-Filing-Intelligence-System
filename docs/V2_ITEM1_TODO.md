# V2 Item 1 — Reranker + Dynamic Cap + Eval Rerun

## Current Status

| Step | Description | Status |
|---|---|---|
| 1 | Add config values | ✅ Done |
| 2 | Build `retrieval/reranker.py` | ✅ Done |
| 3 | Integrate reranker into retriever | ✅ Done |
| 4 | Dynamic cap in synthesizer | ✅ Done |
| 5 | Test on V1 test queries | ✅ Done — all 4 pass |
| 6 | Re-run eval pipeline | ⏳ Blocked — 4/9 queries scored, Groq 100K TPD limit hit |
| 7 | Update docs | ❌ Waiting for Step 6 |

**Blocker:** RAGAS library uses ~15-25K tokens per query (multi-step decomposition). Groq free tier 70b model has 100K TPD limit — only enough for ~4-5 queries per day. Need checkpointing or daily budget reset to complete.

---

## Goal
Improve context precision from 0.68 to 0.80+ by adding a cross-encoder reranker and fixing the hardcoded context cap.

## Key Design Decisions (from discussion)

- Reranker applies **once on the merged pool**, not per combination
- Reranker **only reorders** — does not decide how many chunks to keep
- **TOP_K stays at 5** per combination — no pool widening
- Synthesizer dynamic cap: `min(len(chunks), MAX_CONTEXT_CHUNKS)` — no combination count passing needed
- Retriever return type unchanged — still returns a list of chunks

## Pipeline Change

```
V1: query → filter extraction → Cartesian ChromaDB queries → merge by cosine → synthesizer (hardcoded top-10)
V2: query → filter extraction → Cartesian ChromaDB queries → merge → reranker reorders → synthesizer (dynamic cap, ceiling 30)
```

---

## Step-by-Step

### Step 1 — Add config values ✅ DONE

**File:** `config.py`

Added:
```python
RERANKER_MODEL = "BAAI/bge-reranker-base"
MAX_CONTEXT_CHUNKS = 30
```

`RERANKER_MODEL` — cross-encoder model, same BGE family as our embedder, runs on CPU (~550MB).
`MAX_CONTEXT_CHUNKS` — hard ceiling. Replaces the hardcoded 10 in synthesizer.py.

---

### Step 2 — Build `retrieval/reranker.py` ✅ DONE

**File:** `retrieval/reranker.py` (new)

**What it does:**
- Loads `BAAI/bge-reranker-base` cross-encoder model once in `__init__`
- Single public method: `rerank(query, chunks) → list[dict]`
  - Takes the query string + list of chunk dicts (from retriever)
  - Scores each (query, chunk_text) pair using cross-encoder
  - Adds `reranker_score` field to each chunk dict
  - Returns the same chunks sorted by reranker_score descending
- Model loaded from `RERANKER_MODEL` in config.py — not hardcoded

**Cross-encoder scoring:**
```
For each chunk:
    Input:  [CLS] query [SEP] chunk["text"] [SEP]
    Output: single relevance logit (higher = more relevant)
    Stored: chunk["reranker_score"] = logit value
```

**Standalone test:** `if __name__ == "__main__"` block that:
- Loads a few sample chunks manually
- Runs reranker on them
- Prints before/after ordering with scores

---

### Step 3 — Integrate reranker into `retrieval/retriever.py` ✅ DONE

**File:** `retrieval/retriever.py` (modify)

**What changes:**
- Import `Reranker` from `retrieval/reranker.py`
- Initialize reranker in `Retriever.__init__()` (loaded once, reused across queries)
- After Step 5 (cosine sort at line 359), add reranker call:
  ```
  existing: all_results.sort(key=lambda x: x["similarity_score"], reverse=True)
  new:      all_results = self.reranker.rerank(query, all_results)
  ```
- Return value stays the same — list of chunk dicts, now sorted by reranker_score instead of cosine

**What does NOT change:**
- Filter extraction (Step 1–2 in retriever)
- Cartesian product logic (Step 3)
- ChromaDB queries (Step 4)
- Deduplication logic
- Return type — still a plain list

---

### Step 4 — Dynamic cap in `synthesis/synthesizer.py` ✅ DONE

**File:** `synthesis/synthesizer.py` (modify)

**What changes:**
- Remove hardcoded `MAX_CONTEXT_CHUNKS = 10` at line 41
- Import `MAX_CONTEXT_CHUNKS` from `config.py`
- Line 108 stays the same: `selected = chunks[:max_context]`
  - `max_context` parameter default changes from hardcoded 10 to `MAX_CONTEXT_CHUNKS` from config
  - Callers don't pass `max_context` — they just send all chunks, synthesizer caps at 30

**Effective behavior:**
```
synthesize(query, chunks)
    selected = chunks[:30]   # was chunks[:10]
```

Since retriever sends `combinations × TOP_K` chunks (minus dedupes):
- 1 combo × 5 = 5 chunks → synthesizer uses all 5
- 2 combos × 5 = 10 chunks → synthesizer uses all 10
- 6 combos × 5 = 30 chunks → synthesizer uses all 30
- 25 combos × 5 = 125 chunks → synthesizer caps at 30

**What does NOT change:**
- `_build_context()` — still builds numbered passages from selected chunks
- Groq API call — same prompt, same temperature, same max_tokens
- Return schema — same dict structure
- `format_citations()` — unchanged

---

### Step 5 — Test on V1 test queries ✅ DONE

**Ran the same 4 queries from V1 retriever validation:**

1. `"What were Apple's main risk factors in 2020?"` — 1 combo, 5 chunks
2. `"Describe Apple's business and products"` — 1 combo (no year), 5 chunks
3. `"Compare Apple and Microsoft's risk factors in 2020"` — 2 combos, 10 chunks
4. `"What is the weather forecast for New York?"` — invalid, rejected

**Verified:**
- [x] Reranker runs without errors
- [x] Chunks have `reranker_score` field added
- [x] Order changes from cosine ranking (e.g. Q1: chunk_001 had highest cosine 0.834 but dropped to position 5 after reranking)
- [x] Dynamic cap works: query 1 sends 5 chunks to LLM, query 3 sends 10
- [x] Invalid query still rejected before reranker is called
- [x] End-to-end: retriever → reranker → synthesizer all work together

---

### Step 6 — Re-run eval pipeline ⏳ IN PROGRESS (blocked by Groq daily token limit)

**Run:** `python evaluation/ragas_evaluator.py`

**V2 change:** Replaced V1 custom eval functions with RAGAS 0.4.3 library for industry-standard metrics.
See `evaluation/EVAL_PIPELINE.md` for full details on RAGAS setup, metrics, and rate limit issues.

**RAGAS judge model:** `llama-3.3-70b-versatile` (CONFLICT_MODEL, 12K TPM, 100K TPD)
**Pipeline model:** `llama-3.1-8b-instant` (GROQ_MODEL, 6K TPM, 500K TPD)

**Partial results (4 of 9 queries scored before 100K TPD limit hit):**

| Query | Type | Faithfulness | Relevancy | Precision | Recall |
|---|---|---|---|---|---|
| Q01 | single_factual | 1.0 | 0.998 | 0.917 | 1.0 |
| Q02 | single_factual | 1.0 | 0.996 | 1.0 | 1.0 |
| Q03 | single_factual | 1.0 | 1.0 | 1.0 | 1.0 |
| Q04 | cross_year | 0.385 | 0.970 | 1.0 | 0.5 |
| Q05–Q10 | — | — | — | — | — |

**Blocking issue:** Groq free tier 100K TPD exhausted after ~4.5 queries. RAGAS uses ~15-25K tokens per query (multi-step claim decomposition + verbose JSON responses). Need daily budget reset to continue.

**Needed to complete:** Add checkpointing to save partial results and resume without re-scoring completed queries.

**Compare against V1 baseline:**

| Metric | V1 | V2 (target) |
|---|---|---|
| Context Precision | 0.68 | 0.80+ |
| Context Recall | 0.83 | ~0.83 (no regression) |
| Faithfulness | 0.83 | >= 0.83 |
| Answer Relevance | 0.94 | >= 0.94 |

**If precision doesn't improve:**
- Check reranker scores — are they actually different from cosine order?
- Check if eval queries have enough combinations to benefit from reranking
- Consider: model might need `bge-reranker-large` instead of `base`

**If other metrics regress:**
- Check if dynamic cap is sending too many/too few chunks
- Check if reranker is pushing irrelevant chunks up (shouldn't happen, but verify)

---

### Step 7 — Update docs ❌ NOT STARTED (waiting for Step 6)

- [ ] `evaluation/eval_results.json` — V2 scores
- [ ] `README.md` — before/after comparison table
- [ ] `CLAUDE.md` — update "Resume Here" section with V2 state
- [ ] `V2_PLAN.md` — mark Item 1 as complete

---

## Files Changed/Added Summary

| File | Change |
|---|---|
| `config.py` | Add `RERANKER_MODEL`, `MAX_CONTEXT_CHUNKS` |
| `retrieval/reranker.py` | **New** — cross-encoder reranker module |
| `retrieval/retriever.py` | Import + initialize reranker, call after Cartesian merge |
| `synthesis/synthesizer.py` | Replace hardcoded 10 with `MAX_CONTEXT_CHUNKS` from config |
| `evaluation/eval_results.json` | V2 scores |
| `README.md` | Before/after table |
| `CLAUDE.md` | V2 state |
| `V2_PLAN.md` | Mark Item 1 complete |
