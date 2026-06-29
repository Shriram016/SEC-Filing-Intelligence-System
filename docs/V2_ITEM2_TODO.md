# V2 Item 2 — Langfuse Instrumentation

## Current Status

| Step | Description | Status |
|---|---|---|
| 1 | Install Langfuse + setup env vars | ✅ Done — langfuse 4.12.0 installed, keys in `.env` |
| 2 | Create `pipeline.py` wrapper | ✅ Done — `run_query_pipeline()` + `run_conflict_pipeline()` |
| 3 | Add `@observe()` to pipeline components | ✅ Done — 6 functions across 4 files |
| 4 | Update `ui/app.py` to use pipeline wrapper | ✅ Done — both tabs use pipeline wrappers |
| 5 | Test end-to-end trace in Langfuse UI | ✅ Done — `test_langfuse_e2e.py` 2/2 pass, traces sent to Langfuse |
| 6 | Update docs | ✅ Done |

---

## Goal

Add full observability over every step in the pipeline — every LLM call, every retrieval, every scoring decision — so that when a query produces a bad answer, we can open Langfuse and see exactly where it went wrong.

---

## What Problem Are We Solving?

Right now, when a user asks a question and gets a bad answer, we're blind. We don't know:
- Did the filter extraction miss the right company/year?
- Did ChromaDB return irrelevant chunks?
- Did the reranker push the wrong chunks up?
- Did the LLM hallucinate despite having good chunks?
- Did the scorer miss a problem?

Langfuse records every step of every query — like a security camera for the pipeline. After a query runs, we open Langfuse UI and see the full trace: every prompt, every response, every timing, every token count.

---

## What Langfuse Captures

**For each LLM call (marked as "generation"):**
- Input prompt (system + user message)
- Output response (full text)
- Model name (e.g. `llama-3.1-8b-instant`)
- Token counts (input + output + total)
- Latency (milliseconds)
- Cost (if provider returns it)

**For each non-LLM step (marked as "span"):**
- Input/Output (what went in, what came out)
- Timing (how long it took)
- Errors (if something failed)

---

## No Framework Dependency

Langfuse does NOT require LlamaIndex or LangChain. Our pipeline uses direct Groq API calls — Langfuse's `@observe()` Python decorator wraps any function, regardless of what's inside.

```python
from langfuse import observe   # v4+ — import directly from langfuse, not langfuse.decorators

@observe(as_type="generation")   # ← LLM call
def my_llm_call(prompt):
    response = groq_client.chat.completions.create(...)
    return response

@observe()                        # ← non-LLM step
def my_retrieval(query):
    results = chromadb_collection.query(...)
    return results
```

---

## LLM Calls in Our Pipeline

4 Groq API calls across 4 files:

| # | File | Method | Model | What it does |
|---|---|---|---|---|
| 1 | `retrieval/retriever.py` | `_extract_filters()` | `llama-3.1-8b-instant` | Parse query → extract tickers/years/sections |
| 2 | `synthesis/synthesizer.py` | `synthesize()` | `llama-3.1-8b-instant` | Generate grounded answer from chunks |
| 3 | `scoring/scorer.py` | `score()` | `llama-3.1-8b-instant` | Faithfulness judge (1–5 rubric) |
| 4 | `conflict/conflict_analyzer.py` | `analyze_pair()` | `llama-3.3-70b-versatile` | Cross-year conflict detection |

---

## Two Pipelines Triggered from UI

**Query tab** (3 LLM calls per query):
```
user query → retriever.retrieve() → synthesizer.synthesize() → scorer.score() → answer + confidence
```

**Conflict tab** (1 LLM call per year pair):
```
company + section + year range → analyze_conflicts() → analyze_pair() per pair → conflict report
```

---

## Trace Structure (What Langfuse Will Show)

**Query pipeline trace:**
```
Trace: "query-pipeline" (one per user query)
│
├── filter_extraction (generation)
│   Input:  "You are a query parser for SEC 10-K..."
│   Output: {"tickers": ["AAPL"], "years": [2020], "sections": ["Item 1A"]}
│   Model:  llama-3.1-8b-instant
│   Tokens: ~350
│   Time:   ~400ms
│
├── retrieval (span)
│   ├── query_embedding (span) — BGE model encodes query
│   ├── chromadb_query combo=AAPL+2020+Item1A (span)
│   ├── chromadb_query combo=MSFT+2020+Item1A (span)  ← one per Cartesian combo
│   └── rerank (span) — cross-encoder reorders merged pool
│   Output: 10 chunks with reranker_score
│   Time:   ~800ms
│
├── synthesis (generation)
│   Input:  "[1] Apple | 2020 | Risk Factors\n..."
│   Output: "Apple disclosed risks related to..."
│   Model:  llama-3.1-8b-instant
│   Tokens: ~2100
│   Time:   ~1500ms
│
└── faithfulness_judge (generation)
    Input:  "Score this answer 1-5..."
    Output: "4"
    Model:  llama-3.1-8b-instant
    Tokens: ~180
    Time:   ~500ms
```

**Conflict pipeline trace:**
```
Trace: "conflict-pipeline" (one per conflict analysis run)
│
├── analyze_pair year_a=2020 year_b=2021 (generation)
│   Model:  llama-3.3-70b-versatile
│   Tokens: ~4000
│   Time:   ~5000ms
│
├── analyze_pair year_a=2021 year_b=2022 (generation)
│   ...
│
└── analyze_pair year_a=2023 year_b=2024 (generation)
    ...
```

All Cartesian product combinations and all year pairs are captured under the same trace because Langfuse automatically groups nested `@observe()` calls under the outermost parent.

---

## The One Structural Change Needed

**Problem:** The UI currently calls retriever, synthesizer, and scorer as three separate calls. Langfuse needs one parent function wrapping all three to create a single root trace.

**Current (`ui/app.py`):**
```python
chunks = retriever.retrieve(query, logger=log)
result = synthesizer.synthesize(query, chunks, logger=log)
score  = scorer.score(result, logger=log)
```

**After (new `pipeline.py`):**
```python
# pipeline.py — thin wrapper, owns the root trace
@observe(name="query-pipeline")
def run_query_pipeline(query, retriever, synthesizer, scorer):
    chunks = retriever.retrieve(query)
    result = synthesizer.synthesize(query, chunks)
    score  = scorer.score(result)
    return {**result, **score}

@observe(name="conflict-pipeline")
def run_conflict_pipeline(company, section, start_year, end_year):
    return analyze_conflicts(company, section, start_year, end_year)
```

**UI changes to:**
```python
from pipeline import run_query_pipeline, run_conflict_pipeline
result = run_query_pipeline(query, retriever, synthesizer, scorer)
```

Same logic, same components, just wrapped so Langfuse has a root to attach everything to.

---

## Step-by-Step Plan

### Step 1 — Install Langfuse + setup env vars

**Install:**
```
pip install langfuse
```

**Add to `requirements.txt`:**
```
langfuse>=2.0.0
```

**Add to `.env`:**
```
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_SECRET_KEY=your_secret_key
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```

User needs to create a free Langfuse account at https://cloud.langfuse.com and get API keys.

**Note:** Langfuse v4 uses `LANGFUSE_BASE_URL` (not `LANGFUSE_HOST`).

---

### Step 2 — Create `pipeline.py` wrapper

**File:** `pipeline.py` (new, project root)

Two functions:
- `run_query_pipeline(query, retriever, synthesizer, scorer)` — wraps query tab flow
- `run_conflict_pipeline(company, section, start_year, end_year)` — wraps conflict tab flow

Both decorated with `@observe()` to create root traces. Thin wrappers — no new logic, just call the existing components.

---

### Step 3 — Add `@observe()` to pipeline components

**File: `retrieval/retriever.py`**
- `retrieve()` → `@observe(name="retrieval")`
- `_extract_filters()` → `@observe(name="filter_extraction", as_type="generation")`

**File: `synthesis/synthesizer.py`**
- `synthesize()` → `@observe(name="synthesis", as_type="generation")`

**File: `scoring/scorer.py`**
- `score()` → `@observe(name="faithfulness_judge", as_type="generation")`

**File: `conflict/conflict_analyzer.py`**
- `analyze_pair()` → `@observe(name="analyze_pair", as_type="generation")`
- `analyze_conflicts()` → `@observe(name="conflict_analysis")`

**What does NOT change:**
- Function signatures — same inputs, same outputs
- Function logic — same code inside
- Return types — same dicts and lists
- Existing logger calls — kept alongside Langfuse (Langfuse captures different things)

---

### Step 4 — Update `ui/app.py` to use pipeline wrapper

**Query tab changes:**
```python
# Before:
chunks = retriever.retrieve(query, logger=log)
result = synthesizer.synthesize(query, chunks, logger=log)
score  = scorer.score(result, logger=log)

# After:
from pipeline import run_query_pipeline
result = run_query_pipeline(query, retriever, synthesizer, scorer)
```

**Conflict tab changes:**
```python
# Before:
results = analyze_conflicts(company, section, start_year, end_year, logger=log)

# After:
from pipeline import run_conflict_pipeline
results = run_conflict_pipeline(company, section, start_year, end_year)
```

UI rendering code unchanged — it reads the same dict structure from the result.

---

### Step 5 — Test end-to-end trace in Langfuse UI

**Test 1 — Query tab:**
- Run a query: "What were Apple's risk factors in 2020?"
- Open Langfuse UI → find the trace
- Verify: filter_extraction, retrieval, synthesis, faithfulness_judge all visible as child spans
- Verify: LLM calls show model, tokens, prompt, response
- Verify: timing captured for each step

**Test 2 — Conflict tab:**
- Run conflict analysis: Apple, Item 1A, 2022–2024
- Open Langfuse UI → find the trace
- Verify: each analyze_pair shows as a child generation span
- Verify: model is `llama-3.3-70b-versatile`

**Test 3 — Failed/low-scoring query:**
- Run a vague query that produces a low-confidence answer
- Walk through the trace to identify where quality was lost
- This is the demo deliverable — show that Langfuse makes debugging visible

---

### Step 6 — Update docs

- [ ] `CLAUDE.md` — add Langfuse to tech stack, update component state
- [ ] `V2_PLAN.md` — mark Item 2 as complete
- [ ] `README.md` — add Langfuse section with trace screenshot description

---

## Files Changed/Added

| File | Change |
|---|---|
| `pipeline.py` | **New** — root trace wrappers for query + conflict pipelines |
| `retrieval/retriever.py` | Add `@observe()` decorators to `retrieve()` and `_extract_filters()` |
| `synthesis/synthesizer.py` | Add `@observe()` decorator to `synthesize()` |
| `scoring/scorer.py` | Add `@observe()` decorator to `score()` |
| `conflict/conflict_analyzer.py` | Add `@observe()` decorators to `analyze_pair()` and `analyze_conflicts()` |
| `ui/app.py` | Import and call `run_query_pipeline()` / `run_conflict_pipeline()` instead of direct component calls |
| `requirements.txt` | Add `langfuse>=2.0.0` |
| `.env` | Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` |
| `test_langfuse_e2e.py` | **New** — E2E test script for query pipeline (2 tests: valid + invalid) |

---

## Estimate

~2–3 days:
- Step 1–2: ~0.5 day (install, wrapper)
- Step 3–4: ~1 day (decorators on 4 files + UI update)
- Step 5–6: ~1 day (testing, demo trace, docs)
