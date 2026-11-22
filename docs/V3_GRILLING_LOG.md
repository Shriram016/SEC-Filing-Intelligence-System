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

### Q85 (M1a, 2026-11-19) — Which PDF readers to test?
- **Options shown:** pdfplumber, PyMuPDF (AGPL), Docling, Unstructured, Marker (GPL), cloud services (paid).
- **Answer:** Start with pdfplumber only. If it breaks, move to another reader.
- **Rule added:** pdfplumber fails if < 95% of checked table cells are correct (value, row, unit). Next candidate: Docling.
- **Verdict:** changed (spec said "comparison by test"). Flagged as a portfolio shortcut.

### Q86 (M1a, 2026-11-19) — Which vector store?
- **Options shown:** pgvector, Qdrant, ChromaDB.
- **Answer:** pgvector not needed. Use Qdrant.
- **Side effect:** chats, logs and eval results need a second database (PostgreSQL or SQLite), decided at the API milestone.
- **Verdict:** changed (spec said "chosen by test").
- **Also agreed:** the chunk method does not matter for the M1a tests; it is decided in M1b.

### Q87 (M1a, 2026-11-19) — Which embedding models to test?
- **Options shown:** bge-small, bge-base, bge-m3, nomic-embed v1.5, Qwen3-Embedding-0.6B, gte-modernbert-base; dropped jina-v3 (non-commercial licence) and paid APIs (OpenAI, Voyage).
- **Answer:** No paid models. Try the free ones.
- **Test set:** bge-base-en-v1.5 (baseline), bge-m3 (long input + sparse vectors for hybrid), Qwen3-Embedding-0.6B (strongest quality candidate).
- **Verdict:** confirmed (free local model, Q38).

### Q88 (M1a, 2026-11-19) — How do we store tables?
- **Finding:** pdfplumber reads all values (100%), but its table finder breaks columns. Word positions keep the columns (96%). See `experiments/m1a/RESULTS_reader.md`.
- **Options shown:** layout text; own table builder from word positions; Docling; cloud service (paid).
- **Answer:** layout text (option 1).
- **Check added:** dev questions tagged `answer_source` = table / text; compare scores. Clearly lower table score → test Docling on the same 77 cells.
- **Verdict:** new. Portfolio shortcut flagged (production usually stores structured tables).

### Q89 (M1a, 2026-11-19) — Which embedding model?
- **Finding:** Hit@5 bge-base 55%, bge-m3 55–57.5%, Qwen3-0.6B 52.5–55% on 40 frozen questions → tie. bge-base is ~3× faster than bge-m3 and ~14× faster than Qwen3. See `experiments/m1a/RESULTS_embed.md`.
- **Options shown:** bge-base-en-v1.5; bge-m3 (recommended for 8k input + sparse vectors); Qwen3-Embedding-0.6B.
- **Answer:** bge-base-en-v1.5. The 512-token limit is not an issue with small chunks (6% cut in the test).
- **Rule added:** M1b chunks stay below 512 tokens; log any chunk that is cut. Hybrid search, if needed, uses a separate BM25 index.
- **Verdict:** new.

### Q90 (M1b prep, 2026-11-20) — One section logic per company, or one general logic?
- **Finding:** 360 PDFs, 40 companies; 93% are SEC filings printed from HTML. 10-K Items are fixed by law, but simple rules find all key Items in only 196/269 10-Ks. Causes: format (no space after the dot, dashes, non-breaking spaces), content in Exhibit 13 (CVS, older Verizon), own layout (Intel 2017+, MGM 2015–18). Templates change between years for the same company; only 9/40 companies use the same PDF tool every year. Script: `experiments/structure/check_10k_items.py`.
- **Options shown:** one rule set per company; one general logic per document with a fallback to page headings.
- **Answer:** one general logic per document (production standard). Company rules only after a measured failure.
- **Also agreed:** use the document list (not the file name) for company, type and year; period dates from the cover page.
- **Other types (checked after):** 10-Q Items 1–4 found 24/27; 8-K item codes 28/28 (large 8-Ks are mostly exhibits); earnings have no legal structure but a common pattern; all 5 annual reports contain a full 10-K. The same general logic covers all types. See ingestion.md §10.
- **Verdict:** new.

### Q91 (M1b, 2026-11-20) — Which documents does M1b use?
- **Options shown:** ~20 documents chosen to cover all templates; all 360; ~5 easy 10-Ks.
- **Answer:** ~20 documents that cover all 5 types and the difficult layouts (own layout, Exhibit 13, annual report, large 8-K, landscape earnings, 10-Q). Only documents no locked question uses (same guard as M1a). M1b finalises the logic; M2 runs it unchanged on all 360 and logs weak documents.
- **Verdict:** new.

### Q92 (M1b, 2026-11-20) — How does Qdrant run?
- **Options shown:** Qdrant server in Docker; Qdrant local mode (in-process, folder on disk; portfolio shortcut).
- **Answer:** Qdrant server in Docker (`docker-compose.yml`, `localhost:6333`). Production standard; dashboard; snapshots; API and ingestion can use it at the same time.
- **Verdict:** new.

### Q93 (M1b, 2026-11-20) — Chunk method and size?
- **Shown:** chunk types (fixed, recursive, structure-aware, semantic, parent-child, LLM context, page). Production norm: structure-aware + recursive inside long sections, 256–1,024 tokens, tables separate.
- **Answer:** structure-aware split (Items / item codes / page headings; never across a section), recursive split (paragraph → sentence) inside long sections; join short parts of the same section. Target ~350 tokens, max 480 (bge-base limit 512 incl. the header). Overlap ~50 tokens when a section is split; none across headings. Header on each chunk: "Company type FY › section › subsection".
- **Later, only on measured need:** parent-child; other sizes (200 / 480) tested on the dev set in M1d.
- **Verdict:** new.

### Q94 (M1b, 2026-11-20) — Table chunks?
- **Options shown:** one table = one chunk, large tables split into row groups; tables as normal text; one chunk per table, never split.
- **Answer:** one table = one chunk with title, unit line and column headers. If > 480 tokens: split into row groups; each group repeats title + headers. Every part carries `table_id` so the answer step can fetch the full table. A table continued on the next page is joined first. Small tables stay as their own chunk.
- **Verdict:** new.

### Q95 (M1b, 2026-11-20) — Who writes table labels? (closes Q23)
- **Options shown:** code template; LLM label (one call per table, cost); code template now, LLM later only on measured need.
- **Answer:** code template now (company, type, year, section, table title, unit, row names, column headers). LLM labels only if table questions score clearly lower on the dev set; cost estimate and approval first.
- **Verdict:** new (closes Q23).

### Q96 (M1b, 2026-11-20) — Period dates?
- **Asked:** can the year in the file name be used directly as a filter?
- **Finding:** not alone. Fiscal ≠ calendar year (Walmart FY2023 ends 2023-01-31); a 10-K holds 2–3 years of numbers (single-10-K companies: Amex, FedEx, PayPal); name year can be wrong (`SALESFORCE_2021_8K_dated-2023-01-04`, `FOOTLOCKER_2022_8K_dated_2023-02-21`) or missing (McDonald's 8-Ks).
- **Answer:** (1) `fiscal_year` from the document list `doc_period`; (2) exact `period_end` / `report_date` from cover-page patterns per type (earnings: fallback to list year + name quarter, `period_source = estimated`); (3) log list/cover mismatches; (4) store `fiscal_year`, `fiscal_quarter`, `period_end`, `report_date`, `period_source` on every chunk. Search uses the year as a **boost, not a hard filter**. Free (no LLM).
- **Verdict:** new (refines Q25).

### Q97 (M1b, 2026-11-20) — Document list year vs year in the document?
- **Finding:** `ULTABEAUTY_2024Q1_EARNINGS` says "First Quarter Fiscal 2023, ended April 29, 2023"; the document list says 2024. Other list errors found: `LOCKHEEDMARTIN_2023Q2_10Q` is an earnings release; `PG_E_2023_EARNINGS-dated-2023-06-01` is an 8-K with debt exhibits.
- **Options shown:** A. year stated in the document; B. document list year.
- **Answer:** A. `fiscal_year` = the year stated in the document when found (e.g. "Fiscal 2023"), else the list year; `list_fiscal_year` keeps the list value; the difference is logged. A 10-K cover gives only the end date, so its year stays the list year (some retailers name the fiscal year by its start).
- **Verdict:** new (refines Q96).

### Q98 (M1b, 2026-11-20) — Why not LangChain or LlamaIndex?
- **Finding:** not decided before; ingestion was built on direct libraries (pdfplumber, sentence-transformers, qdrant-client). Most of the code is SEC-specific (Items, tables, periods, data checks) and no framework has it.
- **Options shown:** direct libraries (recommended); a framework for the simple parts (load, embed, store).
- **Answer:** direct libraries; document the reasons and where the custom code gives an advantage. Look again at the answer/agent milestone.
- **Record:** ADR-0008 (`docs/adr/0008-no-rag-framework.md`).
- **Verdict:** new.

### Q99 (M1b, 2026-11-20) — How deep should the embedded label be?
- **Finding:** label hand-check, 2 rounds × 50 random chunks: company/type/year 100/100, section 94/100, subsection 85/100, minor heading 85/100, full path 66% → 72%. Each fix round found new rare cases (long tail). The section is found by fixed SEC patterns; subsection and heading only by font style, which differs per company.
- **Asked:** is it worth this effort to get the label right?
- **Options shown:** A. keep fixing round by round; B. fix the general causes, take the minor heading out; C. accept the labels as they are. Then: stop tuning, embed only the reliable part, measure.
- **Answer:** embed company, type, period + section only. Subsection, heading and table title are stored fields, not embedded (`context` keeps the full path). Fix the open section causes (cheap). Setting `label_depth` (`none` / `section` / `full`); M1d compares the three on the dev set; the deep levels come back only if `full` clearly wins.
- **Section fixes done:** Item check runs before the heading word limit (long titles: 10-K Item 5 in 6 documents, Costco Item 7, 8-K Item 5.02, Amcor Item 2.03, Apple 10-Q Item 2); brackets removed before the title word count, limit 24; exhibit heading with a footnote number ("Exhibit 10.5(40)", MGM); an Item followed by lower-case prose is not a heading. Known left: a wrapped sentence line "Exhibit 95 to this annual report." (3M, 1 chunk).
- **Verdict:** new (refines Q93, Q95).

### Q100 (M1c, 2026-11-20) — Search filters and how to fix eval errors
- **Asked:** high-level plan check (subset → ingest → metadata filter + vector search → LLM answer → dev set → fix → all 360 → test).
- **Answer:** (1) the **company is a hard filter**; year, period, doc type and section are optional (boost only). (2) Fixing dev-set errors fixes the **cause** (search, PDF reading, answer step) for a group of questions, never a single question. The final score comes from the locked set.
- **Record:** `engine.md` §search, `evaluation.md` §5.
- **Verdict:** confirms Q24, Q25, Q96; new rule for fixes.

### Q101 (M1d, 2026-11-21) — Drop the label-depth test?
- **Finding:** search test on `chunks` (label `section`): Hit@5 0.48. Doc-filter oracle Hit@5 0.70. Main causes: wrong year or duplicate document of the same company (61% of top-5 chunks), and table pages ranked low. Not the label.
- **Asked:** why are we still experimenting with the label?
- **Answer:** drop the `none` / `full` comparison planned in Q99. `section` is final. Look at the label again only if data points to it (tables still weak after the year boost and keyword search).
- **Also decided:** stop search experiments until the baseline gives a first answer score (walking skeleton first). The year boost comes with the router in M2.
- **Verdict:** changes Q99 (test dropped).

### Q102 (M1, 2026-11-21) — Baseline output format
- **Asked by the user:** the LLM call always returns structured JSON, never free text.
- **Answer:** the baseline returns JSON (`found`, `answer`, `value`, `unit`, `sources`), enforced by the API (`output_config.format`) and checked by code; one retry, then a clear error (Q32). Top 5 chunks, no company filter, Claude Sonnet 5.5 with thinking off (`between_tools`; `disabled` is rejected on this model). Paid runs only with `--allow-paid`; dry run prints tokens + cost; $2 cost limit per run.
- **Flag:** a classic plain-RAG baseline answers in free text; the README says ours uses JSON.
- **Verdict:** new (applies Q31 to the baseline).

### Q103 (M1, 2026-11-21) — What is stored as ground truth, and what is checked?
- **Finding:** the gold number was stored only inside the `gold_answer` text, so the scorer had to parse it.
- **Answer:** add `gold_value` + `gold_unit` to answerable dev questions (35 of 50 filled; the 15 without are explain-why and choice answers, marked by hand). Checks: number (code), text (hand), evidence page in the chunks (code), the model cited the evidence page (code). Failure tags: `search_miss`, `answer_error`, `broken_json`.
- **Verdict:** new (refines Q10, Q11).

### Q104 (M2, 2026-11-21) — Router schema and search filters
- **Finding:** baseline: 13 of 19 wrong answers were search misses; 61% of top-5 chunks came from other documents of the same company (mostly the wrong year). The time fields on a chunk (`fiscal_year`, `period_end`, …) belong to the **document**, not to the chunk's content.
- **Asked by the user:** if the router extracts the year and the doc type correctly, why not hard filters? That is the purpose of the structured router output.
- **Issue shown:** the year in the question is the year of the fact; `fiscal_year` is the year of the document. The FY2023 10-K also holds 2022; not every year exists for every company. An exact year filter would miss these.
- **Answer:**
  1. Router JSON: `route`, `standalone_question`, `reason`, `companies` (enum of the 40 names), `other_companies` (names not in the collection → `not_covered`), `years`, `doc_type`, `metric`. All fields always present; empty = `[]` / `null`. The LLM gives `answer` / `unrelated` / `advice` / `unclear`; code sets `not_covered`.
  2. The LLM gives only the years the question names. **Code** chooses the documents from a catalog: year Y, else Y+1 (option A; option B "always Y and Y+1" measured as the alternative); never Y−1. `doc_type` only when the question names it.
  3. All of these are **hard filters**, applied as one `doc_name` filter. Coverage: company has a document for Y or Y+1.
  4. Follow-up rewrite folded into the router call (`standalone_question`); history length at M3.
- **Known limit:** years only in an old 5-year table are not reached; twin documents of the same year are both searched.
- **Record:** `router.md` §2, `engine.md` §3.2.
- **Verdict:** changes Q100 (year and doc type: boost → hard filter via document list).
- **Measured (2026-11-21):** free "perfect router" test: Hit@5 0.48 (no filter) / 0.48 (company only) / **0.62 (rule A)** / 0.62 (rule B, lower Hit@1) / 0.70 (gold document). Rule A kept (rule set before the run: B needed +3 questions). Smoke test (paid, $0.0153): router JSON correct 2/2, answers 1/2 (the miss: right page, the needed table chunk ranked low). Results: `experiments/m2/RESULTS_router_search.md`, `experiments/m2/RESULTS_smoke.md`.

### Q105 (M2, 2026-11-22) — Table title in the embedded text; split tables
- **Finding:** inside the gold document, table pages Hit@5 0.61 vs text 0.82. Smoke test dev_0032: right page, but the "KEY FINANCIAL METRICS - CONSOLIDATED" table chunk ranked low. Code check: the table title was in the answer text, but not in the embedded text (`label_depth=section` dropped it, Q99). Split tables caused 3 baseline errors (the needed rows in another part).
- **Asked by the user:** why is something in the LLM text that is not in the embedded text? The embedded text should be the label + the chunk text.
- **Answer:**
  1. Rule: **embedded text = label + everything in the answer text.** The table title is part of the table, so it is always embedded. Subsection and minor heading stay out (Q99/Q101 unchanged for them).
  2. Apply by a normal re-ingestion (38 min, free) into a new collection `chunks_v2` with its own ingest folder; the old `chunks` stays for rollback. Small test first: the dev-set documents in a test collection, compared with `chunks` inside the gold document (page Hit@k and a new "gold number in the top-k chunks" check). Go only if tables improve and text does not drop.
  3. Split tables: code adds the other parts of a retrieved table (same `table_id`, nearest first, max 3 extra chunks per question).
- **Record:** `ingestion.md` (Embedded label), `engine.md` §3.2.
- **Verdict:** changes Q99 (table title embedded); new (split-table expansion).
- **Measured (2026-11-22, free):** small test (21 dev documents, gold document): table Hit@5 0.607 → 0.607, Hit@10 0.643 → 0.714; text unchanged (text chunks identical). **No gain at Hit@5 → `chunks_v2` not built** (rule set before the run). The split-table expansion does not fix the 3 baseline "split table" errors: those are one table cut into separate tables by the PDF reader, not row groups. Results: `experiments/m2/RESULTS_table_titles.md`. Decision on the next step: open.

### Q106 (M2, 2026-11-22) — PDF reader: tables cut in two, lost table titles
- **Finding (Q105 hand check + free count on `chunks`):** 9,780 of 29,808 tables (33%, in 344 of 359 documents) have no title. The reader ends a table at the first line without numbers, so a long row name with no numbers (Apple 10-Q p5 "Change in unrealized gains/losses…") cuts one table into two, and the row name becomes the title of the second table. The join rule only joins tables across pages. The title is looked for only in the block just above the table (J&J "Supplementary Sales Data" was lost). 7,589 pages have 2+ tables (upper limit for cuts).
- **Answer:**
  1. Same-page join with strict rules (gap 1–2 lines, no numbers, no full stop, not a heading, columns line up, same unit); the gap lines become a row.
  2. Lost titles: look higher; exact rule after a hand check of about 30 untitled tables. Never a section heading.
  3. Strict over loose; unit tests check that different tables stay separate.
  4. Measure: a free count script (untitled tables, probable cuts) before and after on the 21 dev documents + 20 random documents; hand check of 20 changed tables (locked evidence pages skipped). Small test collection `chunks_t106` (folder `data/v3_t106`), compared inside the gold document. **Go only if table Hit@5 goes up from 0.607 and text Hit@5 does not drop** → then full re-ingest into `chunks_v2` (also brings in Q105), keep `chunks` for rollback.
- **Record:** `ingestion.md` §4 (Table cuts and titles).
- **Verdict:** new (refines Q94, Q105).
- **Measured (2026-11-22, free):** cuts 103 → 24 and untitled 972 → 893 (41 documents); most untitled tables were harmless (13/30 not financial tables, 6/30 title text already in the chunk). Hand check of 20 changed tables: 14 better, 0 wrong joins. Small test (gold document): table Hit@5 0.607 → **0.714**, Hit@10 0.643 → 0.821, Value@5 0.60 → 0.80; text unchanged → go. Full `chunks_v2` (rule A): all Hit@5 0.62 → 0.64, Hit@10 0.70 → 0.78, table Hit@5 0.571 → 0.607, Value@5 0.50 → 0.65; text unchanged → **switched to `chunks_v2`** (also brings in Q105). `chunks` kept for rollback. Results: `experiments/m2/RESULTS_table_reader.md`.
- **Smoke test (2026-11-22, paid $0.0150, approved):** `chunks_v2`, dev_0005 (cut table) and dev_0009 (lost title): 2/2 correct, page seen and cited. `experiments/m2/RESULTS_smoke_q106.md`.

### Q107 (M2, 2026-11-22) — Checked answers: claims, quote check, calculator, final rule
- **Finding:** the routed pipeline uses the baseline answer (one sentence, one value, cited pages). Nothing checks that a page says what is claimed (ADR-0003 not built).
- **Answer:**
  1. One Sonnet call returns claims (label, extract number, exact quote, value as printed, unit, period), calculations (op + input IDs), `main`, and a sentence with placeholders only.
  2. Code checks each quote in its extract (whitespace, case, quote marks and dashes forgiven; 3+ words) and each value in its quote (number matcher shared with the search test, `filing_rag/numbers.py`). Failed claims removed; no retry.
  3. **Calculator moved from M3 to M2:** add, subtract, divide, ratio_pct, pct_change; scale conversion; different families refused. Without it, 16/50 dev questions (calculate, compare) could never pass. The planner stays in M3.
  4. Final rule: answer / partial / refuse; no number reaches the user unless checked or calculated; the period line comes from chunk metadata.
  5. The baseline keeps its old format (frozen comparison). The checked answer also gives the old fields (value, unit, sources), so the scorer is unchanged.
- **Record:** `engine.md` §3.3–3.6.
- **Verdict:** changes the milestone of the calculator (M3 → M2); details the schema (Q30, Q31).
- **Smoke (2026-11-22, $0.0206):** dev_0005 and dev_0038 both correct, claims 3/3 passed, calculator used on dev_0038. Code replaced the model's sentence on dev_0038 (reason not logged) → rows now save `model_sentence` + `sentence_used`; negative inputs shown in parentheses. `experiments/m2/RESULTS_smoke_q107.md`.
