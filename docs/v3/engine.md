# Spec — Answering engine

**Status:** design approved (grilling 2026-11-18 → 2026-11-19). Router + search built (M2); checked answers built (Q107, 2026-11-22).
**Milestones:** M2 (simple questions), M3 (hard questions).
**Sources:** `docs/V3_GRILLING_LOG.md` Q15, Q16, Q24–Q32, Q35, Q36, Q64, Q65. ADR-0002, ADR-0003, ADR-0005.

## 1. Purpose

Answer a routed question from the filings. Every number is quoted and checked by code. All maths is done by code.

The engine is a **self-contained library**. It has no web or UI code, so it can be tested alone.

## 2. Flow

```
router output → planner → for each step: search → read fact → (calculator) → answer writer (JSON)
              → claim + quote check (code) → answer / partial answer / refuse
```

## 3. Parts

### 3.1 Planner (plan first)
- One LLM call writes a plan: a list of small steps (for example "find AWS revenue FY2021", "find AWS revenue FY2022", "calculate growth").
- Code runs the steps in order.
- If a step fails, the plan can be revised **once**. Hard limit: never loops.
- The plan is made from the question alone, before any document is read (safety, see `safety.md`).
- Agent loop: only if plan-first fails for most cases. No comparison test up front. Q28, ADR-0002.

### 3.2 Search
- Semantic search (embeddings) + metadata filters (company, doc type, period, section) from the router output. Shared store: V3 searches all chunks; nobody gives it the document. Q24.
- **Filter rule (Q104, replaces the boost in Q100):** company, year and doc type are **hard filters**, applied as one filter: `doc_name` is one of the documents chosen by code from the catalog (`router.md` §2.2: year Y, else Y+1; doc type only when the question names it). No company named → no filter. Section is not filtered.
- **Fallback:** no document matches → the route is `not_covered` before any search (coverage check). If a covered search returns nothing useful, the answer says "could not find" (retrieval failure, not a correct refusal). Q25, Q33.
- **Built (2026-11-21):** `Searcher.search(..., doc_names=...)` (Qdrant `MatchAny` on the indexed `doc_name`); routed pipeline in `src/filing_rag/engine/routed.py`. Free test Hit@5 0.48 → 0.62 (`experiments/m2/RESULTS_router_search.md`).
- **Split tables (Q105):** a table above the token limit is stored as row groups with one `table_id`. When the search returns one part, code adds the other parts of the same table (nearest parts first, at most `table_parts_max_extra` = 3 extra chunks per question), so the answer step reads the whole table. No LLM call.
- **BM25 keyword search and a reranker:** added only when dev evals show the need, each with a before/after eval recorded. Q26, Q27.

### 3.3 Calculator tool
- The LLM picks the formula and the cited inputs. Code does the arithmetic.
- Returns result + formula + inputs. Units handled explicitly (millions vs billions, %). Q29, ADR-0003.
- **Built in M2 (Q107), not M3:** without it, every calculate / compare question fails the number check. The calculations are part of the answer JSON (no extra LLM call). Ops: `add` (2+ inputs), `subtract` (a − b), `divide` (a / b, a ratio), `ratio_pct` (a / b × 100), `pct_change` ((b − a) / |a| × 100). Inputs are claim IDs or earlier calculation IDs. Code converts the scale (thousand / million / billion) and refuses inputs of different families (USD vs % vs count) and a division by zero. The planner (several searches) stays in M3.

### 3.4 Answer writer
- Structured JSON always. No free text from the LLM. Code validates the JSON, then renders text. Q31.
- **Schema (Q107):** `found`, `claims` (each: `id`, `label`, `extract` = the number of the extract in the prompt, `quote` = exact text copied from that extract, `value` as printed or null, `unit` with its scale, `period`), `calculations` (each: `id`, `op`, `inputs`, `label`, `unit`), `main` = the claim or calculation ID that answers the question (or null), `answer` = a short sentence that uses **placeholders** (`{c1}`, `{k1}`) and never writes a number itself.
- The model cites the extract number; code maps it to the chunk ID (fewer copy errors than long IDs).
- Answers show the period: code adds the company, document type and period end from the chunk metadata of the checked claims, not from the LLM. Q25.
- Broken JSON (invalid, missing field, cut off): retry once, then a clear error. Log every retry; track the structure-valid rate. Q32.

### 3.5 Claim + quote check (code)
- Quote must exist in the cited extract. Allowed differences: whitespace (aligned table columns), case, curly quotes, dashes, non-breaking spaces. A quote needs at least 3 words, one with letters (a bare number proves nothing).
- The claim value must appear in the quote as printed ("1,788", "(1,788)" for a negative, decimals, "1.8 billion").
- A calculation passes only when all its inputs passed and the calculator accepts it.
- Failed claims are removed, with the reason logged (`bad_extract`, `quote_not_found`, `quote_too_short`, `value_not_in_quote`, `calc_error`). No retry for a failed check (minimum LLM calls). Q30, ADR-0003.

### 3.6 Final rule (code)
- Every step found a checked fact → answer.
- Some steps failed → partial answer that says exactly what was not found.
- Nothing passed → refuse with the reason ("could not find").
- **Rules (Q107):** `found` false or no claim passed → refuse. The `main` item passed and every placeholder in the sentence passed → answer, with the sentence filled by code. The sentence is used only when it has no digits outside placeholders (years and dates allowed); otherwise code writes a plain sentence from the checked items. The `main` item failed, or a used item failed → partial: the checked items + "could not check: <label>". No number reaches the user unless it passed the check or came from the calculator.
- The plain-RAG baseline keeps its old answer format (frozen for the comparison).

## 4. Multi-turn chat
- The engine receives the stand-alone question (rewritten from the follow-up) plus the chat history. Q64.
- Where the rewrite happens: build time, minimum-LLM-calls rule. Q65.

## 5. Models

| Job | Model | Ref |
|---|---|---|
| Planner, fact reading, answer writer | Claude Sonnet 5.5 (for now; re-tune by cost-vs-accuracy test) | Q36 |
| Backup when Claude is down | An OpenAI model (build time) | Q53 |

One swappable model layer: a model change is a config change. Q35, ADR-0005.

## 6. Scope notes
- Question types: find a number, calculate, explain why, compare years. Compare companies: kept, **low priority**, dev-tested only. Q16.
- Conflict flagging: **not in v1**. Add it only if real conflicts are found in the data (M8). Q15.

## 7. Tests
- Unit: calculator, quote checker, JSON validator, final rule, plan step runner (fake LLM).
- Integration: fake LLM with recorded replies + a real local store.
- Dev evals: accuracy per question type, claim-check failure rate, structure-valid rate.

## 8. Open at build time
Prompts; JSON schemas per question type; length limits per type; search settings (top-k, filters); follow-up rewrite location.
