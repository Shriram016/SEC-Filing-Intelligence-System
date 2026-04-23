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
│  Answer         │  LlamaIndex orchestrates context assembly
│  Synthesis      │  Groq API (Llama 3) generates grounded answer
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Citation       │  Maps each claim to source chunk
│  Extractor      │  Returns company, year, section, page metadata
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
Embeds the user query, retrieves top-k chunks from ChromaDB with similarity scores. Supports metadata filtering for targeted retrieval by company, year, or section.

### 4. Answer Synthesis
LlamaIndex assembles context from retrieved chunks. Groq API (Llama 3) generates an answer grounded strictly to retrieved context.

### 5. Citation Extractor
Maps the generated answer to the specific retrieved passages it was derived from. Returns source metadata — company, year, section, page — for every citation.

### 6. Confidence Scorer
Combines two signals into a single weighted score:
- **Retrieval similarity** — cosine similarity between query and retrieved chunks
- **Faithfulness** — LLM-judged score: does the answer stay within the bounds of retrieved passages?

### 7. Conflict Detector
Two-stage pipeline:
- **Stage 1** — semantic similarity comparison across years flags candidate section pairs
- **Stage 2** — LLM reads flagged pairs and identifies actual contradictions with severity assessment

### 8. Evaluation Pipeline
- **RAGAS** — retrieval precision, faithfulness, hallucination rate
- **Custom evaluators** — citation accuracy (is the cited passage actually the source?) and conflict detection accuracy (are flagged conflicts real?)

---

## Tech Stack

| Layer | Tool |
|---|---|
| HTML Parsing | BeautifulSoup + lxml |
| Embeddings | BAAI/bge-base-en |
| Vector Store | ChromaDB |
| Orchestration | LlamaIndex |
| LLM | Groq API — Llama 3 |
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

