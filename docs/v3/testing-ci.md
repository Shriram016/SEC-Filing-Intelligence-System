# Spec — Tests and CI

**Status:** approved (grilling 2026-11-19). Not built.
**Milestones:** M0 (basic CI), grows with each component.
**Sources:** `docs/V3_GRILLING_LOG.md` Q69–Q71. V3_DESIGN.md 8.3.

## 1. Layers

| Layer | What it checks | When | Costs money? |
|---|---|---|---|
| Code quality | Formatting, lint, type checks, secret scan, vulnerable dependencies | Every push | No |
| Unit tests | Parts alone: calculator, quote checker, router rules, catalog lookup, splitter, period parser, rate limiter, SSE builder | Every push | No |
| Integration tests | Parts together: real database in CI + **fake AI with recorded replies** | Every push | No |
| Ingestion tests | Broken or huge sample PDFs are skipped and logged | Every push | No |
| End-to-end UI tests (login, chat) | Decided at build time (for example Playwright) | — | No |
| Quality gate | ~20 dev questions with the real AI; fails if the score drops beyond a set margin | **Manual** for now | Yes |
| Weekly dev eval | Drift check | **Manual** for now | Yes |
| Full evals, load test, locked runs | Whole dev set; load; locked set at M3/M6 only | On demand | Yes |

## 2. Rules

- Every component comes with its unit tests (V3 build workflow).
- Free tests run automatically. Any run with real AI calls is manual and shows its cost first. Q70, Q71.
- The README states that the quality gate can run in CI and why it is manual (cost).

## 3. Tools

GitHub Actions + pytest (confirmed at build time). Frontend test tool chosen in M4.
