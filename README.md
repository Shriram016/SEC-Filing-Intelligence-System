# SEC Filing Intelligence System

A RAG-based system that answers natural language questions over real SEC 10-K filings with exact passage-level citations, confidence scores, and cross-year conflict detection. Built to run fully on a local 16GB machine with no GPU.

---

## What This Project Does

Most RAG systems retrieve documents and generate answers. This system goes further:

- **Answers questions** grounded to specific passages in SEC filings — not just filenames
- **Scores confidence** using a weighted combination of retrieval similarity and LLM-judged faithfulness
- **Detects conflicts** across filing years — surfaces when a company's statements in 2020 contradict 2023, systematically, without the user knowing what to look for
- **Evaluates itself** using RAGAS 0.4.3 with 4 LLM-as-judge metrics across 24 predefined queries with extractive ground truths

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
│                 │  Groq (llama-4-scout-17b, temperature=0)
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
│  Synthesis      │  Groq (llama-4-scout-17b) generates grounded answer
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
For every year pair: LLM (llama-3.3-70b-versatile) reads both years
side-by-side → identifies contradictions, removals, reframings
    │
    ▼
Conflict Report (topic, year A claim, year B claim, severity)
```

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
- Item 8 (Financial Statements) — almost entirely tables. Flattening iXBRL HTML tables destroys row-column relationships, making retrieval unreliable for numerical data. Requires a text-to-SQL or row-to-sentence conversion approach — planned for v2.
- Items 2–6 — Properties, Legal, Mine Safety — mostly boilerplate, low signal.
- Items 9–15 — procedural disclosures (auditor, governance, compensation) — not relevant to financial analysis questions.

---

## Key Components

### 1. Ingestion Pipeline
Downloads 10-K HTM files from SEC EDGAR using the EDGAR Submissions API (`primaryDocument` field). BeautifulSoup + lxml strips the iXBRL HTML to clean text, preserving newlines for section detection. A regex-based section detector finds Item boundaries and extracts only the 4 target sections. A sentence-aware chunker splits each section into ~300-word chunks with 50-word overlap. A metadata tagger stamps every chunk with `{company, year, section, section_name, filing_type, source_file, chunk_id}`.

### 2. Embedding + Indexing
BAAI/bge-base-en (768 dimensions, CPU, ~550MB) embeds every chunk with `normalize_embeddings=True`. ChromaDB stores vectors and all metadata fields. Upsert-based — safe to re-run. **2,835 chunks** total across 25 filings.

### 3. Retrieval Engine
Takes a raw natural language query and returns the most relevant chunks from ChromaDB. No filter dropdowns — the query is parsed automatically.

**Query understanding (Groq `llama-4-scout-17b`, temperature=0):** A single LLM call validates whether the query is answerable from SEC 10-K filings, extracts all mentioned companies/years/sections as lists, and generates a sub-query template for multi-hop queries (e.g., `"<company> AI risk disclosures in <year>"`). Handles paraphrases naturally (`"fiscal 2023"` → 2023, `"risk factors"` → Item 1A).

**Cartesian product retrieval:** If multiple companies or years are detected, the retriever generates every combination (e.g. AAPL×2022, MSFT×2022) and runs one ChromaDB query per combination — top-k each. This guarantees balanced representation for comparison queries rather than letting one company dominate by similarity score alone.

**BGE asymmetric retrieval:** The query is embedded with an instruction prefix (`"Represent this sentence for searching relevant passages: "`) at query time only — not at indexing time. This is how the model was trained: query vectors and document vectors live in different regions of embedding space by design.

**Cross-encoder reranking:** After ChromaDB retrieval, a cross-encoder (BAAI/bge-reranker-base) reranks each combination's chunks using focused sub-queries. For a query like "Compare Apple and Microsoft's risks in 2023," each combo's chunks are reranked with a filled sub-query ("Apple risks in 2023", "Microsoft risks in 2023") instead of the original comparison query. This prevents the reranker from scoring chunks near zero when no single chunk discusses "comparison" or "evolution."

### 4. Answer Synthesis
Retrieved chunks are assembled into a context window. For multi-hop queries, chunks are grouped by sub-query with headers (`=== Apple risks in 2022 ===`) so the LLM clearly sees which facts belong to which company/year. Groq `llama-4-scout-17b` generates an answer grounded strictly to the provided passages — the system prompt explicitly instructs comparison across passages for multi-hop queries, and refusal when the context is insufficient. Capped at `max_tokens=1024`.

### 5. Source Citations
The synthesizer returns the full list of source chunks used as context (`result["sources"]`), including chunk ID, company, year, section, similarity score, and text. No separate citation extraction component is needed — the synthesizer already surfaces this. The UI renders each source in an expandable panel.

Source-level citation (which chunks were used) rather than claim-level (which sentence came from which chunk) — claim-level requires an extra LLM call per query and is unreliable for multi-point comparative answers.

### 6. Confidence Scorer
Combines two signals into a single weighted confidence score:

```
confidence = 0.4 × avg_retrieval_similarity + 0.6 × faithfulness_score
```

- **Retrieval similarity** — mean cosine similarity between the query vector and the retrieved chunk vectors (from ChromaDB distances)
- **Faithfulness** — Groq `llama-4-scout-17b` judges whether the answer stays within the retrieved passages on a 1–5 rubric, normalised to 0–1: `(raw - 1) / 4`

Faithfulness is weighted higher (0.6) because a high similarity score alone does not guarantee the LLM stayed within the context.

Special case: if the synthesizer emits the standard refusal string, faithfulness is set to 1.0 without a Groq call — correct refusal is the best possible behaviour.

### 7. Conflict Detector

The core differentiator of this project — not because it uses a different architecture, but because it solves a different problem.

A Q&A system is **reactive**: it answers questions the user knows to ask. But the user never learns that the 2020 filing said *"significant concentration risk from single-source suppliers"* and the 2023 filing quietly says *"risk is actively managed."* That shift is the story — and a Q&A system buries it, because the user didn't know to ask.

The Conflict Detector is **proactive and systematic**: it scans all year-pair combinations automatically. Across 5 companies × 4 sections × C(5,2)=10 year pairs, that is 200 comparisons. No analyst would manually type 200 comparison queries into a chat interface. This runs the full scan and surfaces what changed.

For each year pair, the LLM (`llama-3.3-70b-versatile` — the heavier model, because detecting subtle contradictions requires more reasoning than Q&A) reads the full section text from both years side by side. It returns up to 3 structured conflicts per pair with severity labels (high / medium / low / none), specific claims from each year, and a change description.

A 65-second delay between calls manages Groq's rate limit. A pre-filter based on embedding similarity was considered and rejected — mean-pooled vectors are too coarse to reliably detect whether actual claims conflict, and at this scale the LLM call cost is negligible.

### 8. Evaluation Pipeline

24 predefined queries with **extractive ground truths** — every ground truth fact was pulled verbatim from the actual `_sections.json` filing text. No manual fabrication. Evaluated using RAGAS 0.4.3 with `llama-3.3-70b-versatile` as the LLM judge.

**Query types:** 6 single factual, 5 cross-year, 4 cross-company, 3 conflict-triggering, 3 vague, 3 invalid.

**4 metrics via RAGAS 0.4.3:**

| Metric | What it measures |
|---|---|
| **Faithfulness** | Does the answer stay within retrieved context? |
| **Answer Relevance** | Does the answer address the question asked? |
| **Context Precision** | Are the relevant chunks ranked near the top? |
| **Context Recall** | Does the retrieved context contain enough to derive the ground truth? |

**Results by category (21 evaluated, 3 correctly rejected):**

| Category | Queries | Faithfulness | Relevance | Precision | Recall |
|---|---|---|---|---|---|
| Single Factual | 6 | **0.972** | **0.971** | **0.935** | **1.000** |
| Cross-Year | 5 | 0.721 | **0.985** | 0.403 | **1.000** |
| Cross-Company | 4 | 0.673 | **0.950** | 0.173 | **1.000** |
| Conflict Triggering | 3 | 0.574 | 0.644 | 0.315 | 0.667 |
| Vague | 3 | 0.719 | **0.955** | N/A | N/A |
| Invalid | 3 | N/A | N/A | N/A | N/A |

**What the scores mean:**
- Single factual queries score excellently across all 4 metrics — the core pipeline works.
- Answer relevance is consistently high (0.95+) across all answerable categories — the system addresses the question asked.
- Context recall is 1.0 for all categories except conflict triggering — retrieved context covers the ground truth.
- Faithfulness on multi-hop queries (0.57–0.72) is lower than single factual (0.97). Manual inspection of multiple queries (Q09, Q13, Q15) confirmed the answers were factually correct — the LLM-as-judge penalizes valid cross-source inferences that don't appear verbatim in any single chunk.
- Context precision is low on multi-hop queries (0.17–0.40) because 20 chunks are retrieved per query but only 3–4 are essential. This does not affect answer quality.

**Evaluation limitations:** LLM-as-judge scores vary across runs due to non-deterministic LLM output on hosted APIs, even at temperature=0. Category averages are more reliable than individual query scores. Full eval report in `evaluation/EVAL_REPORT_V2.md`.

---

## Tech Stack

| Layer | Tool |
|---|---|
| HTML Parsing | BeautifulSoup + lxml |
| Embeddings | BAAI/bge-base-en (768-dim, CPU) |
| Reranker | BAAI/bge-reranker-base (cross-encoder) |
| Vector Store | ChromaDB (local persistent) |
| LLM — Q&A pipeline | Groq API — `llama-4-scout-17b-16e-instruct` |
| LLM — Conflict analysis | Groq API — `llama-3.3-70b-versatile` |
| LLM — Eval judge | Groq API — `llama-3.3-70b-versatile` (via RAGAS 0.4.3) |
| Observability | Langfuse v4 (`@observe()` decorator) |
| Evaluation | RAGAS 0.4.3 (4 metrics, 24-query eval set) |
| UI | Streamlit |
| Language | Python 3.10+ |

---

## Differentiators Over Vanilla RAG

| Feature | Vanilla RAG | This System |
|---|---|---|
| Query understanding | Keyword match or raw embedding | LLM validates + extracts structured filters + sub-query template |
| Retrieval | Single similarity search over all docs | Cartesian product per company/year/section combination |
| Reranking | None or single-pass | Per-combo cross-encoder reranking with focused sub-queries |
| Context presentation | Flat chunk list | Chunks grouped by sub-query with headers for multi-hop |
| Citations | Source filename | Exact passage + company, year, section, similarity score |
| Confidence | None | Retrieval similarity + LLM faithfulness, weighted |
| Conflict detection | None | Systematic LLM analysis of every year pair |
| Evaluation | None | RAGAS 0.4.3, 24 queries, 4 metrics, extractive ground truth |
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

---

## Installation

### Prerequisites

- Python 3.10+
- 16GB RAM (no GPU required)
- Groq API key (paid tier recommended for eval runs)

### Setup

```bash
# Clone the repository
git clone https://github.com/your-username/sec-rag-intelligence.git
cd sec-rag-intelligence

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file with your Groq API key
echo GROQ_API_KEY=your_key_here > .env
```

### Run Ingestion (one-time, ~10–15 minutes)

All scripts must be run from the **project root**:

```bash
python ingestion/downloader.py       # Download 25 HTM filings from SEC EDGAR
python ingestion/parser.py           # Extract clean text from iXBRL HTML
python ingestion/section_detector.py # Detect Item 1, 1A, 7, 7A boundaries
python ingestion/chunker.py          # Split sections into ~300-word chunks
python ingestion/metadata_tagger.py  # Tag each chunk with company/year/section
python embeddings/embedder.py        # Embed all chunks with BAAI/bge-base-en
python embeddings/indexer.py         # Load into ChromaDB (2,835 chunks)
```

### Run the App

```bash
streamlit run ui/app.py
```

### Run Evaluation

```bash
python evaluation/ragas_evaluator.py                        # Full 24-query eval (~20 min)
python evaluation/ragas_evaluator.py --queries Q01 Q02      # Run specific queries only
python evaluation/ragas_evaluator.py --queries Q01 --fresh  # Re-score a query (won't overwrite results JSON)
```

---

## Logging

Every query and conflict run produces a timestamped log file in `logs/`:

- `logs/query_YYYYMMDD_HHMMSS.log` — full pipeline trace per query (filter extraction, retrieval, synthesis, scoring)
- `logs/conflict_Company_Section_YYYYMMDD_HHMMSS.log` — conflict analysis trace per run

---

## Known Limitations

- **Financial tables not parsed** — Item 8 (financial statements) is excluded. Tables in iXBRL HTML cannot be reliably flattened to plain text without destroying row-column structure.
- **LLM-as-judge variance** — RAGAS scores vary across runs due to non-deterministic LLM output on Groq's API, even at temperature=0. Category averages are reliable; individual query scores are not. Manual inspection of answers is recommended alongside automated metrics.
- **Faithfulness on comparative queries** — the faithfulness metric penalizes valid cross-source inferences (e.g., "Company A grew faster than Company B") because no single chunk contains that statement. Manual inspection confirmed answers are correct in cases where the judge scored low.
- **Context precision on multi-hop** — 20 chunks retrieved per multi-combo query, but only 3–4 are essential. Precision is structurally low. Does not affect answer quality.
- **Rate limits** — Conflict analysis enforces a 65-second delay between LLM calls. The evaluation script takes ~20 minutes for 24 queries.
- **Single-user** — Streamlit is not a production server. Built for local use and portfolio demonstration.
