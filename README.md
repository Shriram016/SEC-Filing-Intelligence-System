# SEC Filing Intelligence System

A RAG-based system that answers natural language questions over real SEC 10-K filings with exact passage-level citations, confidence scores, and cross-year conflict detection. Built to run fully on a local 16GB machine.

---

## What This Project Does

Most RAG systems retrieve documents and generate answers. This system goes further:

- **Answers questions** grounded to specific passages in SEC filings — not just filenames
- **Scores confidence** using a weighted combination of retrieval similarity and LLM-judged faithfulness
- **Detects conflicts** across filing years — when a company's statements in 2020 contradict 2023
- **Evaluates itself** using RAGAS metrics and custom evaluators for citation accuracy and conflict detection

---

## Dataset

| Dimension | Detail |
|---|---|
| Companies | Apple, Microsoft, Amazon, Google, Meta |
| Years | 2020, 2021, 2022, 2023, 2024 |
| Total Filings | 25 10-K filings from SEC EDGAR |
| Source | Publicly available via EDGAR full-text search |

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────┐
│  Retrieval      │  Embed query → ChromaDB top-k search
│  Engine         │  Filter by metadata (company, year, section)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Answer         │  Chunks assembled into numbered context window
│  Synthesis      │  Groq API (Llama 3) generates grounded answer
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Citation       │  format_citations() on Synthesizer — no separate
│  Extractor      │  component. Sources already returned by synthesizer.
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Confidence     │  Retrieval similarity score (ChromaDB)
│  Scorer         │  + LLM faithfulness score (prompted judge)
└────────┬────────┘
         │
         ▼
    Final Output
    Answer + Citations + Confidence Score
```

**Conflict Detection runs as a separate pipeline:**

```
User selects company + section
    │
    ▼
Retrieve same section across all 5 years
    │
    ▼
Pairwise semantic similarity → flag low-similarity year pairs
    │
    ▼
LLM analyzes flagged pairs → identifies actual contradictions
    │
    ▼
Conflict Report (what changed, which years, severity)
```

---

## Scope: Which Sections We Focus On

A 10-K filing has 15+ sections. This system focuses on **4 high-signal sections** only:

| Section | Name | Why included |
|---|---|---|
| Item 1 | Business | Explains what the company does — answers "what/how" questions |
| Item 1A | Risk Factors | Richest section for cross-year conflict detection — companies quietly add/drop risks |
| Item 7 | MD&A | Management's narrative on financials — most analyst-relevant section |
| Item 7A | Market Risk | Quantitative exposure data — comparable across years |

**Why not the other sections?**
- Item 8 (Financial Statements) — actual numbers live here, but it is almost entirely tables. Table extraction from iXBRL HTML requires special handling beyond plain text parsing and is out of scope for v1.
- Items 2, 3, 4 (Properties, Legal, Mine Safety) — mostly boilerplate, low signal for meaningful questions.
- Items 9–15 — procedural disclosures (auditor info, governance, executive compensation) — not relevant to financial analysis questions.

This scoping keeps retrieval sharp and focused.

**Current limitation:** Tables (like Item 8 Financial Statements) are not parsed in v1. Flattening HTML tables to plain text breaks the row-column relationship, making retrieval unreliable for numerical data. Proper table-aware RAG requires converting table rows to natural language sentences or a text-to-SQL approach — planned for v2.

---

## Key Components

### 1. Ingestion Pipeline
Downloads 10-K filings (HTM/iXBRL HTML) from SEC EDGAR, extracts clean text via BeautifulSoup + lxml, detects section boundaries (Item 1, Item 1A, Item 7, Item 7A), and applies hierarchical chunking — section-aware at the top level, fixed-size with overlap within sections. Every chunk is tagged with `{company, year, section, page, chunk_id}`.

### 2. Embedding + Indexing
BAAI/bge-base-en embeds every chunk. ChromaDB stores vectors and metadata. Ingestion runs once and persists locally.

### 3. Retrieval Engine
Takes a raw natural language query and returns the most relevant chunks from ChromaDB. No filter dropdowns — the query is understood automatically.

**Query understanding (Groq, temperature=0):** A single LLM call validates whether the query is answerable from SEC 10-K filings, and extracts all mentioned companies, years, and sections as lists. Handles paraphrases naturally (`"fiscal 2023"` → 2023, `"risk factors"` → Item 1A).

**Cartesian product retrieval:** If multiple companies or years are detected, the retriever generates every combination (e.g. AAPL×2020, MSFT×2020) and runs one ChromaDB query per combination — top-k each. This guarantees balanced representation for comparison queries rather than letting one company dominate the results.

**No reranker needed:** Three design choices eliminate the need for a separate reranking step: (1) metadata pre-filtering narrows the candidate pool to the right company/year/section before vector search; (2) BGE's asymmetric retrieval (query prefix at query time only) achieves the same query-document alignment that cross-encoders provide; (3) per-combination top-k means there is never a large noisy pool that needs reordering.

### 4. Answer Synthesis
Retrieved chunks are assembled into a numbered context window. Groq API (Llama 3) generates an answer grounded strictly to the provided passages — the system prompt explicitly forbids drawing on training knowledge.

### 5. Citation Extractor
Built as `format_citations()` inside the `Synthesizer` class — not a standalone component. The synthesizer already returns the source chunks used to generate the answer (`"sources"` field), so no separate extraction step is needed. `format_citations()` reshapes that list into a display-ready format: chunk text, company, year, section, chunk ID, and similarity score.

Source-level citation (which chunks were used) rather than claim-level (which sentence came from which chunk) — claim-level requires an extra LLM call per query and is unreliable for multi-point comparative answers.

### 6. Confidence Scorer
Combines two signals into a single weighted score:
- **Retrieval similarity** — cosine similarity between query and retrieved chunks
- **Faithfulness** — LLM-judged score: does the answer stay within the bounds of retrieved passages?

### 7. Conflict Detector
The core differentiator of this project. A plain Q&A system answers questions the user knows to ask. The Conflict Detector surfaces what the user didn't know to ask: *did this company say something materially different about this topic in 2020 vs 2023?*

SEC 10-K filings are uniquely suited to this — same company, same structured sections (Item 1A, Item 7), five consecutive years. Companies quietly soften risk language, drop previously disclosed risks, or shift framing between filings. Analysts do this comparison manually today. This automates it.

Two-stage pipeline to keep LLM costs down:
- **Stage 1 (similarity filter)** — pairwise cosine similarity across years flags only the pairs where language actually shifted. There are up to 200 possible year-pairs across all companies and sections — the filter runs fast vector math to narrow this to a small set of genuine candidates.
- **Stage 2 (LLM analysis)** — the LLM reads only the flagged pairs and identifies actual contradictions with severity (high / medium / low). Expensive reasoning only on what passed the cheap filter.

### 8. Evaluation Pipeline
- **RAGAS** — retrieval precision, faithfulness, answer relevance, hallucination rate across 10 predefined queries with ground truth answers
- Custom evaluators were considered and dropped — citation accuracy overlaps directly with RAGAS faithfulness, and conflict detection accuracy requires manual ground truth labelling for marginal gain over reading the output directly

---

## Tech Stack

| Layer | Tool |
|---|---|
| HTML Parsing | BeautifulSoup + lxml |
| Embeddings | BAAI/bge-base-en |
| Vector Store | ChromaDB |
| LLM / Synthesis | Groq API — Llama 3 (direct API, no framework) |
| Evaluation | RAGAS + custom evaluators |
| UI | Streamlit |
| Language | Python |

---

## Differentiators Over Vanilla RAG

| Feature | Vanilla RAG | This System |
|---|---|---|
| Citations | Source filename | Exact passage + metadata |
| Confidence | None | Retrieval + faithfulness weighted score |
| Conflict detection | None | Two-stage semantic + LLM pipeline |
| Evaluation | None | RAGAS + custom eval suite |
| Chunking | Fixed-size | Hierarchical section-aware |


---

## Streamlit UI

The UI exposes three views:

**Query View** — submit a natural language question and receive:
- Answer
- Citation panel (passages, company, year, section, page)
- Confidence score with breakdown

**Conflict Explorer** — select a company and section to view a cross-year conflict report

**Eval Dashboard** — RAGAS metrics and custom eval scores as charts

---

## Installation

### Prerequisites

- Python 3.10+
- 16GB RAM (runs fully locally — no GPU required)
- Groq API key (free tier sufficient)

### Setup

```bash
# Clone the repository
git clone https://github.com/your-username/sec-rag-intelligence.git
cd sec-rag-intelligence

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GROQ_API_KEY=your_key_here
```

### Run Ingestion (one-time)

```bash
# Download and process all 25 filings
python ingestion/downloader.py
python ingestion/parser.py
python ingestion/chunker.py

# Embed and index into ChromaDB
python embeddings/indexer.py
```

### Run the App

```bash
streamlit run ui/app.py
```

### Run Evaluation

```bash
python evaluation/ragas_evaluator.py
python evaluation/custom_evaluator.py
```

