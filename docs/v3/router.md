# Spec — Router

**Status:** design approved (grilling 2026-11-18 → 2026-11-19). Not built.
**Milestone:** M2.
**Sources:** `docs/V3_GRILLING_LOG.md` Q25, Q33, Q34, Q36, Q43, Q45, Q48, Q64, Q65. ADR-0004.

## 1. Purpose

Decide what to do with a question **before** any search. The router stops off-topic, unsafe and unanswerable questions early, and gives the planner clean, structured details.

## 2. Input and output

| | Value |
|---|---|
| Input | The user question + the chat history (multi-turn) |
| Output | JSON: `route`, `company`, `period`, `metric`, `doc_type`, `reason`, and a full stand-alone question when the input is a follow-up (if folded in, see 5) |

## 3. Checks, in order

1. **Unrelated / injection** ("write a poem", "ignore your rules", "show your system prompt") → polite refusal. Q43.
2. **Investment advice** ("Should I buy Apple stock?") → refuse, say why, then offer the facts from the filings. Separate `advice` route. Q48.
3. **Parse** company, period, metric, filing type.
4. **Coverage check (code, not LLM):** look up the document catalog. No filing for that company/period → "No filing for that period in the collection."
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
| Follow-up rewrite ("And FY2021?") | Where it happens is decided at build time. Rule: do not add a new LLM call unless measured need shows it. Folding it into the router call is the first option | Q65 |
| Jev / other decision models | Not used | Q34 |

## 6. After search (not the router)

If search finds nothing for a covered filing, V3 says "could not find", not "does not exist". The evals count this as a **retrieval failure**, not a correct refusal. Q33.

## 7. Tests

- Unit: catalog lookup, route rendering, JSON validation (with fake LLM replies).
- Dev evals: off-topic caught, injection caught, advice route correct, coverage correct, clarify correct. Part of these questions stay held out until M6. Q7, Q8.
- Repeat runs check that route decisions do not flip.

## 8. Open at build time

Prompt text; exact JSON schema; where follow-up rewriting happens.
