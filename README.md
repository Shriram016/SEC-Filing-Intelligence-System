# SEC Filing Intelligence System

A RAG system that answers natural language questions over real SEC 10-K filings. Every answer comes with the source passages it was built from, a confidence score, and an on-demand view of how a company's disclosures changed between years. Embedding, reranking and the vector index run locally on a 16GB machine with no GPU; language-model calls go to the Groq API.

**Status:** V2, documented as a baseline. Measured results and known failures are listed honestly below; some parts (the conflict detector, the confidence score) are not yet validated.

---

## What This Project Does

- **Answers questions** from four sections of 25 filings (5 companies, 2020–2024), showing the source passages with company, year and section
- **Scores confidence** from retrieval similarity and an LLM faithfulness check (weights are untuned; see Known Failures)
- **Shows year-to-year changes** on demand: pick a company, a section and a year range, and an LLM compares each pair of years (not yet evaluated)
- **Evaluates itself** on 32 queries with ground truths checked against the filing text; the metrics depend on the question type, including a yes/no check for questions the data cannot answer

---

## Dataset

| Dimension | Detail |
|---|---|
| Companies | Apple, Microsoft, Amazon, Google, Meta |
| Tickers | AAPL, MSFT, AMZN, GOOGL, META |
| Years | 2020, 2021, 2022, 2023, 2024 |
| Total Filings | 25 10-K filings from SEC EDGAR |
| Total Chunks Indexed | 2,835 |
| Source | Publicly available via EDGAR full-text search |

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────┐
│  Query Parser   │  LLM validates query + extracts filters + sub-query template
│                 │  Groq (qwen3.8-27b, temperature=0)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Retrieval      │  Cartesian product of filter combinations
│  Engine         │  One ChromaDB query per combination (top-k each)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Reranker       │  Cross-encoder (BAAI/bge-reranker-base)
│                 │  Per-combo reranking with focused sub-queries
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Answer         │  Chunks grouped by sub-query in context window
│  Synthesis      │  Groq (qwen3.8-27b) generates grounded answer
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Confidence     │  Retrieval similarity (ChromaDB cosine)
│  Scorer         │  + LLM faithfulness judge (1–5 rubric, normalised)
└────────┬────────┘
         │
         ▼
    Final Output
    Answer + Source Citations + Confidence Score
```

**Conflict Detection runs as a separate on-demand pipeline:**

```
User selects company + section + year range
    │
    ▼
Read full section text for each year from _sections.json
    │
    ▼
For every year pair: LLM (qwen3.8-27b) reads both years side by side
(each year's text cut to 3,500 words) → lists changes with a severity
    │
    ▼
Conflict Report (topic, year A claim, year B claim, severity)
```

> **Models:** Groq retired the models this project was first built on (Llama-4-Scout and Llama-3.3-70B), so all language-model steps now use `qwen/qwen3.8-27b`, and the evaluation judge is `openai/gpt-oss-120b`. The conflict detector was not re-validated after the model change. Model names and prices live in `config.py`.

---

## Scope: Which Sections Are Indexed

A 10-K filing has 15+ sections. This system focuses on **4 high-signal sections** only:

| Section | Name | Why included |
|---|---|---|
| Item 1 | Business | Explains what the company does — answers "what/how" questions |
| Item 1A | Risk Factors | Richest section for cross-year conflict detection — companies quietly add/drop risks |
| Item 7 | MD&A | Management's narrative on financials — most analyst-relevant section |
| Item 7A | Market Risk | Quantitative exposure data — comparable across years |

**Why not the other sections?**
- Item 8 (Financial Statements) — almost entirely tables. Flattening iXBRL HTML tables destroys row-column relationships, making retrieval unreliable for numerical data. Requires a text-to-SQL or row-to-sentence conversion approach — not done in V2. Questions whose answers are only in the financial tables (for example a balance-sheet line) are therefore declined.
- Items 2–6 — Properties, Legal, Mine Safety — mostly boilerplate, low signal. Questions answered only there (for example office space) are declined too.
- Items 9–15 — procedural disclosures (auditor, governance, compensation) — not relevant to financial analysis questions.

---

## Key Components

### 1. Ingestion Pipeline
Downloads 10-K HTM files from SEC EDGAR using the EDGAR Submissions API (`primaryDocument` field). BeautifulSoup + lxml strips the iXBRL HTML to clean text, preserving newlines for section detection. A regex-based section detector finds Item boundaries and extracts only the 4 target sections. A sentence-aware chunker splits each section into ~300-word chunks with 50-word overlap. A metadata tagger stamps every chunk with `{company, year, section, section_name, filing_type, source_file, chunk_id}`.

### 2. Embedding + Indexing
BAAI/bge-base-en (768 dimensions, CPU, ~550MB) embeds every chunk with `normalize_embeddings=True`. ChromaDB stores vectors and all metadata fields. Upsert-based — safe to re-run. **2,835 chunks** total across 25 filings.

### 3. Retrieval Engine
Takes a raw natural language query and returns the most relevant chunks from ChromaDB. No filter dropdowns — the query is parsed automatically.

**Query understanding (Groq `qwen3.8-27b`, temperature=0):** A single LLM call validates whether the query is answerable from SEC 10-K filings, extracts all mentioned companies/years/sections as lists, and generates a sub-query template for multi-hop queries (e.g., `"<company> AI risk disclosures in <year>"`). Handles paraphrases naturally (`"fiscal 2023"` → 2023, `"risk factors"` → Item 1A).

**Cartesian product retrieval:** If multiple companies or years are detected, the retriever generates every combination (e.g. AAPL×2022, MSFT×2022) and runs one ChromaDB query per combination — top-k each. This guarantees balanced representation for comparison queries rather than letting one company dominate by similarity score alone.

**BGE asymmetric retrieval:** The query is embedded with an instruction prefix (`"Represent this sentence for searching relevant passages: "`) at query time only — not at indexing time. This is how the model was trained: query vectors and document vectors live in different regions of embedding space by design.

**Cross-encoder reranking:** After ChromaDB retrieval, a cross-encoder (BAAI/bge-reranker-base) reranks each combination's chunks using focused sub-queries. For a query like "Compare Apple and Microsoft's risks in 2023," each combo's chunks are reranked with a filled sub-query ("Apple risks in 2023", "Microsoft risks in 2023") instead of the original comparison query. This prevents the reranker from scoring chunks near zero when no single chunk discusses "comparison" or "evolution."

**Known weak points:** the parser asks for JSON in the prompt text only; there is no enforced schema, and if the reply cannot be parsed the retriever falls back to "no filters". A question that names no company or year runs one semantic search over all chunks, so the top results can be dominated by one or two companies (a general "what do companies say about AI" question retrieved Google, Microsoft and one Meta chunk, and nothing from Apple or Amazon).

### 4. Answer Synthesis
Retrieved chunks are assembled into a context window. For multi-hop queries, chunks are grouped by sub-query with headers (`=== Apple risks in 2022 ===`) so the LLM clearly sees which facts belong to which company/year. Groq `qwen3.8-27b` generates an answer grounded strictly to the provided passages — the system prompt explicitly instructs comparison across passages for multi-hop queries, and refusal when the context is insufficient.

Answers are free-form prose. By default (`ANSWER_STYLE = "concise"` in `config.py`) the prompt asks for 1–3 sentences for facts and up to 8 bullets for comparisons; the original unconstrained style (`"free"`) is still available. In the original style comparison answers ran 400–700 words and several were cut off at the `max_tokens=1024` cap. The context is capped at 30 chunks, and that cap can drop a whole company or year (see Known Failures).

### 5. Source Citations
The synthesizer returns the full list of source chunks used as context (`result["sources"]`), including chunk ID, company, year, section, similarity score, and text. No separate citation extraction component is needed — the synthesizer already surfaces this. The UI renders each source in an expandable panel.

Source-level citation (which chunks were used) rather than claim-level (which sentence came from which chunk) — claim-level requires an extra LLM call per query and is unreliable for multi-point comparative answers. The answer text itself may or may not mention passage numbers; the concise prompt asks it not to.

### 6. Confidence Scorer
Combines two signals into a single weighted confidence score:

```
confidence = 0.4 × avg_retrieval_similarity + 0.6 × faithfulness_score
```

- **Retrieval similarity** — mean cosine similarity between the query vector and the retrieved chunk vectors (from ChromaDB distances)
- **Faithfulness** — Groq `qwen3.8-27b` judges whether the answer stays within the retrieved passages on a 1–5 rubric, normalised to 0–1: `(raw - 1) / 4`

Faithfulness is weighted higher (0.6) because a high similarity score alone does not guarantee the LLM stayed within the context.

Special case: if the synthesizer emits the standard refusal sentence, faithfulness is set to 1.0 without an LLM call. In practice this gives refusals a confidence of about 0.91–0.94, as high as good answers (a known issue). The 0.4 / 0.6 weights were chosen by judgment and never tuned or checked against answer correctness.

### 7. Conflict Detector

A question-and-answer system only answers what the user thinks to ask. The conflict detector is a different entry point: it compares a company's disclosures across years so that changes can be spotted without knowing what to ask. A 2020 filing may say *"significant concentration risk from single-source suppliers"* while a later one says *"risk is actively managed"*; that shift is the kind of change it tries to surface.

**How it runs:** on demand, in the Streamlit tab. The user picks one company, one section and a year range. For every pair of years in the range, one LLM call reads both years' section text side by side and returns up to 3 structured changes (topic, each year's claim, a description, and a severity of high, medium, low or none). A 65-second pause between calls stays inside Groq's rate limit.

**It is a tool, not a finished evaluation:**
- **Never run at scale.** The earlier README claim of "200 comparisons" is the number of *possible* pairs (5 companies × 4 sections × 10 year pairs). Nobody has run them all, and the UI runs one company and one section at a time.
- **It reads only part of each section.** Text is cut to the first 3,500 words per year to fit the rate limit. That is shorter than most of the sections: all 25 Item 1A sections (median 10,196 words), 21 of 25 Item 7 and 14 of 25 Item 1. A risk reported as "removed" may simply sit past the cut-off.
- **Not evaluated.** There is no ground truth for what changed, so nothing measures whether flagged changes are real or whether real changes are missed. Its model was replaced after Groq retired the original one (now `qwen3.8-27b`) and has not been re-validated.

An embedding-similarity pre-filter was considered and rejected: mean-pooled vectors are too coarse to tell whether claims actually conflict, and at this scale the LLM cost is small.

### 8. Evaluation Pipeline

**32 queries in 6 categories**, each with a ground truth written from the filing text and checked against it. The audit caught real errors; for example two ground truths wrongly said Microsoft's 2022 filing had no AI risk discussion, when it already did.

| Category | n | What it tests |
|---|---|---|
| Single fact | 6 | One fact or topic from one filing |
| Cross-year | 8 | Change over time for one company |
| Cross-company | 4 | Comparison between companies in one year |
| Vague | 3 | Broad question, no ground truth |
| Should refuse | 8 | In the domain, but the indexed data cannot answer it (a year not in the data, an unindexed section, a company not covered, an opinion) |
| Invalid | 3 | Not about SEC filings |

**Which metrics apply depends on the question type** (full definitions and caveats: [`docs/EVAL_METRICS_GUIDE.md`](docs/EVAL_METRICS_GUIDE.md)):

| Category | Faithfulness | Relevance | Precision | Recall | Ground-truth coverage |
|---|---|---|---|---|---|
| Single fact | yes | yes | yes | yes | yes |
| Cross-year, cross-company | yes | yes | no | yes | yes |
| Vague | yes | yes | no | no | no |
| Should refuse, invalid | a yes/no check: did the system decline? | | | | |

RAGAS scores a good answer built from retrieved text, so a correct refusal has nothing to score; those categories get a pass/fail check instead. **Ground-truth coverage** is the share of ground-truth facts the answer supports. It uses RAGAS's own claim checking but replaces its recall formula, which returned 0.0 on correct answers. The judge (`gpt-oss-120b`, a different model family from the answering model) sees the same numbered passages the answering model saw.

**Latest results** (run `full2_20261014`, a single run; per-query tables in [`evaluation/EVAL_RESULTS_LATEST.md`](evaluation/EVAL_RESULTS_LATEST.md)):

| Category | Faithfulness | Relevance | Precision | Recall | GT coverage |
|---|---|---|---|---|---|
| Single fact (6) | 1.00 | 0.94 | 0.95 | 1.00 | 0.86 |
| Cross-year (8) | 0.93 | 0.93 | – | 0.94 | 0.72 |
| Cross-company (4) | 0.95 | 0.88 | – | 0.83 | 0.47 |
| Vague (3) | 0.78 | 0.91 | – | – | – |

Yes/no checks: all 3 invalid queries were rejected, and all 8 should-refuse queries were declined (4 rejected by the query parser, 4 refused by the answering step).

**How to read these numbers**
- **One run, noisy judge.** Scores move between scoring passes on identical input (one question's context recall went from 1.0 to 0.5 with the same retrieved passages and the same ground truth). The run-to-run spread has not been measured yet, so differences of a few points mean little.
- **Not comparable with earlier published numbers.** The earlier headline of faithfulness 0.97 and precision 0.94 was the single-fact category only, measured with models Groq has since retired, with ground-truth errors, and with a judge that could not see passage numbers. Those figures are retired.
- **Weak spots.** Cross-company coverage is low (0.47). Shorter answers (the concise prompt) cut length by about half but did not raise scores overall; some questions lost facts. The vague-question faithfulness (0.78) comes from answers that generalise to "all companies" from uneven evidence. The confidence score does not separate good answers from refusals.
- **The judge is lightly validated.** It has been checked by hand on only a few answers. It missed one wrong direction word ("decreased" from 139 to 208) in an answer it scored as fully faithful.

---

## Tech Stack

| Layer | Tool |
|---|---|
| HTML Parsing | BeautifulSoup + lxml |
| Embeddings | BAAI/bge-base-en (768-dim, CPU) |
| Reranker | BAAI/bge-reranker-base (cross-encoder) |
| Vector Store | ChromaDB (local persistent) |
| LLM — Q&A pipeline | Groq API — `qwen/qwen3.8-27b` |
| LLM — Conflict analysis | Groq API — `qwen/qwen3.8-27b` (placeholder, not re-validated) |
| LLM — Eval judge | Groq API — `openai/gpt-oss-120b` (via RAGAS 0.4.3) |
| Observability | Langfuse v4 (`@observe()` decorator) |
| Evaluation | RAGAS 0.4.3 claim checking and metrics, 32-query eval set, own aggregation for ground-truth coverage |
| Tests | pytest: 59 offline tests; a GitHub Actions workflow runs them (first run on GitHub pending) |
| UI | Streamlit |
| Language | Python 3.13 (the version it was built and tested on) |

---

## Differentiators Over Vanilla RAG

| Feature | Vanilla RAG | This System |
|---|---|---|
| Query understanding | Keyword match or raw embedding | LLM validates + extracts structured filters + sub-query template |
| Retrieval | Single similarity search over all docs | Cartesian product per company/year/section combination |
| Reranking | None or single-pass | Per-combo cross-encoder reranking with focused sub-queries (effect not measured) |
| Context presentation | Flat chunk list | Chunks grouped by sub-query with headers for multi-hop |
| Citations | Source filename | Source passages with company, year, section and similarity score |
| Confidence | None | Retrieval similarity + LLM faithfulness, weighted (untuned; does not separate good answers from refusals) |
| Conflict detection | None | On-demand LLM comparison of year pairs for one company and section (truncated text, not evaluated) |
| Evaluation | None | 32 queries, metrics chosen per question type, ground truths audited against the filing text |
| Observability | None | Langfuse tracing on all pipeline steps |
| Chunking | Fixed-size | Sentence-aware, section-scoped, with overlap |

---

## Streamlit UI

The UI has two tabs:

**Query Tab** — submit a natural language question and receive:
- Answer grounded to retrieved passages
- Citation panel (chunk text, company, year, section, similarity score)
- Confidence score with breakdown (retrieval similarity, faithfulness, formula)

**Conflict Explorer Tab** — select company, section, and year range:
- Runs LLM analysis on every year pair in the selected range
- Displays conflicts with severity badges (high / medium / low)
- Shows side-by-side claims from each year with change description
- Summary counts (high / medium / low / no change)

The app runs locally (`streamlit run ui/app.py`); it is not deployed online.

---

## Documentation

- [`evaluation/EVAL_RESULTS_LATEST.md`](evaluation/EVAL_RESULTS_LATEST.md) — latest results, per query
- [`docs/EVAL_METRICS_GUIDE.md`](docs/EVAL_METRICS_GUIDE.md) — what each metric means and why one is custom
- [`docs/RAG_QUERY_TYPES.md`](docs/RAG_QUERY_TYPES.md) — the kinds of questions a RAG system gets
- [`docs/V2_POLISH_PLAN.md`](docs/V2_POLISH_PLAN.md) — the audit and the plan behind this cleanup
- [`docs/V2_PENDING_CHANGES.md`](docs/V2_PENDING_CHANGES.md) — open changes and review notes

---

## Installation

### Prerequisites

- Python 3.13 (built and tested on 3.13.3)
- 16GB RAM (no GPU required)
- A Groq API key. A paid tier is recommended for evaluation runs; one full 32-query run costs roughly $0.45–0.55 at current prices.

### Setup

```bash
git clone https://github.com/Shriram016/SEC-Filing-Intelligence-System.git
cd SEC-Filing-Intelligence-System

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env            # then set GROQ_API_KEY (the Langfuse keys are optional)
```

### Build the index (one-time, about 10–15 minutes)

Run from the **project root**:

```bash
python scripts/build_index.py                  # download → parse → sections → chunk → tag → embed → index
python scripts/build_index.py --start-at embed # resume from a later step
```

Steps whose output already exists are skipped, and the script stops with a message if a step leaves files missing. The individual scripts (`ingestion/downloader.py`, `parser.py`, `section_detector.py`, `chunker.py`, `metadata_tagger.py`, `embeddings/embedder.py`, `indexer.py`) can also be run one by one.

### Run the app

```bash
streamlit run ui/app.py
```

### Run the tests

```bash
pip install -r requirements-dev.txt
pytest tests/offline        # 59 tests; no API key or downloaded data needed
```

The scripts in `tests/integration/` check the real data, the index and live services; they are script-style and are run by hand.

### Run the evaluation

```bash
python evaluation/ragas_evaluator.py --dry-run          # show the plan, no API calls
python evaluation/ragas_evaluator.py --queries Q03 Q25  # selected queries
python evaluation/ragas_evaluator.py                    # all 32 queries (about 35 minutes)
python evaluation/rescore.py --run-id <run folder>      # re-score a finished run's saved answers
```

Each run writes its own folder under `evaluation/runs/` with the full record per query, the judge's per-statement verdicts, token counts and cost, and the per-query pipeline logs.

---

## Logging

Every query and conflict run produces a timestamped log file in `logs/`:

- `logs/query_YYYYMMDD_HHMMSS.log` — full pipeline trace per query (filter extraction, retrieval, synthesis, scoring)
- `logs/conflict_Company_Section_YYYYMMDD_HHMMSS.log` — conflict analysis trace per run

Evaluation runs also copy each query's pipeline log into `evaluation/runs/<run id>/query_logs/`, so a run folder is self-contained.

---

## Known Failures and Limitations

**Bugs found in an audit and deliberately not fixed in V2** (documented here so they can be fixed and measured later):

1. **The context cap can drop whole companies or years.** After per-combination reranking the chunks are joined combination by combination, and the synthesizer keeps the first 30 as if they were sorted globally. With four or more combinations the last company or year can be cut entirely.
2. **The conflict detector reads only the first 3,500 words of each year.** Most sections are longer (all 25 Item 1A, 21 of 25 Item 7, 14 of 25 Item 1), so a risk reported as "removed" may sit past the cut-off.
3. **Refusals get high confidence** (about 0.91–0.94) because a refusal is scored as perfectly faithful.
4. **Refusal detection in the pipeline is an exact-sentence match.** A reworded refusal is not recognised (the evaluation uses a tolerant check; the app does not).

**Behaviour weaknesses seen in the evaluation:**

- **Answers are free-form prose** with no enforced structure, length or citation format. In the original style they ran 400–700 words and some were cut off at the token cap; the concise style halves the length but can drop facts (cross-company ground-truth coverage is 0.47).
- **The query parser asks for JSON in the prompt only.** There is no enforced schema; an unparseable reply silently falls back to "no filters".
- **General questions ("what do companies say about X") retrieve unevenly**, dominated by one or two companies, and the answer generalises to "all companies".
- **Wrong details can pass the faithfulness check**: an answer that said a figure "decreased" from 139 to 208 was scored as fully faithful.

**Not validated or not measured:**

- **The conflict detector has never been evaluated**, and its model was swapped after Groq retired the original.
- **The confidence score** weights (0.4 / 0.6) are untuned, and the score does not separate good answers from refusals.
- **The reranker's effect was never measured.** Logs from one question showed identical reranker inputs leading to both a refusal and an answer, so the earlier claim that reranking fixed multi-hop refusals is unsupported (evidence in `evaluation/archive/evidence/`).
- **The LLM judge is lightly validated** (a few hand-checked answers), and the run-to-run spread of the scores has not been measured yet.

**Environment and data:**

- **The original V2 models were retired by Groq**, so the earlier published numbers cannot be reproduced; all current numbers use the replacement models.
- **Financial tables (Item 8) and Items 2–6 are not indexed**, so questions that depend on them are declined.
- **Rate limits:** conflict analysis waits 65 seconds between calls; a full 32-query evaluation takes about 35 minutes.
- **Single-user, local.** Streamlit is not a production server, and the app is not deployed online.
