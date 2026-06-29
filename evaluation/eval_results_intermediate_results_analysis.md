# Evaluation Results Analysis — V2 (TOP_K=10, Reranker)

## Run Details

- **Date:** 2026-06-28
- **Pipeline model:** llama-3.1-8b-instant
- **Judge model:** llama-3.3-70b-versatile (RAGAS 0.4.3)
- **Eval set:** eval_queries_v2.json (24 queries)
- **TOP_K:** 10 per combination
- **MAX_CONTEXT_CHUNKS:** 30
- **Reranker:** BAAI/bge-reranker-base (cross-encoder)

---

## Query-Level Scores

| ID | Type | Query | Faith | Relev | Prec | Recall | Notes |
|---|---|---|---|---|---|---|---|
| Q01 | single_factual | Apple supply chain risks 2022 | 0.818 | 0.979 | 0.867 | 1.000 | |
| Q02 | single_factual | Microsoft AI risks 2023 | 0.846 | 0.989 | 1.000 | 1.000 | |
| Q03 | single_factual | Amazon net sales + AWS 2021 | 1.000 | 1.000 | 1.000 | 1.000 | Perfect |
| Q04 | single_factual | Google Cloud + Vertex AI 2023 | 0.727 | 0.841 | 0.917 | 1.000 | |
| Q05 | single_factual | Meta revenue + net income 2023 | 1.000 | 1.000 | 1.000 | 1.000 | Perfect |
| Q06 | single_factual | Apple interest rate risks 2022 | 0.909 | 0.994 | 1.000 | 1.000 | |
| Q07 | cross_year | Apple risk factors 2020 vs 2023 | 0.538 | 0.971 | 0.000 | 0.500 | Low precision |
| Q08 | cross_year | Microsoft AI risk 2022 vs 2023 | 0.000 | 0.000 | 0.867 | 0.500 | **Refused** |
| Q09 | cross_year | Meta revenue 2022 vs 2023 | 0.900 | 1.000 | 0.478 | 1.000 | |
| Q10 | cross_year | Amazon business 2020 vs 2024 | 0.000 | 0.000 | 0.250 | 0.667 | **Refused** |
| Q11 | cross_year | Google market risk 2021 vs 2024 | 0.414 | 0.991 | 1.000 | 0.667 | |
| Q12 | cross_company | Apple vs Microsoft competitive 2023 | 0.350 | 0.977 | 0.639 | 1.000 | Low faithfulness |
| Q13 | cross_company | Amazon vs Google revenue 2023 | 0.000 | 0.000 | 0.833 | 0.333 | **Refused** |
| Q14 | cross_company | Meta vs Microsoft workforce 2023 | 0.294 | 0.982 | 0.000 | 0.333 | Low recall |
| Q15 | cross_company | Apple, Amazon, Google business 2022 | 0.000 | 0.000 | 0.250 | 0.333 | **Refused** |
| Q16 | vague | Biggest risks in tech | 0.735 | 1.000 | N/A | N/A | |
| Q17 | vague | Macroeconomic conditions | 0.000 | 0.000 | N/A | N/A | **Bad reject** |
| Q18 | vague | Companies on AI | 0.357 | 0.962 | N/A | N/A | |
| Q19 | invalid | Weather in NYC | N/A | N/A | N/A | N/A | Rejected ✓ |
| Q20 | invalid | Super Bowl winner | N/A | N/A | N/A | N/A | Rejected ✓ |
| Q21 | invalid | Tesla revenue | N/A | N/A | N/A | N/A | Rejected ✓ |
| Q22 | conflict_triggering | Meta Reality Labs 2022 vs 2023 | 1.000 | 0.981 | 1.000 | 1.000 | Perfect |
| Q23 | conflict_triggering | Apple supplier risk 2020 vs 2023 | 0.000 | 0.000 | 0.500 | 0.500 | **Refused** |
| Q24 | conflict_triggering | Microsoft AI risk 2022 vs 2024 | 0.000 | 0.000 | 0.367 | 0.667 | **Refused** |

---

## Per-Type Averages

| Type | Count | Faith | Relev | Prec | Recall |
|---|---|---|---|---|---|
| single_factual | 6 | **0.883** | **0.967** | **0.964** | **1.000** |
| cross_year | 5 | 0.370 | 0.592 | 0.519 | 0.667 |
| cross_company | 4 | 0.161 | 0.490 | 0.430 | 0.500 |
| conflict_triggering | 3 | 0.333 | 0.327 | 0.622 | 0.722 |
| vague | 2* | 0.546 | 0.981 | N/A | N/A |
| **OVERALL** | **18** | **0.494** | **0.683** | **0.665** | **0.750** |

*Q17 excluded from vague average (bad reject). 3 invalid queries excluded (correctly rejected, no metrics).

---

## Overall Scores

| Metric | Score |
|---|---|
| Faithfulness | 0.494 |
| Answer Relevance | 0.683 |
| Context Precision | 0.665 |
| Context Recall | 0.750 |

---

## What's Working

**Single factual queries are excellent.** 6/6 scored high across all metrics. The pipeline handles "one company, one year, one section, one topic" questions very well. Retrieval, reranking, and synthesis all work as designed.

**Invalid query rejection is perfect.** All 3 invalid queries (Q19, Q20, Q21) correctly rejected by the query parser, including the borderline case (Q21 — Tesla, a valid company but not in our dataset).

**Q22 (conflict_triggering) scored perfectly.** Meta Reality Labs revenue comparison worked — the synthesizer successfully compared 2022 and 2023 data.

---

## What's Failing

### Problem 1 — Synthesizer refuses to answer multi-hop queries (6 queries affected)

**Affected:** Q08, Q10, Q13, Q15, Q23, Q24

**Symptom:** The synthesizer returns "The provided context does not contain enough information to answer this question" despite having relevant chunks retrieved (10-20 chunks).

**Root cause — reranker scores near zero for comparison queries:**

The reranker (cross-encoder) scores each chunk independently against the full query. For a comparison query like "How did Microsoft's AI risk evolve from 2022 to 2023?", no single chunk talks about "evolution" or "change between years." Each chunk only describes what ONE year said. The reranker gives every chunk a near-zero relevance score.

Example from Q08 log:
```
Reranker top 3 scores: 0.0658, 0.0384, 0.0354
```
Compare with a single factual query (Q04):
```
Reranker top 3 scores: 0.7111, 0.1206, 0.1202
```

The synthesizer sees 20 chunks all scored near-zero relevance, interleaved randomly from different years, and loses confidence → refuses to answer.

**This is a known limitation of cross-encoder rerankers.** They score one chunk at a time against the query. A comparison answer requires combining information from multiple chunks across different sources — no single chunk can answer it alone.

### Problem 2 — Low faithfulness on cross-company queries (Q12, Q14)

**Affected:** Q12 (0.350), Q14 (0.294)

**Symptom:** The pipeline produces an answer, but RAGAS judges many claims as unfaithful.

**Root cause:** When comparing two companies, the LLM synthesizes a narrative that goes slightly beyond what individual chunks state. For example, "Microsoft additionally identified AI as a new competitive dimension — a dimension absent from Apple's disclosures" is an inference the LLM made by noticing something was missing from Apple's chunks, not a direct quote from any chunk.

### Problem 3 — Q17 incorrectly rejected (1 query affected)

**Affected:** Q17 ("How have tech companies been affected by macroeconomic conditions?")

**Symptom:** Query parser marked it `is_valid: false` with reason "unrelated to companies, finance, business, or risk."

**Root cause:** The query is clearly about finance and business, but the LLM query parser sometimes misclassifies vague/broad questions. This is an LLM judgment error, not a systematic issue.

---

## Root Cause Summary

| Problem | Queries | Root Cause | Category |
|---|---|---|---|
| Synthesizer refusal | Q08, Q10, Q13, Q15, Q23, Q24 | Reranker scores all chunks near-zero for comparison queries → LLM loses confidence | **Reranker architecture** |
| Low faithfulness | Q12, Q14 | LLM infers beyond chunk text in comparative answers | Synthesis prompt |
| Bad rejection | Q17 | LLM query parser misclassifies valid broad query | Query parser |

---

## Proposed Fix — Sub-Query Template for Reranking

**The reranker problem affects 6 out of 18 scored queries (33%).** It is the single biggest quality issue.

**Approach:** Have the LLM output a `sub_query_template` alongside the filters. For multi-combo queries, fill the template per combination and rerank each combo's chunks with a focused sub-query instead of the original comparison query.

**Example:**
```
Query: "How did Microsoft's AI risk evolve from 2022 to 2023?"

LLM output:
{
    "tickers": ["MSFT"],
    "years": [2022, 2023],
    "sections": ["Item 1A"],
    "sub_query_template": "<company> AI risk disclosures in <year>"
}

Cartesian: 2 combos
    {MSFT, 2022, Item 1A} → rerank with "Microsoft AI risk disclosures in 2022"
    {MSFT, 2023, Item 1A} → rerank with "Microsoft AI risk disclosures in 2023"
```

Each sub-query is a single factual lookup — the reranker scores these well. The comparison happens at the synthesis step where the LLM is good at it.

**Design decisions:**
- LLM outputs one template, not N sub-queries — scales to any number of combos
- Use `<company>` (not `<ticker>`) in template — matches filing text ("Apple" not "AAPL")
- Template captures the **topic** from the original query (e.g., "AI risk disclosures", "competitive risks", "headcount")
- If only 1 combo → use original query, skip template
- If template is null/malformed → fallback to original query

**Files to change:** `retriever.py` (prompt + rerank logic), `config.py` (flag)
