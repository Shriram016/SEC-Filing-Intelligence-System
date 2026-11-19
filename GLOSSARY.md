# Glossary — V3

One meaning per term. Use these words the same way in code, docs and talks.

| Term | Meaning |
|---|---|
| **Corpus** | The 360 FinanceBench PDFs. Fixed; no user uploads |
| **Document catalog** | One row per PDF: company, doc type, fiscal period, period dates. Used by the coverage check |
| **Chunk** | One stored piece of a document: a text section or one whole table, with metadata |
| **Table label** | A 1–2 sentence description added to a table chunk for search. The table itself is stored unchanged |
| **Fiscal year (FY)** | The company's own reporting year. A year in a question means the fiscal year |
| **Period dates** | The real start/end dates of a filing's period, read from the cover page |
| **Shared store** | One index with all chunks; V3 finds the right document itself (no one hands it the PDF) |
| **Metadata filter** | A search limit on company, doc type, period or section |
| **Fallback search** | A second search with fewer filters when the first finds nothing |
| **Router** | The first step: classifies the question and runs the coverage check before any search |
| **Route** | The router's decision: `unrelated`, `advice`, `not_covered`, `unclear`, `answer` |
| **Coverage check** | Code lookup in the document catalog: does a filing exist for this company and period? |
| **Planner** | The LLM call that writes the list of steps for a question |
| **Plan first** | Make the full plan once, then run it; at most one re-plan |
| **Step** | One planned action: find a fact, or calculate |
| **Calculator tool** | Code that does all arithmetic and returns result + formula + inputs |
| **Claim** | One statement in an answer, with an exact quote and a chunk ID |
| **Quote check** | Code check that a claim's quote exists in the chunk and its numbers match |
| **Partial answer** | An answer that says exactly which steps found nothing |
| **Could not find** | Reply when a covered filing exists but search missed the fact (a retrieval failure) |
| **Locked benchmark** | The 150 FinanceBench questions. Run only at M3 and M6; never used to tune |
| **Held-out behaviour subset** | Dev behaviour questions kept unseen until M6 |
| **Dev set** | Questions drafted by Claude and confirmed by the user; used daily |
| **Test leakage** | Choosing a tool, setting or prompt by looking at locked questions or their evidence |
| **Baseline** | Plain RAG: split, search, one LLM answer, no checks. Same documents and model as V3 |
| **Judge** | The LLM (OpenAI family) that marks text answers against the gold answer |
| **Failure cause** | Why an answer failed: parsing, retrieval, planning, generation, reasoning |
| **Quality gate** | ~20 dev questions run with the real AI; fails if the score drops beyond a set margin. Manual for now |
| **Real-AI run** | Any run that calls a paid model. Manual, cost shown first |
| **SSE** | Server-Sent Events: the API streams progress events, then the checked answer |
| **Walking skeleton** | A thin end-to-end version built first, then deepened |
| **Indirect prompt injection** | Instructions hidden in document text |
| **Direct prompt injection** | Tricks typed by the user ("ignore your rules") |
