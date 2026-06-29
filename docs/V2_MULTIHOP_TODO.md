# V2 — Multi-Hop Query Handling (Sub-Query Template)

## Current Status

| Step | Description | Status |
|---|---|---|
| 1 | Update `_extract_filters()` prompt | ✅ Done |
| 2 | Add template validation | ✅ Done |
| 3 | Change rerank logic in `retrieve()` | ✅ Done |
| 4 | Group chunks in synthesizer context | ✅ Done |
| 5 | Test on failing multi-hop queries (Q08, Q10, Q13, Q15, Q23, Q24) | ✅ Done |
| 6 | Re-run full eval (24 queries) | ✅ Done |
| 7 | Update docs | ✅ Done |

---

## Problem

Cross-encoder reranker scores each chunk independently against the query. For comparison queries like "How did Microsoft's AI risk evolve from 2022 to 2023?", no single chunk talks about "evolution" or "change between years." The reranker gives every chunk near-zero scores, the synthesizer loses confidence and refuses to answer.

**Evidence from eval run (2026-06-28):**
- 6 out of 18 scored queries refused to answer (33%)
- All 6 were multi-hop (cross-year, cross-company, or conflict-triggering)
- Reranker top scores for Q08: 0.0658, 0.0384, 0.0354 (vs 0.7111 for single factual Q04)
- Full analysis in `evaluation/eval_results_intermediate_results_analysis.md`

---

## Solution — Sub-Query Template

Have the LLM output a `sub_query_template` alongside the filters. For multi-combo queries, fill the template per combination and rerank each combo's chunks with a focused sub-query instead of the original comparison query.

**Example:**
```
Query: "How did Microsoft's AI risk evolve from 2022 to 2023?"

LLM output:
{
    "is_valid": true,
    "tickers": ["MSFT"],
    "years": [2022, 2023],
    "sections": ["Item 1A"],
    "sub_query_template": "<company> AI risk disclosures in <year>"
}

Cartesian: 2 combos
    {MSFT, 2022, Item 1A} → rerank with "Microsoft AI risk disclosures in 2022"
    {MSFT, 2023, Item 1A} → rerank with "Microsoft AI risk disclosures in 2023"
```

**Why this works:**
- Each sub-query is a single factual lookup — reranker scores these well
- The topic ("AI risk disclosures") carries over from the original query
- The comparison happens at synthesis, where the LLM is good at it
- One LLM call, one template — scales to any number of combos

---

## Design Decisions

- LLM outputs one template, not N sub-queries — scales to 4, 8, 32 combos without extra tokens
- Use `<company>` (not `<ticker>`) in template — filing text says "Apple" not "AAPL"
- Template captures the **topic** from the original query (e.g., "AI risk disclosures", "competitive risks", "headcount")
- `<section>` is NOT a placeholder — too generic. The topic from the original query is more specific than section names
- If only 1 combo → use original query, skip template
- If template is null/malformed → fallback to original query (no breakage)
- ChromaDB embedding stays the original query — sub-query is only for reranking

---

## Conflict Analyzer — Not Affected

The conflict analyzer (`conflict/conflict_analyzer.py`) is a completely separate pipeline:
- Does NOT use the retriever, reranker, or synthesizer
- Reads full section text directly from `_sections.json` files
- Sends both years' full text to the 70b model in one prompt
- Triggered from the Conflict Explorer tab, not the Query tab

No changes needed.

---

## Step-by-Step

### Step 1 — Update `_extract_filters()` prompt

**File:** `retrieval/retriever.py`

**Sub-steps:**

**1a. Add explanation lines to the prompt (new task #5):**
```
5. SUB-QUERY TEMPLATE: If the query compares across multiple companies OR multiple years,
   create a short template that captures the core topic of the query.
   Use <company> and <year> as placeholders — these will be filled for each combination.
   The template should preserve the specific topic from the original query (e.g., "AI risks",
   "competitive risks", "headcount") — not generic terms like "data" or "information".
   If the query targets a single company AND single year, set to null.
```

**1b. Add examples to the prompt:**
```
Query: "How did Microsoft's AI risk evolve from 2022 to 2023?"
→ sub_query_template: "<company> AI risk disclosures in <year>"

Query: "Compare Apple and Microsoft's competitive risks in 2023"
→ sub_query_template: "<company> competitive risks in <year>"

Query: "What were Apple's risk factors in 2022?"
→ sub_query_template: null  (single combo, not needed)
```

**1c. Add `sub_query_template` to the expected JSON output format:**
```json
{
    "is_valid": true,
    "rejection_reason": null,
    "tickers": [],
    "years": [],
    "sections": [],
    "sub_query_template": null
}
```

**1d. Increase `max_tokens` from 200 to 250** (template adds ~20 tokens to the response)

**No Pydantic used** — filter extraction uses `json.loads()` + manual validation. No schema class to update.

### Step 2 — Add template validation

**File:** `retrieval/retriever.py` (in `_extract_filters()`, after JSON parsing)

**Sub-steps:**

**2a.** After `json.loads()`, extract `sub_query_template` from the parsed dict. If key is missing → default to `null`.

**2b.** If template is an empty string `""` → set to `null`.

**2c.** Check template has at least one placeholder — must contain `<company>` or `<year>`. If neither found → set to `null` (useless without placeholders).

**2d.** Add `sub_query_template` to the log output:
```
RETRIEVER | filter_extraction | EXIT | ... sub_query_template="<company> AI risk disclosures in <year>"
```

**2e.** Return `sub_query_template` as part of the filters dict (alongside tickers, years, sections).

**Output — `_extract_filters()` return dict after Steps 1+2:**

Single factual query:
```python
{
    "is_valid":           True,
    "rejection_reason":   None,
    "tickers":            ["AAPL"],
    "years":              [2022],
    "sections":           ["Item 1A"],
    "sub_query_template": None,
}
```

Multi-hop query:
```python
{
    "is_valid":           True,
    "rejection_reason":   None,
    "tickers":            ["MSFT"],
    "years":              [2022, 2023],
    "sections":           ["Item 1A"],
    "sub_query_template": "<company> AI risk disclosures in <year>",
}
```

Same dict, one new field. Downstream code that reads `filters["tickers"]` or `filters["years"]` still works — they ignore the new field unless they need it.

**Fallback:** Any malformed template → null → current behaviour (rerank with original query). No breakage.

### Step 3 — Change rerank logic in `retrieve()`

**File:** `retrieval/retriever.py`

**Sub-steps:**

**3a.** Read `sub_query_template` from the filters dict returned by `_extract_filters()`:
```python
sub_query_template = filters.get("sub_query_template")
```

**3b.** Add `TICKER_TO_COMPANY` reverse mapping at the top of the file (we already have `COMPANY_TO_TICKER`):
```python
TICKER_TO_COMPANY = {v: k for k, v in COMPANY_TO_TICKER.items()}
# {"AAPL": "Apple", "MSFT": "Microsoft", ...}
```

**3c.** Change Step 4 (ChromaDB queries) to store results per combo instead of merging immediately:
```
Current:  all_results = []  →  for each combo: append chunks to all_results
New:      combo_results = {}  →  for each combo: combo_results[combo_key] = [chunks]
```
Combo key is a tuple like `("MSFT", 2022, "Item 1A")` — just an identifier to group chunks. Not the sub-query.

**3d.** After all ChromaDB queries are done, check the branching condition:
```
if len(combinations) == 1 OR sub_query_template is None:
    → merge all combo_results into one flat list
    → rerank with original query (current behaviour)
    → done

else (combos > 1 AND template exists):
    → go to 3e
```

**3e.** For each combo in combo_results:
- Get the ticker and year from the combo dict: `combo["ticker"]`, `combo["year"]`
- Convert ticker to company name: `TICKER_TO_COMPANY["MSFT"]` → `"Microsoft"`
- Fill the template: `"<company> AI risk disclosures in <year>"` → `"Microsoft AI risk disclosures in 2022"`
- Call reranker: `self.reranker.rerank(filled_sub_query, combo_chunks, logger)`

**3f.** Merge all reranked groups into one flat list.

**3g.** Return the flat list — same `list[dict]` return type as before. No downstream breakage.

**Key design decision — sub-query is only for reranker, NOT for ChromaDB:**
- ChromaDB uses the original query embedding + metadata filters (ticker, year, section). This already scopes results correctly.
- The problem was never ChromaDB retrieval — it returned relevant chunks. The problem was the reranker scoring them near zero with the comparison query.
- Using sub-queries for ChromaDB would require embedding each sub-query separately (one BGE encode per combo). More compute, no benefit.

**What stays the same:**
- ChromaDB queries — same embeddings, same filters, same TOP_K
- Deduplication logic — same
- Return type — same `list[dict]`
- Single factual queries — same path, no change in behaviour

### Step 4 — OPTIONAL: group chunks in synthesizer context

**Status:** Do NOT implement until Steps 1-3 are tested and validated.

**What it does:**
Currently the synthesizer receives chunks sorted by reranker score — interleaved randomly across years/companies. For a cross-year query, the LLM sees: 2023 chunk, 2022 chunk, 2023 chunk, 2022 chunk... It has to mentally sort them while reading.

Grouping would organize the chunks by their sub-query group before sending to the LLM:
```
=== Microsoft AI risks in 2022 ===
[1] 2022 chunk...
[2] 2022 chunk...

=== Microsoft AI risks in 2023 ===
[3] 2023 chunk...
[4] 2023 chunk...
```

Same chunks, same information — just organized so the LLM can compare more easily.

**Why it's optional:**
The core problem is the reranker scoring comparison chunks near zero (Steps 1-3 fix this). Grouping is a presentation improvement — it helps the LLM read the context, but doesn't fix the root cause. If better reranking alone stops the refusals and the LLM produces good comparative answers from interleaved chunks, grouping adds complexity for no gain.

**When to implement:**
Run the eval after Steps 1-3. If cross-year/cross-company faithfulness improves but is still below 0.7, then grouping may help push it higher. If scores are already good, skip it.

**Additional consideration — balanced representation:**
After per-combo reranking, merging all groups by score could result in unbalanced representation (e.g. 8 chunks from 2022, only 2 from 2023). If this step is implemented, consider taking top N per combo before merging to ensure equal representation across groups.

---

## Files Changed

| File | Change | Size |
|---|---|---|
| `retrieval/retriever.py` | Prompt update + template validation + per-combo rerank logic | Medium |
| `synthesis/synthesizer.py` | Optional: grouped context for multi-hop queries | Small |
| `retrieval/reranker.py` | No change — already accepts any query string | None |
| `scoring/scorer.py` | No change | None |
| `pipeline.py` | No change | None |
| `ui/app.py` | No change | None |
| `conflict/conflict_analyzer.py` | No change — separate pipeline | None |
| `config.py` | No change | None |

---

## Test Plan

### Step 5 — Test all 24 queries

**5a.** Run the full eval pipeline (all 24 queries) with a fresh checkpoint:
```
del evaluation/eval_checkpoint.json
python evaluation/ragas_evaluator.py
```

**5b.** Check logs for multi-hop queries (Q07-Q15, Q22-Q24):
- Did the LLM output a `sub_query_template`?
- Was each combo reranked with a filled sub-query?
- Reranker scores improved from near-zero?
- Did the synthesizer answer or refuse?

**5c.** Check logs for single factual queries (Q01-Q06):
- Template should be null
- Behaviour unchanged from before

**5d.** Check vague queries (Q16-Q18):
- Template behaviour — could go either way depending on filter extraction
- Q17 still being incorrectly rejected?

**5e.** Check invalid queries (Q19-Q21):
- Still correctly rejected?

**5f.** Compare all 24 scores against the intermediate results in `evaluation/eval_results_intermediate_results_analysis.md`. Generate a before/after table:

| Query | Type | Before (Faith) | After (Faith) | Before (Relev) | After (Relev) | Change |
|---|---|---|---|---|---|---|
| Q01 | single_factual | 0.818 | ? | 0.979 | ? | No regression expected |
| Q02 | single_factual | 0.846 | ? | 0.989 | ? | No regression expected |
| ... | ... | ... | ... | ... | ... | ... |
| Q08 | cross_year | 0.000 | ? | 0.000 | ? | Should improve (was refused) |
| Q10 | cross_year | 0.000 | ? | 0.000 | ? | Should improve (was refused) |
| Q13 | cross_company | 0.000 | ? | 0.000 | ? | Should improve (was refused) |
| Q15 | cross_company | 0.000 | ? | 0.000 | ? | Should improve (was refused) |
| Q23 | conflict_triggering | 0.000 | ? | 0.000 | ? | Should improve (was refused) |
| Q24 | conflict_triggering | 0.000 | ? | 0.000 | ? | Should improve (was refused) |

**5g.** If any multi-hop query still refuses → check logs to identify if it's a template issue, reranker issue, or synthesizer issue. Decide if Step 4 (grouping) is needed.

### Step 6 — Update eval results

- Update `evaluation/eval_results_v2.json` with new scores
- Update `evaluation/eval_results_intermediate_results_analysis.md` with before/after comparison
- Document what improved and what didn't

### Step 7 — Update docs

- `CLAUDE.md` — update resume section with multi-hop handling status
- `V2_PLAN.md` — add multi-hop as a completed item or in-progress
- `V2_MULTIHOP_TODO.md` — mark completed steps
