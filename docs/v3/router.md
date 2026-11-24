# Spec — Router

**Status:** design approved (grilling 2026-11-18 → 2026-11-19); schema and filter rule set 2026-11-21 (Q104). Building (M2).
**Milestone:** M2.
**Sources:** `docs/V3_GRILLING_LOG.md` Q25, Q33, Q34, Q36, Q43, Q45, Q48, Q64, Q65, Q104. ADR-0004.

## 1. Purpose

Decide what to do with a question **before** any search. The router stops off-topic, unsafe and unanswerable questions early, and gives the planner clean, structured details.

## 2. Input and output

| | Value |
|---|---|
| Input | The user question + the chat history (multi-turn) |
| Output | JSON (schema below): `route`, `standalone_question`, `reason`, `steps`, `other_companies`, `doc_type`, `metric` |

### 2.1 JSON schema (Q104, steps Q109)

**Q109 change (2026-11-23):** `companies` and `years` are replaced by `steps` (the plan, `engine.md` §3.1). Each step is `{company, year, search}`: `company` from the 40-name enum or `null` (no company named), `year` 2000–2030 or `null` ("latest" / no year), `search` = short search text for that one fact. One step per company + year pair the question names; at least 1 step for route `answer`; duplicate pairs removed by code. More than 4 steps → code sets route `unclear` with "Please ask about at most 4 company-year pairs." The companies of a decision = the step companies. The rows below for `companies` / `years` describe the M2 schema (kept for the record).

Every field is always present (strict schema, `additionalProperties: false`). "Optional" means the value can be empty (`[]`) or `null`.

| Field | Filled by | Possible values | Must have a value? |
|---|---|---|---|
| `route` | LLM, then code | LLM: `answer`, `unrelated`, `advice`, `unclear`. Code: `answer` → `not_covered` after the coverage check | Yes |
| `standalone_question` | LLM | Full question that makes sense alone (a follow-up is rewritten with the chat history) | Yes |
| `reason` | LLM | Short text. For `unclear`: the one clarifying question | Yes |
| `companies` | LLM | List of the 40 company names in the collection (enum) | No: `[]` |
| `other_companies` | LLM | List of named companies that are **not** in the collection (for example "Tesla") | No: `[]` |
| `years` | LLM | Whole numbers 2000–2030: only the years the question names. "Latest" / "most recent" → `[]` | No: `[]` |
| `doc_type` | LLM | `10-K`, `10-Q`, `8-K`, `earnings`, `annual report`; **only when the question names it** | No: `null` |
| `metric` | LLM | Short text, for example `"revenue"` (logged, not used in search) | No: `null` |

Code checks (Pydantic): `unclear` → `reason` holds the clarifying question; for `unrelated` / `advice` the company and year fields are not used. Broken JSON → one retry, then a clear error (Q32).

### 2.2 Document selection and filters (Q104)

The LLM gives only the years the question names. **Code** chooses the documents from the catalog (one row per document, built from the stored chunk payloads, so it uses the same `fiscal_year` as the search):

1. For each company and each year Y: documents with `fiscal_year = Y`; if none, documents with `fiscal_year = Y+1` (the next filing holds Y as its prior-year column). Never Y−1 (an older filing cannot hold a later year). This is "option A"; "always Y and Y+1" (option B) was measured as the alternative.
2. No year in the question → all documents of the company.
3. `doc_type` set → keep only that type.
4. Twin documents of the same year (for example a 10-K and an annual report) → both kept.
5. No company → no document filter (search everything).

**Q109:** the selection runs once per step (the step's company and year), so each step has its own document list and its own search. The decision's `doc_names` (logs, coverage) is the union of the step lists. A step without a company has no filter.

The search then uses one **hard filter**: `doc_name` is one of the chosen documents. So company, year and doc type are all hard filters, applied through the document list. Known limit: a year reported only in an older 5-year table (for example 2015 from a FY2020 10-K) is not reached.

## 3. Checks, in order

1. **Unrelated / injection** ("write a poem", "ignore your rules", "show your system prompt") → polite refusal. Q43.
2. **Investment advice** ("Should I buy Apple stock?") → refuse, say why, then offer the facts from the filings. Separate `advice` route. Q48.
3. **Parse** company, period, metric, filing type.
4. **Coverage check (code, not LLM):** look up the document catalog. Covered = the company has a document for year Y or Y+1 (and of the named doc type, if any); no year named → the company alone is enough. Not covered, or a company in `other_companies` → `not_covered`: "No filing for that period in the collection."
5. **Too unclear** → ask back one short question.
6. Otherwise → `answer` route → planner.

## 4. Routes

| Route | Reply |
|---|---|
| `unrelated` | Polite refusal: V3 only answers questions on the filings |
| `advice` | Refusal + reason + offer of the factual version |
| `not_covered` | "No filing for <company> <period> in the collection" |
| `unclear` | One clarifying question |
| `answer` | Go to the planner |

## 5. Key decisions

| Decision | Choice | Ref |
|---|---|---|
| Separate router before the planner | Yes | Q33, ADR-0004 |
| How it decides | One call to a cheap LLM (Claude Haiku 5.5), JSON output. Code does the coverage check | Q34, Q36 |
| Fiscal year | A year in a question = that company's fiscal year. Ask back only for "calendar year" or "last 12 months" | Q25 |
| Follow-up rewrite ("And FY2021?") | Folded into the router call: the router gets the recent chat history and returns `standalone_question`; search uses it. No extra LLM call. History length tested at M3 | Q65, Q104 |
| Filters | Company, year (Y else Y+1) and named doc type are hard filters, applied as a list of documents chosen by code | Q104 (replaces the boost in Q100) |
| Jev / other decision models | Not used | Q34 |
| Planner | Folded into the router call as `steps` (one per company + year, max 4, no re-plan). No extra LLM call | Q109 |

## 6. After search (not the router)

If search finds nothing for a covered filing, V3 says "could not find", not "does not exist". The evals count this as a **retrieval failure**, not a correct refusal. Q33.

## 6.1 Built and measured (2026-11-21)

Code: `src/filing_rag/router/catalog.py` (document selection), `src/filing_rag/router/router.py` (Haiku 5.5, effort `low`, adaptive thinking; `between_tools` is rejected on Haiku), `src/filing_rag/engine/routed.py` (router → filtered search → answer).

| Measure | Result |
|---|---|
| Free search test, "perfect router" (`experiments/m2/RESULTS_router_search.md`) | Hit@5 0.48 (no filter) → 0.62 (rule A); rule B 0.62 with lower Hit@1; gold document 0.70 |
| Smoke test, 2 questions (`experiments/m2/RESULTS_smoke.md`) | Router JSON correct 2/2; answers 1/2; cost $0.0153; router 2.7–4.8 s |

Open causes: twin documents of the same year; the fiscal quarter is not used ("Q1 2023" → all 2023 documents); right page but the needed table chunk ranks low.

## 7. Tests

- Unit: catalog lookup, route rendering, JSON validation (with fake LLM replies).
- Dev evals: off-topic caught, injection caught, advice route correct, coverage correct, clarify correct. Part of these questions stay held out until M6. Q7, Q8.
- Repeat runs check that route decisions do not flip.
- Router check (Q109, `evaluation/router_check.py`): route vs `expected_route`; step pairs vs `gold_steps`; gold documents covered by the step documents; gold page in the top 5 of a step. Router calls only (no writer).

## 8. Open at build time

Prompt text; number of history turns sent for follow-ups (M3). Decided: JSON schema (2.1), document selection (2.2), follow-up rewrite in the router call.
