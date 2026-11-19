# V3 Grilling Log

Record of the design grilling of `docs/V3_DESIGN.md`. One question per entry.
Verdict: **kept** (design unchanged), **changed** (design must change), **dropped** (question not relevant), **open** (not decided).

**Goal (confirmed 2026-11-04):** showcase expertise in building a RAG system end to end, through a portfolio project.

## Parked items (after the plan is complete)

- **P1 (2026-11-04):** Revisit https://financebenchmark.ai/ (third-party aggregator by Avae, not Patronus). Study its benchmark categories — All, Verification, Document QA, Forensic Reasoning, Numerical, Agent Task — and the benchmarks in each. Decide if any add value to V3.

---

## Area 1 — Problem statement

### Q1 — Pain point vs commercial tools (Bloomberg, AlphaSense, ChatGPT upload)
- **Answer (2026-11-04):** Not needed. V3 is a portfolio project to show RAG expertise, not an alternative to commercial tools.
- **Verdict:** dropped
- **Action:** none. Do not frame V3 against commercial products.

### Q2 — Why equity analysts + SEC filings, not a generic RAG demo?
- **Answer (2026-11-04):** (1) FinanceBench gives a ready, human-checked eval set with answers. (2) SEC filings are representative of real-world data in PDF files.
- **Verdict:** kept
- **Action:** use both reasons in the README "why this data" line. Follow-up Q3 checks the HTML-vs-PDF main source.

## Area 2 — Data

### Q3 — Main source format: PDF, HTML, or both?
- **Facts checked online (2026-11-04):** FinanceBench repo has 361 PDFs (269 10-K, 30 8-K, 27 10-Q, 29 earnings, 6 annual reports; 2015–2024), hosted on company IR sites/CDNs, not sec.gov. Evidence uses PDF page numbers. SEC EDGAR serves HTML + inline XBRL, no PDFs.
- **Answer (2026-11-04):** Stick with FinanceBench data. Main corpus = the 361 FinanceBench PDFs. SEC HTML not used in v1.
- **Verdict:** changed (design had SEC HTML as main source, PDF secondary)
- **Action:** after approval, update V3_DESIGN.md Step 2, Step 4.2–4.3, Stop 1 (PDF reader becomes core, not secondary), Stop 9 (no HTML/PDF dedup needed), milestones M1/M4. XBRL may still serve as dev answer key (to confirm in Area 3).

## Area 3 — Evals

### Q4 — Keep all 150 FinanceBench questions locked, or split some into dev?
- **Answer (2026-11-04):** All 150 are the benchmark (locked test) set. During development, use our own eval set.
- **Verdict:** kept
- **Action:** none for the split. Dev set source decided in Q5.

### Q5 — How is the dev eval set built?
- **Answer (2026-11-04):** Claude generates questions and answers from the project corpus; the user evaluates and confirms each one.
- **Verdict:** changed (design used XBRL auto-generated questions + half of a hand-made set; XBRL generation not chosen)
- **Action:** after approval, update V3_DESIGN.md Step 3.2 and 3.4. Size and categories decided next.

### Q6 — Dev set size and categories?
- **Answer (2026-11-04):** Decide at build time.
- **Verdict:** open (deferred to build time)
- **Action:** add to V3_DESIGN.md "Open questions".

### Q7 — Does the locked test include held-out behaviour questions (refuse, unclear, conflict, hidden instructions)?
- **Answer (2026-11-04):** No. Refusing, unclear and unrelated questions are part of the dev evals. The locked benchmark = FinanceBench 150 only, testing the core answering logic.
- **Verdict:** changed (design put half of the hand-made set in the locked test)
- **Action:** after approval, update V3_DESIGN.md Step 3.4 (locked test = FinanceBench 150 only).

### Q8 — Behaviour scores come from the tuned dev set; how to keep them honest?
- **Answer (2026-11-04):** Keep a small part of the dev behaviour questions (refuse, unclear, unrelated, conflict, hidden instructions) unseen until the end.
- **Verdict:** changed (adds a held-out behaviour subset)
- **Action:** after approval, update V3_DESIGN.md Step 3.4: two locked sets — FinanceBench 150 (core logic) + held-out behaviour subset (size decided at build time with Q6).

### Q9 — Which baselines? (plain RAG, long-context, closed-book)
- **Discussion:** user asked why baselines are needed when a benchmark with answers exists. Reason given: a score alone has no reference point; a baseline shows how much the V3 design adds; FinanceBench is hard, so a low score needs context.
- **Answer (2026-11-04):** Plain RAG only.
- **Verdict:** changed (design had plain RAG + long-context; closed-book was proposed)
- **Action:** after approval, update V3_DESIGN.md Step 3.3 and T4. Note the gap: the "why not long context?" interview question has no measured answer.
- **Reference numbers (FinanceBench paper):** GPT-4-Turbo vector-store RAG ≈ 50% correct; long-context ≈ 79%. Use these as published reference points in the README.

### Q10 — How to mark FinanceBench text answers?
- **Answer (2026-11-04):** Both: code checks numbers (value, unit, rounding); LLM judge (different model family, fixed rubric: correct / partly correct / wrong) marks text against the gold answer; user hand-marks a sample (~30–50) and the judge-vs-human agreement rate (or Cohen's kappa) is reported. Low agreement → fix the rubric/judge before trusting scores.
- **Verdict:** kept (extends Step 3.5 from "explain why" only to all FinanceBench text answers)
- **Action:** after approval, update V3_DESIGN.md Step 3.5.

### Q11 — Who tags the failure cause (parsing, planning, retrieval, generation, reasoning)?
- **Answer (2026-11-04):** Hybrid. (1) Code auto-tags retrieval (evidence page retrieved?) and parsing (gold number present in the parsed evidence page?). (2) An LLM reads the trace and suggests planning / generation / reasoning. (3) User confirms or corrects each suggested tag.
- **Verdict:** changed (design said "every failure is tagged by cause" without saying how)
- **Action:** after approval, update V3_DESIGN.md Step 3.5.

### Q12 — How many repeat runs per locked-test result?
- **Answer (2026-11-04):** 3 runs. Report mean with a range.
- **Verdict:** changed (T3 said "repeated runs" without a number)
- **Action:** after approval, update V3_DESIGN.md T3. Cost of 3 × 150 questions shown before each locked run.

### Q13 — README headline numbers?
- **Answer (2026-11-18):** Keep for now: (1) FinanceBench accuracy vs plain RAG, (2) correct-refusal rate, (3) citation-check pass rate.
- **Verdict:** kept (tentative; may revisit in the Showcase area)
- **Action:** none now.

## Area 4 — Scope

### Q14 — Define a "minimum impressive version" cut line?
- **Answer (2026-11-18):** No. Push and complete the full plan.
- **Verdict:** kept (full scope, no cut line)
- **Action:** none.

### Q15 — Keep "flag conflicts" in v1 with the FinanceBench-only corpus?
- **Context:** conflict cases came from SEC XBRL restatements (old data plan). The 361 PDFs (~9 per company) have no automatic list of conflicts; real conflicts may be rare.
- **Answer (2026-11-18):** Not needed for now. Include it when real conflicts are found in the data.
- **Verdict:** changed (moved out of v1; was a first-version ability)
- **Action:** after approval, update V3_DESIGN.md Step 3.1 behaviours, 4.1 abilities, Stop 7 (conflict rule), Step 6 threat 1(c) (planted figures were caught by the conflict rule — needs another defence or note), Step 10 demo item 3.

### Q16 — Keep "compare companies" in v1?
- **Context:** FinanceBench 150 has no cross-company questions (some compare years within one company). Tested only with dev questions.
- **Answer (2026-11-18):** Keep, but low priority for now.
- **Verdict:** changed (was a core question type; now low priority)
- **Action:** after approval, update V3_DESIGN.md Step 3.1 and 4.1 (compare companies = low priority, dev-tested only).

### Q17 — Is a public live demo part of the final goal?
- **Answer (2026-11-18):** Yes.
- **Verdict:** changed (Step 4.4 had deployment deferred and the live demo undecided)
- **Action:** after approval, update V3_DESIGN.md Step 4.4, Q1 and M7. Hosting, access control and spending cap decided in the Deployment area.

### Q18 — Keep M8 (publish the dev eval set as an open dataset)?
- **Answer (2026-11-18):** Very, very low priority.
- **Verdict:** changed (M8 / A5 becomes optional, last)
- **Action:** after approval, mark M8 and A5 as optional in V3_DESIGN.md.

### Q19 — Keep the MCP server (A4)?
- **Answer (2026-11-18):** Keep, low priority.
- **Verdict:** changed (was planned in M5; now low priority)
- **Action:** after approval, mark A4 low priority in V3_DESIGN.md.

## Area 5 — System design

### Q20 — How to check which PDF reader extracts tables correctly (XBRL dropped)?
- **Answer (2026-11-18):** Both: FinanceBench evidence text + user hand-check of a sample.
- **Verdict:** changed (Stop 1 compared readers against XBRL numbers)
- **Action:** after approval, update V3_DESIGN.md Stop 1. See Q21 (locked-test leakage risk).

### Q21 — Using FinanceBench evidence pages to choose the PDF reader = test leakage?
- **Answer (2026-11-18):** Agreed. Choose the reader only on pages not used by any FinanceBench question, with the user's hand-check. FinanceBench evidence is NOT used for the reader test.
- **Verdict:** changed (overrides Q20: reader test = non-FinanceBench pages + hand-check only)
- **Action:** after approval, update V3_DESIGN.md Stop 1 and add a general rule to Step 3.4: no tool, setting or prompt is chosen using locked-test questions or their evidence pages.

### Q22 — Add a search label (description) to each table chunk?
- **Answer (2026-11-18):** Yes. Per table: (1) detect, (2) copy exactly (numbers, rows, columns, units), (3) add a 1–2 sentence label (company, period, unit, main row names in plain words), (4) store table + label as one chunk. Search uses the label; the answer step reads the exact table. The source document is not changed.
- **Verdict:** changed (Stop 2 kept tables whole but had no search label)
- **Action:** after approval, update V3_DESIGN.md Stop 2 and Stop 3. How labels are made: Q23.

### Q23 — Who writes table labels: code template, LLM, or both by test?
- **Note:** table count (20k–40k) was Claude's unverified estimate (≈50–100 tables per 10-K × 361 docs). Real count known only after parsing.
- **Answer (2026-11-18):** Cannot decide without looking at the tables. Decide at build time.
- **Verdict:** open (build time)
- **Action:** add to V3_DESIGN.md "Open questions".

### Q24 — Shared store or single store?
- **Context:** FinanceBench paper reports both. Shared store = search all documents; single store = a human gives the correct document first ("chat with this PDF").
- **Answer (2026-11-18):** Shared store. V3 searches all chunks, using metadata filters (company, filing type, period, section) that it extracts from the question itself. Nobody gives it the document.
- **Verdict:** kept (matches Stop 3)
- **Action:** README must state "shared store" and compare only with the paper's shared-store results. Proposed addition (to confirm in Q25): fallback search with a looser filter when the filter finds nothing.

### Q25 — Fiscal-year handling and filter fallback
- **Facts checked (2026-11-18):** FinanceBench doc_name = `COMPANY_YEAR[Qn]_TYPE` (e.g. `APPLE_2022_10K`, `APPLE_2023Q3_10Q`, `AMCOR_2022_8K_dated-2022-04-26`). doc_period is a plain year; no fiscal year-end field. Names have errors (misspelling `ACTIVSIONBLIZZARD`, mixed case `Pfizer_...`, one duplicate with different doc_period).
- **Answer (2026-11-18), final approach:**
  1. A year in a question = that company's **fiscal year**. No clarifying question.
  2. At ingestion, read the real period dates from each PDF cover page and store them on every chunk. Do not trust file names.
  3. Show the period dates in the answer (e.g. "Apple FY2022, ended Sep 2022"), so different year-ends are visible.
  4. Ask back only if the user says "calendar year" or "last 12 months".
  5. If the filtered search finds nothing, search again with fewer filters.
- **Verdict:** changed (T1 said ambiguous periods trigger "ask when unclear"; now fiscal year is the default and dates are shown instead)
- **Action:** after approval, update V3_DESIGN.md T1, Stop 2 (period dates from cover page), Stop 3 (fallback), Stop 7 (unclear rule).

### Q26 — Search parts: start with hybrid (embeddings + BM25) + reranker, each proven by ablation?
- **Answer (2026-11-18):** Start with semantic (embedding) search + metadata filters only. If evals fail a lot, add hybrid (BM25 keyword) and test again.
- **Verdict:** changed (Stop 3 started with hybrid + reranker). Note: hybrid is the production standard; starting simple and adding by measured need is a valid, defensible order.
- **Action:** after approval, update V3_DESIGN.md Stop 3. Reranker decided in Q27.

### Q27 — Reranker from the start or later?
- **Answer (2026-11-18):** Later. Add the reranker only when dev evals show the need, same as BM25.
- **Verdict:** changed (Stop 3 had a reranker from the start)
- **Action:** after approval, update V3_DESIGN.md Stop 3: v1 search = embeddings + metadata filters + fallback; BM25 and reranker added by measured need, each with a before/after eval recorded.

### Q28 — Plan first (max one re-plan) or agent loop?
- **Discussion:** V3 is multi-step ("agentic") RAG: each "find" step is one retrieval, "calculate" is the calculator tool. Fixed template (V2) < plan first (LLM writes steps once per question) < agent loop (LLM decides after every step). Plan first fits predictable finance questions: fixed cost, safety (plan made before documents are read), easy debugging.
- **Answer (2026-11-18):** Plan first. Consider the agent loop only if plan first fails for most cases. No comparison test up front.
- **Verdict:** changed (Stop 4 had a planned plan-first vs agent-loop comparison; now only on need)
- **Action:** after approval, update V3_DESIGN.md Stop 4.

### Q29 — Code does the maths?
- **Answer (2026-11-18):** Yes. All calculations are done by code via a calculator tool. The LLM does no arithmetic at all; it only picks the formula and the cited inputs.
- **Verdict:** kept (Stop 5)
- **Action:** none.

### Q30 — Claims + exact quotes, checked by code?
- **Discussion:** three industry levels — sources listed only (V2), inline [N] unchecked, quote-level checked (high-trust domains; e.g. Anthropic Citations API returns exact quoted text; Vertex AI grounding and Azure groundedness detection check support).
- **Answer (2026-11-18):** Keep. LLM writes claims with exact quotes + chunk IDs; code checks quote exists in the chunk and numbers appear in the quote or come from the calculator; failed claims removed.
- **Verdict:** kept (Stop 6)
- **Action:** none.

### Q31 — Structured JSON output or free text? (Stop 6b)
- **Answer (2026-11-18):** Structured JSON always. No free text from the LLM. Code validates the JSON, then renders readable text for the user.
- **Verdict:** changed (Stop 6b was open)
- **Action:** after approval, update V3_DESIGN.md Stop 6b. Bad-output handling: Q32.

### Q32 — What to do on broken JSON (invalid, missing field, cut off)?
- **Answer (2026-11-18):** Retry the call once. If it fails again, show a clear error.
- **Verdict:** changed (Stop 6b was open)
- **Action:** after approval, update V3_DESIGN.md Stop 6b. Log every retry and failure; track the structure-valid rate as a metric.

### Q33 — Refusals: kinds, and a separate router before search
- **Discussion:** user raised 3 kinds of "can't answer": (1) off-topic (weather) — was in Step 6; (2) data not in the collection (e.g. no 3M 2021 filing) — was MISSING; must be known before search; (3) data exists but retrieval missed it — a retrieval failure, not a correct refusal.
- **Answer (2026-11-18):** Add a separate **router** component before the planner. Checks in order: (1) safety / off-topic / buy-sell advice → polite refusal; (2) parse company, period, metric, filing type; (3) coverage check against a **document catalog** built from the 361 PDFs' metadata → "no filing for that period"; (4) too unclear → ask back. Only then → planner → retrieval. After search, the rule-based answer / partial answer / refuse stays (Stop 7); V3 says "could not find" (not "does not exist"), and evals count it as a retrieval failure.
- **Verdict:** changed (new component; Step 6 input check and Stop 7 "ask when unclear" move into the router)
- **Action:** after approval, update V3_DESIGN.md Stop 4, Stop 7, Step 6, Step 8.1 (new part), architecture diagram. Add router eval scores (off-topic caught, coverage correct, clarify correct) to dev evals.

### Q34 — How does the router decide?
- **Discussion:** user asked about Jev (TypeSafe AI decision model, launched 2026-09-15; typed answers + probabilities; vendor-claimed calibration; one independent test found scikit-learn better calibrated). Fits yes/no checks, weak for open values (period, metric).
- **Answer (2026-11-18):** Router = one call to a cheaper LLM with JSON output (on-topic, advice, unclear, company, period, metric, filing type). Code does the coverage check against the catalog.
- **Verdict:** changed (new decision for the new router)
- **Action:** after approval, record in V3_DESIGN.md Stop 8 (model per job) and the router section. Jev not used; may be noted as a possible later experiment.

### Q35 — Model approach: model per job, swappable, which provider?
- **Answer (2026-11-18):** Provider = Claude (Anthropic API), not Groq. Model per job and the swappable model layer are kept.
- **Verdict:** changed (Stop 8 started with Groq)
- **Action:** after approval, update V3_DESIGN.md Stop 8, Step 7.2 (cost targets were set for Groq prices — re-check), Step 7.4 (backup provider). Eval judge must be a different model family from Claude (Step 3.5) — to confirm. Per-job model choice: Q36.
- **Clarification (2026-11-18):** "Claude" = "Anthropic" — same provider (Anthropic API).

### Q36 — Which Claude model per job?
- **Prices (cached 2026-11-03, per 1M tokens in/out):** Haiku 5.5 $0.10/$0.50; Sonnet 5.5 $2/$10; Opus 5.5 $4/$20. Note: Step 7.2 cost target (< $0.01 median) was set for Groq; one Sonnet answer call with ~10k input tokens ≈ $0.02.
- **Answer (2026-11-18):** Router = Claude Haiku 5.5. Planner, fact reading and answer writing = Claude Sonnet 5.5 "for now" (can be re-tuned later by cost-vs-accuracy test).
- **Verdict:** changed (Stop 8 picked models at build time)
- **Action:** after approval, update V3_DESIGN.md Stop 8. Re-check Step 7.2 cost targets against Sonnet prices.

### Q37 — Eval judge model family?
- **Answer (2026-11-18):** An OpenAI model (different family from Claude). Exact model chosen at build time (e.g. gpt-oss-120b, used in V2).
- **Verdict:** kept (Step 3.5 / Stop 8 rule: judge from a different family)
- **Action:** after approval, record in V3_DESIGN.md Stop 8.

### Q38 — Embedding model?
- **Answer (2026-11-18):** Free local model (e.g. BGE family). Exact model chosen at build time.
- **Verdict:** changed (Stop 8 planned a comparison against at least one paid option; now free local only)
- **Action:** after approval, update V3_DESIGN.md Stop 8.

### Q39 — Vector store (Stop 9)?
- **Answer (2026-11-19):** Choose at build time by a test. Candidates: PostgreSQL + pgvector, Qdrant, ChromaDB. At about 100k–300k chunks (estimate, not measured), volume does not decide. Decide on filter quality, built-in keyword search (for BM25 later), one DB for logs + eval results, and ease of deploy. HTML/PDF dedup is no longer needed (PDF-only corpus).
- **Verdict:** kept (Stop 9 already said "decide at build time")
- **Action:** after approval, remove the HTML/PDF dedup note from V3_DESIGN.md Stop 9 and add the decision criteria.

## Area 6 — Safety (Step 6)

### Q40 — Who can use the live demo?
- **Answer (2026-11-19):** Only people with a link (unlisted URL). No public listing, no login.
- **Verdict:** open (Step 6 threats must be re-checked for a link-only demo: a shared link can leak, so cost and abuse limits still apply)
- **Action:** after approval, record the access model in V3_DESIGN.md Step 6 and Step 8 deployment.

### Q41 — Spend limit for the live demo?
- **Answer (2026-11-19):** Yes, the demo has a spend limit. Amount and behaviour at the limit: see Q42.
- **Verdict:** kept (Step 6 / Step 7 already plan rate limits and a spending cap)
- **Action:** after approval, record the cap in V3_DESIGN.md Step 6 and Step 8.

### Q42 — Limit amount and period?
- **Answer (2026-11-19):** A question limit, not a dollar limit: about 5 questions per day (first idea). Final design waits until the recruiter use case is clear.
- **Verdict:** open (decide with the deployment area / showcase plan)
- **Action:** revisit in the Deployment area. Then record in V3_DESIGN.md Step 6 and Step 8.

### Q43 — Prompt injection in the user question?
- **Answer (2026-11-19):** Refuse it. The router treats it as an unrelated question. Add injection questions to the dev eval set (behaviour tests).
- **Verdict:** kept (Step 6 lists prompt injection; now routed through the router's "unrelated" path and tested in dev evals)
- **Action:** after approval, update V3_DESIGN.md Step 6 and the dev eval plan (Step 3).

### Q44 — Indirect prompt injection (instructions hidden in PDF text)?
- **Answer (2026-11-19):** Accept the risk for now. The 361 PDFs come from company sites, so the sources are trusted. Note: claims + exact quotes checked by code (Stop 6) already limit what injected text can change.
- **Verdict:** superseded by Q47 (defences + 20-document test kept)
- **Action:** after approval, mark it as an accepted risk in V3_DESIGN.md Step 6, with the reason. Mention it in "known limits" in the README.

### Q45 — Investment advice questions ("Should I buy Apple stock?")?
- **Answer (2026-11-19):** Refuse it. The router treats it as an unrelated question. Add such questions to the dev eval set.
- **Verdict:** refined by Q48 (refuse + offer facts)
- **Action:** after approval, record in V3_DESIGN.md Step 6 and the dev eval plan.

### Q46 — Privacy of logged questions?
- **Answer (2026-11-19):** Store the full question and answer text. Keep logs for 30 days, then delete. Risk is low: an SEC filing demo rarely gets personal data (possible cases: a user types their name/email, private holdings, IP address in request logs).
- **Verdict:** changed (adds a 30-day retention rule)
- **Action:** after approval, add the retention rule to V3_DESIGN.md Step 6 and the monitoring part.

### Q47 — Re-check of Q44 against V3_DESIGN.md Step 6, threat 1
- **Answer (2026-11-19):** Option 1. Keep defences (a) document text marked as data only, (b) plan made from the question alone before any document is read, (c) every claim checked against a quote. Keep the 20 planted-document test.
- **Verdict:** kept (overrides Q44: indirect injection is defended and tested, not an accepted risk)
- **Action:** no change to V3_DESIGN.md Step 6, threat 1. Q44 is superseded.

### Q48 — Re-check of Q45 against V3_DESIGN.md Step 6, threat 3
- **Answer (2026-11-19):** Option 2. Refuse the advice, say why, then offer the facts from the filings ("I cannot give advice. Here is what Apple reported…"). The router needs a separate "advice" route, not the plain "unrelated" route.
- **Verdict:** kept (overrides Q45 detail; V3_DESIGN.md threat 3 stays)
- **Action:** add an "advice" route to the router spec. Test advice prompts in the dev eval set.

### Q49 — Can users upload their own PDFs?
- **Answer (2026-11-19):** No uploads. Users ask only about the fixed 361 FinanceBench PDFs.
- **Verdict:** changed (threat 8 shrinks: bad files can only enter at build time, not from users. Remove "HTML is read as text only" because the corpus is PDF only)
- **Action:** after approval, update V3_DESIGN.md Step 6, threat 8: keep size/type limits and "skip + log bad file" in ingestion; keep broken sample files in ingestion tests.

## Area 7 — Production targets (Step 7)

### Q51 — Cost targets vs Sonnet prices
- **Context:** Step 7.2 targets (median < $0.01, p95 < $0.05) were set for Groq prices. Rough estimate with Haiku router + Sonnet planner/writer (not measured): simple ≈ $0.03, complex ≈ $0.08–$0.15.
- **Answer (2026-11-19):** Set the cost targets after the first measurement, with the reason written down (same rule as 7.3 Load).
- **Verdict:** changed (7.2 numbers removed; set after measurement)
- **Action:** after approval, update V3_DESIGN.md 7.2: remove the Groq-era numbers, add "set after first measurement", change "hard cap on the Groq account" to the Anthropic/OpenAI accounts.

### Q52 — Speed targets vs Sonnet latency
- **Context:** Step 7.1 targets (simple < 5 s median, complex < 20 s) assumed Groq speed. Rough estimate with Haiku router + Sonnet (not measured): simple ≈ 7–10 s.
- **Answer (2026-11-19):** Set the speed targets after the first measurement, with the reason written down. Keep the rules: median + p95, progress messages, per-step timing.
- **Verdict:** changed (7.1 numbers removed; set after measurement)
- **Action:** after approval, update V3_DESIGN.md 7.1.

### Q53 — Backup model when Claude is down (7.4)
- **Answer (2026-11-19):** An OpenAI model as backup. Exact model chosen at build time. Order stays: retry → fall back to OpenAI → clear error.
- **Verdict:** kept (7.4 already wanted a second provider; provider now named)
- **Action:** after approval, update V3_DESIGN.md 7.4 (replace "Groq outage" wording). Note: the eval judge is also OpenAI, so answers made by the backup model are judged by the same family. Log which model wrote each answer.

### Q54 — Rate limit design (7.5)
- **Answer (2026-11-19):** Keep the full production setup (per-user token bucket, per-user cost budget, global limit, per-question guards, HTTP 429 + Retry-After, shared store, limits in config, alerts). Numbers are demo-sized and set in the Deployment area (links to Q42, about 5 questions/day).
- **Verdict:** kept (7.5 stays; "20 questions per hour" and "Groq account limits" numbers to be replaced)
- **Action:** after approval, update V3_DESIGN.md 7.5 numbers and provider names.

## Area 8 — Monitoring (Step 7.6)

### Q56 — Monitoring tools
- **Answer (2026-11-19):** Langfuse for AI traces, plus a separate metrics + alerts tool (e.g. Prometheus + Grafana, or a hosted tool). Exact metrics tool chosen at build time. Prefer OpenTelemetry for instrumentation.
- **Verdict:** kept (7.6 four parts stay; tools now named)
- **Action:** after approval, update V3_DESIGN.md 7.6.

### Q57 — Quality monitoring with little real traffic
- **Answer (2026-11-19):** Both: (1) users mark answers 👍/👎 and a sample of real answers is re-checked automatically; (2) a scheduled eval run (e.g. weekly) on the dev eval set catches quality drops. The locked FinanceBench 150 is NOT used for scheduled runs (keeps it locked).
- **Verdict:** changed (adds scheduled dev-eval runs to 7.6)
- **Action:** after approval, update V3_DESIGN.md 7.6. Show the cost of a scheduled run before turning it on.

### Q58 — Where do alerts go?
- **Answer (2026-11-19):** Email to the owner as the first choice. Also explore a dashboard-only option. Decide exactly at build time.
- **Verdict:** open (decided at build time)
- **Action:** after approval, note in V3_DESIGN.md 7.6: "alert destination: email (preferred) or dashboard, chosen at build time".

## Area 9 — API/UI (Step 8.1, 8.2)

### Q60 — How does the system identify one user for per-user limits?
- **Answer (2026-11-19):** Treat V3 as a real product: user login with username + password. Track usage and limits per user. How recruiters get access (accounts, sign-up, demo login) is decided later (Deployment / Showcase).
- **Verdict:** changed (8.1 said "API key"; now user accounts with login. Q40 "link only" access is refined: the link opens a login page)
- **Action:** after approval, update V3_DESIGN.md 7.5 (per user, not per API key), 8.1 API service, and Step 6 (add threats for accounts: password storage, brute-force login). Revisit recruiter access in the Deployment area.

### Q61 — Build login or use an auth provider?
- **Answer (2026-11-19):** Keycloak (open-source, self-hosted identity provider). It handles password hashing, reset, brute-force protection and tokens. The API checks the Keycloak token (OIDC/JWT) on each request and reads the user ID for per-user limits.
- **Verdict:** changed (new component: identity provider)
- **Action:** after approval, add Keycloak to V3_DESIGN.md 8.1 (as part 7 or inside part 3) and to Step 6. Note: self-hosted Keycloak needs its own server + database at deploy time (check in the Deployment area). Candidate for an ADR.

### Q62 — UI tool
- **Answer (2026-11-19):** React (Next.js or plain React chosen at build time). Reason: industry-standard frontend, standard Keycloak/OIDC login libraries.
- **Verdict:** changed (8.2 was "decide at build time"; now React)
- **Action:** after approval, update V3_DESIGN.md 8.2. Note: new language/toolset (TypeScript) adds build time; plan for it in Milestones.

### Q63 — How does the UI show a citation?
- **Answer (2026-11-19):** Show the citation details only: file name, company, period, page number and the quoted text. The UI does not open or render the PDF.
- **Verdict:** changed (8.2 wanted "open the source with the quote highlighted"; the view-a-source endpoint in 8.1 is no longer needed, or returns details only)
- **Action:** after approval, update V3_DESIGN.md 8.1 and 8.2.

### Q64 — Follow-up questions (multi-turn chat)?
- **Answer (2026-11-19):** Yes. V3 is a chat RAG system: single-turn and multi-turn questions, like real-world chat products. The system keeps chat history per user.
- **Verdict:** changed (new ability; V3_DESIGN.md assumed single questions)
- **Action:** after approval, update V3_DESIGN.md Step 4 (abilities), Stop 4 (planning gets history), 8.1 (store conversations per user), Step 3 (dev eval needs multi-turn cases; FinanceBench 150 is single-turn only), Step 6 (chat history is user data: same 30-day rule?).

### Q65 — Where are follow-up questions rewritten into full questions?
- **Answer (2026-11-19):** Decide at build time. Constraint from the user: do not add a new LLM call for every task. Too many LLM steps in one flow hurt speed and add more things to check. Prefer merging jobs into existing calls where possible.
- **Verdict:** open (decided at build time, with the "minimum LLM calls" rule)
- **Action:** after approval, add a design rule to V3_DESIGN.md Step 5: "Count LLM calls per question. Add a new call only when measured need shows it."

### Q66 — Past chats visible to users?
- **Answer (2026-11-19):** Yes. Users see their past chats in a left sidebar, like ChatGPT. Keep chats for 30 days, then delete (same rule as logs, Q46).
- **Verdict:** changed (new UI feature + chat storage per user)
- **Action:** after approval, update V3_DESIGN.md 8.1 (chat storage in the database), 8.2 (sidebar), Step 6 (30-day deletion for chats and logs).

### Q67 — What does the user see while waiting? (streaming vs checked answer)
- **Answer (2026-11-19):** Use SSE (Server-Sent Events). The backend sends progress events ("Searching…", "Fetching chunks…", "Checking quotes…"), then streams the answer. The answer is streamed only AFTER the quote checks pass (sent in parts for a typing effect), so the user never sees an unchecked answer.
- **Verdict:** kept (8.1 "streams progress" stays; mechanism now named: SSE)
- **Action:** after approval, update V3_DESIGN.md 8.1 (SSE events: progress, answer, done, error).

## Area 10 — Tests/CI (Step 8.3)

### Q69 — End-to-end browser tests (UI + Keycloak login + chat)?
- **Answer (2026-11-19):** Decide at build time (e.g. Playwright in CI, or manual UI testing).
- **Verdict:** open (8.3 has no UI/login test layer yet)
- **Action:** after approval, add an "End-to-end UI tests: decided at build time" row to V3_DESIGN.md 8.3.

### Q70 — When does the quality gate run?
- **Answer (2026-11-19):** Build the quality gate component (≈20 practice questions, compare to the last accepted score, fail on a drop beyond a set margin). For now, run it manually, not on every merge or nightly. Reason: it is a portfolio project built like a real one; real-AI runs cost money. Automating it in CI is a switch that can be turned on later.
- **Verdict:** changed (8.3 said "before important merges and nightly"; now manual trigger)
- **Action:** after approval, update V3_DESIGN.md 8.3. State in the README that it can run in CI and why it is manual (cost). Same rule for the weekly scheduled eval (Q57): built, manual for now? Confirm in the Deployment area.

### Q71 — Does the weekly scheduled eval (Q57) follow the same rule?
- **Answer (2026-11-19):** Yes. Build it, run it manually for now. Scheduling can be switched on later.
- **Verdict:** changed (refines Q57)
- **Action:** after approval, update V3_DESIGN.md 7.6 and 8.3. Rule: every real-AI run (quality gate, weekly eval, full eval) is manual and shows its cost before it runs.

## Area 11 — Deployment (Step 4.4, 8.4)

### Q73 — Where are the parts hosted for the live demo?
- **Answer (2026-11-19):** Decide hosting and deployment only after all development work is done. Candidates noted: one VM + Docker Compose; managed cloud (AWS/GCP); cheap platforms (Vercel + Render/Fly.io).
- **Verdict:** kept (4.4 already defers deployment; live demo stays part of the final goal)
- **Action:** no change to V3_DESIGN.md 4.4. Keep the design note: settings from environment variables, no hard-coded paths, one-command start. Open items moved to the deploy stage: Q42 question limit numbers, recruiter access (Q60), Keycloak hosting (Q61), Docker (8.4), alert destination (Q58).

## Area 12 — Milestones (Step 9)

### Q74 — Redraft milestones or grill each one?
- **Answer (2026-11-19):** Redraft the milestones from all logged answers and show a draft for review.
- **Verdict:** changed (Step 9 table out of date: HTML/40 companies, two baselines, hybrid+reranker in M2, no Keycloak/chat/React, quality gate in CI)
- **Action:** draft shown in chat (2026-11-19); waiting for user review. After approval, replace the V3_DESIGN.md Step 9 table.

### Q75 — Approve the milestone draft?
- **Answer (2026-11-19):** Approved for now.
- **Verdict:** changed (new Step 9 table)
- **Draft approved:**
  - M0 Foundations: remove V2 code from v3; layout; env settings; basic CI (lint, types, secret scan, unit); download 361 PDFs + 150 questions, lock the 150; start dev eval drafting (Claude drafts, user confirms); create V3_LEARNING.md.
  - M1 Walking skeleton + baseline: few companies' PDFs; PDF reader chosen by test (no FinanceBench evidence); chunk metadata (company, doc type, fiscal period from cover page); local embeddings; store chosen by test; plain RAG baseline in eval runner. Measured: first dev scorecard.
  - M2 Core engine, simple questions, all 361 PDFs: router (Haiku) with coverage check + routes (unrelated, advice, unclear); semantic search + metadata filters; structured JSON with claims + exact quotes checked by code; API with SSE. Measured: vs baseline, refusal rate, citation pass rate; first speed/cost measurement → set 7.1/7.2 targets; hybrid/reranker only if retrieval failures dominate.
  - M3 Hard questions: planner (plan-first, max one re-plan), calculator tool, multi-turn follow-ups, year comparisons, company comparisons (low priority). Measured: failure causes (hybrid tagging); locked run 1 (3 runs); judge-vs-human agreement (30–50 answers).
  - M4 Users + UI: Keycloak login; chats per user + sidebar + 30-day deletion; React UI (progress, citation details, 👍/👎).
  - M5 Safety + production: safety test set (incl. 20 planted documents); full rate limits; retries + OpenAI fallback; Langfuse + metrics + alerts; quality gate + weekly eval (manual); load test. Measured: safety pass rates; load number.
  - M6 Final test: failure-by-cause analysis. Measured: locked run 2 (3 runs); held-out behaviour subset opened.
  - M7 Deploy + showcase: hosting, Docker, recruiter access, question-limit numbers; README, architecture diagram, demo video.
  - M8 Optional (low priority): MCP server (A4), open dataset (A5), conflict detection if real conflicts exist, P1 revisit.
- **Action:** after approval, replace the V3_DESIGN.md Step 9 table.

## Area 13 — Showcase (Step 10)

### Q76 — Demo video items (old items 2 and 3 no longer fit)
- **Answer (2026-11-19):** No demo video. The live demo (Q17) is the way visitors see it working.
- **Verdict:** changed (Step 10 "2–3 minute demo video" and the six demo items removed; M7 drops the video)
- **Action:** after approval, update V3_DESIGN.md Step 10 (top of README: problem line, headline numbers, live demo link + screenshots if wanted) and M7.

### Q77 — Technical write-up (blog) outside the repo?
- **Answer (2026-11-19):** The README is the main technical write-up. A separate blog post is optional, only if time remains after everything is done.
- **Verdict:** changed (blog moves to optional, M8-level priority)
- **Action:** after approval, update V3_DESIGN.md Step 10 ("Outside the repo" row → optional) and add to M8.

### Q78 — README headline numbers (revisit of Q13)
- **Answer (2026-11-19):** Decide at the end, after results exist: choose the numbers that make real sense and matter most. Q13's three numbers stay as the starting candidates.
- **Verdict:** open (decided at M7)
- **Action:** after approval, note in V3_DESIGN.md Step 10: "headline numbers chosen at M7 from real results".

## Final check (draft, 2026-11-19) — waiting for user review

### Top 5 risks
1. **PDF tables read badly.** Most FinanceBench answers sit in financial tables. A weak PDF reader breaks everything after it. *Defence:* choose the reader by test in M1 (no FinanceBench evidence); failure tagging separates parsing from retrieval.
2. **Scope is large for one person.** React + TypeScript, Keycloak, chat history, full rate limits, a monitoring stack, plus the RAG engine. *Defence:* walking skeleton first; milestone order puts the core engine and locked run 1 before users/UI; M8 is optional.
3. **Dev eval bias.** Claude drafts the dev questions and Claude models answer them. *Defence:* user confirms every dev question; the locked test is human-written FinanceBench; the judge is an OpenAI model; judge-vs-human agreement is reported.
4. **Cost of real-AI runs.** Rough estimate (not measured): 2 locked runs × 3 repeats × 150 questions ≈ 900 questions + judge, about $45–$135, plus dev runs. *Defence:* every real-AI run is manual and shows its cost first; targets set after first measurement.
5. **"Why not long context?" has no measured answer.** Only plain RAG is a baseline; the paper shows long-context ≈ 79% vs vector RAG ≈ 50%. *Defence:* cite the paper numbers honestly; optional small long-context run on a subset if time allows.

Also watch: the 361 PDFs are hosted on company sites (links can break) and FinanceBench is CC-BY-NC-4.0 (credit it, no commercial use). Download once in M0 and keep checksums.

### Interview pitch (draft)
"V3 is a chat assistant that answers equity-analyst questions from 361 real SEC filings. Every number in an answer comes with an exact quote that code checks, and every calculation is done by code, not the model. I measured it on FinanceBench, a human-written benchmark where plain vector RAG scores about 50%, against my own plain-RAG baseline, and I report failures by cause. It runs like a real product: login, per-user rate limits, fallback to a second AI provider, traces, metrics and alerts."

### Q80 — Approve top risks and pitch?
- **Answer (2026-11-19):** Risks and defences approved for now. The pitch stays a draft; refine it later.
- **Verdict:** kept (risks); open (pitch)
- **Action:** next step: specs in docs/v3/, GLOSSARY.md, ADRs, then proposed V3_DESIGN.md changes.

### Q81 — Approve the spec / ADR / glossary file list?
- **Answer (2026-11-19):** Yes. Also agreed the V3 build workflow: approval per component (explain what, why, key decisions, step plan → approve → code + unit tests). Free runs I may run myself; any LLM/paid run needs approval and a cost estimate first.
- **Verdict:** kept
- **Action (done 2026-11-19):** wrote `docs/v3/` (ingestion, router, engine, api, ui, evaluation, safety, observability, testing-ci, deployment), `docs/adr/0001–0007`, `GLOSSARY.md`. Next: propose V3_DESIGN.md changes for approval.

### Q83 — How to update V3_DESIGN.md?
- **Answer (2026-11-19):** Option B: rewrite it as an overview that links to the specs and ADRs. Keep it updated with the latest details.
- **Verdict:** changed
- **Action (done 2026-11-19):** V3_DESIGN.md rewritten (12 sections). Old version in git history (commit 3248756). All "after approval, update V3_DESIGN.md" actions in this log are now covered by the overview + specs.

### Correction (2026-11-19, M0) — corpus count
- **Finding:** the document list has 361 rows, but one name (`FOOTLOCKER_2023_annualreport`) appears twice with two periods. Unique PDFs = **360** (269 10-K, 30 8-K, 27 10-Q, 29 earnings, 5 annual reports). The repo also holds 8 PDFs not in the list; they are not in the corpus.
- **Action (done):** "361" changed to "360" in the specs, ADRs, glossary and V3_DESIGN.md. Pitch now says "360 real company filings", because some documents are earnings reports, not SEC filings. Older entries above keep the original number.
