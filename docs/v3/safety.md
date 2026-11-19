# Spec — Safety

**Status:** approved (grilling 2026-11-19). Not built.
**Milestone:** M5 (safety test set); defences are built with each component.
**Sources:** `docs/V3_GRILLING_LOG.md` Q40–Q49, Q60, Q61. V3_DESIGN.md Step 6.

## 1. Access

- The demo is reached by link only, and the link opens a **login page** (Keycloak). Q40, Q60.
- Per-user limits (first idea: about 5 questions per day). Final numbers in the deploy stage. Q41, Q42.

## 2. Threats and defences

| # | Threat | Defence | Test | Ref |
|---|---|---|---|---|
| 1 | Hidden instructions inside a PDF (indirect prompt injection) | (a) Document text is marked as data only. (b) The plan is made from the question alone, before any document is read; a re-plan sees only structured step results. (c) Every claim is a code-checked quote | 20 planted documents in the dev set | Q44 → Q47 |
| 2 | User tries to trick V3 (direct injection, jailbreak) | Router `unrelated` route refuses. The system prompt holds no secrets | Injection prompts in dev evals | Q43 |
| 3 | Investment advice | Router `advice` route: refuse, say why, offer the facts | Advice prompts in dev evals | Q45 → Q48 |
| 4 | Off-topic use | Router `unrelated` route | Off-topic prompts in dev evals | — |
| 5 | Made-up or wrong numbers | Claim + quote check; code does the maths | Claim-check failure rate | Q29, Q30 |
| 6 | Cost abuse / overload | Login + full rate limits + per-question guards | Load test | Q54 |
| 7 | Leaked secrets | Keys only in environment settings, never in code or logs | Secret scan in CI | — |
| 8 | Bad files | Corpus is fixed, no uploads. Size/type checks; bad file skipped and logged at ingestion | Broken sample files in ingestion tests | Q49 |
| 9 | Account attacks (password guessing, weak password storage) | Keycloak handles hashing, brute-force protection and reset | Keycloak config check | Q61 |

Note: threat 1(c) in the old design also used the conflict rule. Conflict flagging is not in v1 (Q15), so defence 1 rests on (a)–(c).

## 3. Privacy

- Store full question and answer text in logs and chats. Delete after **30 days**. Q46, Q66.
- Risk is low: an SEC filing demo rarely gets personal data.

## 4. Safety test set

20 planted documents + user-side prompts for threats 2–4. A part is held out until M6 (`evaluation.md`). Pass rates, failures included, go in the README.
