# V3 Design — AI Research Assistant for Equity Analysts

**Status:** Design complete after the grilling (Q1–Q83, 2026-11-04 → 2026-11-19). Next: M0.
**Started:** 2026-10-05. **Rewritten:** 2026-11-19 as an overview. The previous long version is in git history (commit `3248756`).

**How to read the V3 docs:**

| Need | File |
|---|---|
| The big picture (this file) | `docs/V3_DESIGN.md` |
| Details per component | `docs/v3/*.md` (specs) |
| Why the hard-to-reverse choices were made | `docs/adr/0001–0007` |
| Every question, answer and verdict | `docs/V3_GRILLING_LOG.md` |
| Terms | `GLOSSARY.md` |

**Rule:** a decision lives in one spec. This file summarises and links; it does not repeat details. When a decision changes, update the spec first, then this summary.

---

## 1. Purpose and goal

A portfolio project that shows **expertise in building a RAG system end to end**, built like a real product. When a recruiter or interviewer opens the repo, the first impression should be: *"This person can build a production AI system end to end, with solid system design."*

V3 is a **chat assistant for equity analysts**. It answers questions about real company filings **correctly, with checked evidence, and knows when it cannot answer**.

V3 is not framed as an alternative to commercial tools (Bloomberg, AlphaSense). Q1.

**Honest framing:** a portfolio project cannot claim real production experience. It shows production *thinking* with evidence: measured targets, load and safety tests, monitoring, and an honest write-up of failures.

## 2. Data

- **Corpus:** the 361 FinanceBench PDFs (269 10-K, 30 8-K, 27 10-Q, 29 earnings, 6 annual reports; 2015–2024). No SEC HTML, no XBRL. [ADR-0001](adr/0001-financebench-pdf-corpus.md)
- **Why:** a human-checked benchmark with answers, on real, messy PDF filings. Q2.
- No user uploads. Q49.
- Licence CC-BY-NC-4.0: credit FinanceBench.

## 3. Architecture

```
            ┌──────────── React UI (login, chat, sidebar, progress, citations) ────────────┐
            │                                                                              │
Keycloak ◄──┤                      API service (FastAPI, SSE, rate limits, chats)          │
            │                                     │                                        │
            │                       Answering engine (library)                             │
            │   Router (Haiku) → coverage check (catalog) → Planner (Sonnet) → steps:      │
            │   search (vectors + filters) → read fact → calculator (code)                 │
            │   → answer writer (JSON, Sonnet) → claim + quote check (code) → final rule   │
            │                                     │                                        │
            │        Vector store + database (chunks, catalog, chats, logs)                │
            └──────────────────────────────────────────────────────────────────────────────┘
Ingestion (batch): 361 PDFs → PDF reader → period dates → split + table labels → local embeddings → store
Observability: Langfuse traces + metrics/alerts tool. Evaluation runner: dev set, locked benchmark, baseline.
```

| Part | Spec | Key choices |
|---|---|---|
| Ingestion | [ingestion.md](v3/ingestion.md) | PDF reader by test (no FinanceBench evidence); period dates from cover page; one chunk per table + search label; free local embeddings; store by test |
| Router | [router.md](v3/router.md) | One Haiku call (JSON) + code coverage check. Routes: unrelated, advice, not_covered, unclear, answer. [ADR-0004](adr/0004-router-before-search.md) |
| Answering engine | [engine.md](v3/engine.md) | Plan first, max one re-plan ([ADR-0002](adr/0002-plan-first.md)); semantic search + filters + fallback; calculator in code; JSON claims + quotes checked by code ([ADR-0003](adr/0003-code-maths-and-quote-checks.md)); answer / partial / refuse rule |
| API | [api.md](v3/api.md) | Only front door; SSE progress then checked answer; Keycloak tokens ([ADR-0006](adr/0006-keycloak-login.md)); full rate limits; chats per user, 30-day deletion |
| UI | [ui.md](v3/ui.md) | React ([ADR-0007](adr/0007-react-ui.md)); ChatGPT-style sidebar; citation details only (no PDF viewer) |
| Evaluation | [evaluation.md](v3/evaluation.md) | Locked FinanceBench 150 + held-out behaviour subset; dev set (Claude drafts, user confirms); plain-RAG baseline; code + OpenAI judge; failure causes; 3 repeat runs |
| Safety | [safety.md](v3/safety.md) | 9 threats, each with a defence and a test |
| Observability | [observability.md](v3/observability.md) | Logs, Langfuse traces, metrics + alerts, quality monitoring |
| Tests and CI | [testing-ci.md](v3/testing-ci.md) | Free layers on every push; real-AI runs manual with cost shown |
| Deployment | [deployment.md](v3/deployment.md) | Deferred to M7 |

## 4. Models

| Job | Model |
|---|---|
| Router | Claude Haiku 5.5 |
| Planner, fact reading, answer writer | Claude Sonnet 5.5 (for now) |
| Eval judge | OpenAI model (build time) |
| Backup when Claude is down | OpenAI model (build time) |
| Embeddings | Free local model (build time) |

One swappable model layer. [ADR-0005](adr/0005-model-providers.md)

**Design rule:** count the LLM calls per question. Add a new call only when a measured need shows it. Q65.

## 5. Scope

| Ability | Status |
|---|---|
| Find a number, calculate, explain why, compare years | Core |
| Multi-turn chat with follow-ups | Core |
| Refuse / ask back / advice route / not covered | Core |
| Compare companies | Low priority, dev-tested only (Q16) |
| Flag conflicts | Not in v1; only if real conflicts are found (Q15) |
| BM25 keyword search, reranker | Only on measured need (Q26, Q27) |
| Agent loop | Only if plan first fails for most cases (Q28) |

No "minimum version" cut line: the full plan is built. Q14.

## 6. Production targets

| Target | Rule |
|---|---|
| Speed (median, p95) | Set after the first measurement (M2), reason written down. Progress shown while waiting |
| Cost per question (median, p95) | Set after the first measurement (M2). Recorded per question and per step |
| Load | Set after the load test (M5). Above capacity: short queue + "busy" message |
| Availability | Retry → fall back to OpenAI → clear error. Never a hang, never an unchecked answer. Health endpoint |
| Rate limits | Full production setup, demo-sized numbers (set at deploy) |

Rough estimates (not measured): simple question ≈ $0.03, 7–10 s; complex ≈ $0.08–$0.15. Q51, Q52.

**If constraints change** (interview question): more users → several API servers, shared Redis limits, queue + workers, caching; stricter speed → parallel steps, smaller models; lower cost → small models for most steps; 100× more documents → dedicated vector database, stronger pre-filtering; high availability → multi-zone servers, replicas, failover.

## 7. Milestones

Rules: walking skeleton first, then depth. Baseline and eval runner early. The locked benchmark is opened only at M3 and M6, 3 runs each.

| # | Milestone | Done when | Measured |
|---|---|---|---|
| M0 | Foundations | V2 code removed from `v3`; layout; env settings; basic CI; 361 PDFs + 150 questions downloaded, **150 locked**; dev set drafting starts; `V3_LEARNING.md` | — |
| M1 | Walking skeleton + baseline | Few companies ingested; PDF reader and store chosen by test; chunk metadata with period dates; plain-RAG baseline in the eval runner | First dev scorecard |
| M2 | Core engine, all 361 PDFs | Router + coverage check; semantic search + filters; JSON claims + quote check; API with SSE | vs baseline; refusal rate; citation pass rate; **speed/cost targets set** |
| M3 | Hard questions | Planner, calculator, multi-turn, year comparisons, company comparisons (low priority) | Failure causes; **locked run 1**; judge-vs-human agreement |
| M4 | Users + UI | Keycloak; chats per user + sidebar + 30-day deletion; React UI | — |
| M5 | Safety + production | Safety test set; full rate limits; retries + OpenAI fallback; Langfuse + metrics + alerts; quality gate + weekly eval (manual); load test | Safety pass rates; load number |
| M6 | Final test | Failure-by-cause analysis | **Locked run 2**; held-out behaviour subset |
| M7 | Deploy + showcase | Hosting, Docker, recruiter access, limit numbers; README, architecture diagram | — |
| M8 | Optional | MCP server (A4), open dataset (A5), conflict flagging, blog post, revisit P1 | — |

**Build workflow (per component):** explain what, why, key decisions and a step plan → user approves → code + unit tests → next component. Free runs are run directly; any LLM or paid run needs approval and a cost estimate first.

**Learning notes:** `V3_LEARNING.md` (gitignored), updated after each milestone: what was built, why, trade-offs, failures, likely interview questions.

## 8. Showcase

- **README is the main technical write-up.** No demo video; the live demo shows the system working. A blog post is optional (M8). Q76, Q77.
- **Layers:** 30 seconds (problem line, headline numbers, live demo link) → 2–5 minutes (architecture diagram, results by question type and failure cause, top decisions with rejected options, limits, quickstart) → deep dive (specs, ADRs, eval report, load and safety reports, failure write-ups).
- **Headline numbers:** chosen at M7 from real results. Candidates: FinanceBench accuracy vs plain RAG, correct-refusal rate, citation-check pass rate. Q78.
- **Honesty rules:** failures shown; every number links to its run; FinanceBench credited; a short "V2 → V3" section; published FinanceBench paper numbers (vector RAG ≈ 50%, long-context ≈ 79%) cited as reference points.
- When V3 is ready, make its branch the GitHub default.

## 9. Value additions

| # | Addition | Priority |
|---|---|---|
| A1 | Accuracy vs cost chart (every setup tried as one dot) | M3 onward |
| A2 | "Knows when it can't" curve (answered share vs accuracy) | M3 onward |
| A3 | Failures become dev-set regression tests (never the locked set) | M2 onward |
| A4 | MCP server over the same API | Low (M8) |
| A5 | Open release of the dev set | Very low (M8) |

## 10. Top risks

| # | Risk | Defence |
|---|---|---|
| 1 | The PDF reader reads tables badly | Reader chosen by test in M1; failure tags separate parsing from retrieval |
| 2 | Scope is large for one person | Walking skeleton; core engine and locked run 1 before users/UI; M8 optional |
| 3 | Dev-set bias (Claude drafts and answers) | User confirms every dev question; locked set is human-written; OpenAI judge |
| 4 | Cost of real-AI runs (locked runs ≈ $45–$135, estimate) | Every real-AI run manual, cost shown first |
| 5 | "Why not long context?" has no measured answer | Cite paper numbers; optional small long-context run |

Also: PDFs hosted on company sites can disappear → download once in M0, keep checksums.

## 11. Interview pitch (draft, to refine)

"V3 is a chat assistant that answers equity-analyst questions from 361 real SEC filings. Every number in an answer comes with an exact quote that code checks, and every calculation is done by code, not the model. I measured it on FinanceBench, a human-written benchmark where plain vector RAG scores about 50%, against my own plain-RAG baseline, and I report failures by cause. It runs like a real product: login, per-user rate limits, fallback to a second AI provider, traces, metrics and alerts."

## 12. Decided at build time

| Item | Spec |
|---|---|
| PDF reader; table-label method; chunk sizes; embedding model; vector store | ingestion.md |
| Follow-up rewrite location; router prompt and schema | router.md |
| JSON schemas and length limits per question type; search settings | engine.md |
| Dev set size and categories; judge model; quality-gate margin | evaluation.md |
| Metrics/alerts tool; alert destination | observability.md |
| Next.js vs plain React; end-to-end UI tests | ui.md, testing-ci.md |
| Hosting, Docker, recruiter access, limit numbers, account spending caps | deployment.md (M7) |

**Parked:** P1 — revisit financebenchmark.ai categories after the build plan is done.
