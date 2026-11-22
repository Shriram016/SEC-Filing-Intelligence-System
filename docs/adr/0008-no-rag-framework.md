# ADR-0008 — Direct libraries, no RAG framework (LangChain / LlamaIndex)

**Status:** accepted (2026-11-20). **Source:** grilling log Q98. **Scope:** ingestion now; the answer and agent steps decide again at their milestone.

## Decision
Build the pipeline on small direct libraries, not on a RAG framework:

| Job | Library |
|---|---|
| Read PDF | pdfplumber |
| Embed | sentence-transformers (bge-base-en-v1.5) |
| Store and search | qdrant-client |
| Everything specific to SEC filings | Own code in `src/filing_rag/ingest/` |

## Reasons
1. **Most of the work is specific to SEC filings, and no framework has it.** A framework would still need all of these as custom parts:
   - Items, 8-K item codes, Notes and exhibit headings, with a fallback to page headings (Q90);
   - tables as layout text, joined across pages, split into row groups that repeat the headers (Q88, Q94);
   - period dates from the cover page, and checks against the document list (Q96, Q97);
   - checks that find errors in the document list (wrong type, wrong year, broken files).
2. **The generic parts are already small.** Load, embed and store are a few lines each with the direct libraries. A framework saves little here.
3. **Full control over chunk size.** Chunks are measured with the embedding model's own tokenizer on the exact text that is embedded (label + text), so no chunk goes over the 512-token input limit (M1b result: 0 of 8,568 chunks over the limit). Generic splitters usually count characters or use a different tokenizer.
4. **Correct labels need visible logic.** The chunk label (company › type › year › section path) is made by code and checked by rules and a measured hand-check. Each step can be read, tested and fixed. Framework defaults (for example, which metadata goes into the embedded text) are hidden in layers.
5. **Rules that fit our data.** One bad file never stops a run (skip and log). A re-run replaces a document's chunks (idempotent). Each chunk keeps `list_fiscal_year` next to the year read from the document.
6. **Few dependencies, stable code.** Framework APIs change often. Three small libraries are easier to pin, audit (pip-audit in CI) and upgrade.
7. **Portfolio value.** The code shows how each RAG step works, not only how to call a framework.

## Where the advantage was measured or seen (M1b, 22 documents)
- Items found in all standard 10-Ks, and also in MGM and CVS, where simple rules had failed.
- Data errors found that a generic loader would hide: Lockheed "10-Q" is an earnings release; PG&E "earnings" is an 8-K; Ulta list year 2024 vs "Fiscal 2023" in the text; one Intel file unrecoverable.
- 0 chunks over the token limit; 0 duplicate chunk ids; large tables keep their headers in every part.

## Consequences
- More own code to test: 80+ unit tests cover the ingest package.
- Changing the vector store or the embedding model means a small adapter (`store.py`, `embed.py`), not a config switch.
- New team members must learn our modules instead of known framework classes. The specs (`docs/v3/ingestion.md`) and docstrings explain each module.

## When to look again
- The answer or agent step needs features that a framework gives for free (for example tool calling, tracing or evaluation tools) and that would take a lot of own code.
- A second data source with a different format is added, and framework loaders cover it.

## Rejected
- **LangChain:** generic loaders and splitters; SEC logic would still be custom; many layers and frequent API changes.
- **LlamaIndex:** good node and metadata handling, but the SEC logic would still be custom; its best PDF parser (LlamaParse) is a paid service (no paid parsing, Q85).
- **Framework for the simple parts only:** saves a few lines but adds a large dependency and two styles of code.
