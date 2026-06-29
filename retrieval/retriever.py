"""
retrieval/retriever.py

Component 8 — Query understanding + semantic retrieval from ChromaDB.

Responsibilities:
  1. Parse raw user query via Groq (validate + extract metadata filters)
  2. Build filter combinations (Cartesian product of all extracted values)
  3. Embed query with BGE_QUERY_PREFIX using same BAAI/bge-base-en model
  4. Query ChromaDB — one call per filter combination
  5. Merge results, deduplicate, convert distances to similarity scores, sort

Run from project root:
    python retrieval/retriever.py
"""

import os
import sys
import json
import itertools

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import chromadb
from groq import Groq
from langfuse import observe

# Allow imports from project root regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    EMBEDDING_MODEL,
    BGE_QUERY_PREFIX,
    CHROMA_PERSIST_DIR,
    TOP_K,
    TICKERS,
    YEARS,
    TARGET_SECTIONS,
    COMPANIES,
    GROQ_MODEL,
)
from retrieval.reranker import Reranker

load_dotenv()

# -----------------------------------------------------------------------
# Lookup tables — used to sanitise LLM extraction output
# -----------------------------------------------------------------------
COMPANY_TO_TICKER = dict(zip(COMPANIES, TICKERS))   # "Apple" → "AAPL"
TICKER_TO_COMPANY = {v: k for k, v in COMPANY_TO_TICKER.items()}  # "AAPL" → "Apple"
TICKER_SET        = set(TICKERS)                     # {"AAPL", "MSFT", ...}
VALID_YEARS       = set(YEARS)                       # {2020, 2021, ..., 2024}
VALID_SECTIONS    = set(TARGET_SECTIONS.keys())      # {"Item 1", "Item 1A", ...}


class Retriever:
    """
    Validates a raw user query, extracts metadata filters via Groq,
    builds Cartesian product of filter combinations, and retrieves
    top-k chunks per combination from ChromaDB.
    """

    def __init__(self):
        print("Loading BGE embedding model...")
        self.model = SentenceTransformer(EMBEDDING_MODEL)

        print("Connecting to ChromaDB...")
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        self.collection    = self.chroma_client.get_collection("sec_filings")

        print("Loading cross-encoder reranker...")
        self.reranker = Reranker()

        print("Initialising Groq client...")
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not found. "
                "Create a .env file at project root with: GROQ_API_KEY=your_key"
            )
        self.groq_client = Groq(api_key=api_key)

        print("Retriever ready.\n")

    # -------------------------------------------------------------------
    # Private: query understanding
    # -------------------------------------------------------------------

    @observe(name="filter_extraction", as_type="generation")
    def _extract_filters(self, query: str, logger=None) -> dict:
        """
        Single Groq call (temperature=0) that:
          1. Validates the query is answerable from SEC 10-K filings
          2. Extracts ALL mentioned tickers, years, and section keys as lists

        Returns:
            {
                "is_valid":         bool,
                "rejection_reason": str | None,
                "tickers":          list[str],   # e.g. ["AAPL", "MSFT"]
                "years":            list[int],   # e.g. [2020, 2023]
                "sections":         list[str]    # e.g. ["Item 1A"]
            }
        """
        if logger:
            logger.info(f"RETRIEVER | filter_extraction | ENTER | query={query!r}")

        prompt = f"""You are a query parser for a SEC 10-K filing RAG system.

The database contains 10-K annual reports for these companies ONLY:
  - Apple     (ticker: AAPL)
  - Microsoft (ticker: MSFT)
  - Amazon    (ticker: AMZN)
  - Google    (ticker: GOOGL)
  - Meta      (ticker: META)

Years available: 2020, 2021, 2022, 2023, 2024

Sections available:
  - "Item 1"  → Business (company overview, products, operations)
  - "Item 1A" → Risk Factors (risks, uncertainties, threats)
  - "Item 7"  → MD&A (revenue, financials, management discussion, growth)
  - "Item 7A" → Market Risk (interest rate risk, currency risk, hedging)

Your tasks:
1. VALIDATE: Is the query answerable from SEC 10-K filings?
   Mark invalid ONLY if completely unrelated to companies, finance, business, or risk.

2. EXTRACT TICKERS: List ALL company tickers explicitly or implicitly mentioned.
   "Apple and Microsoft" → ["AAPL", "MSFT"]
   "tech giants" or "all companies" → [] (too vague, leave empty)

3. EXTRACT YEARS: List ALL years mentioned.
   "fiscal 2023", "FY2023", "2023 filing" → [2023]
   "2020 and 2021" → [2020, 2021]
   "last few years" → [] (too vague, leave empty)

4. EXTRACT SECTIONS: List section keys ONLY if the query clearly targets a specific section.
   "risk factors", "risks", "threats" → ["Item 1A"]
   "revenue", "financials", "MD&A", "earnings" → ["Item 7"]
   "business", "products", "operations" → ["Item 1"]
   "market risk", "interest rate", "currency" → ["Item 7A"]
   If unclear or spans multiple sections → []

5. SUB-QUERY TEMPLATE: If the query compares across multiple companies OR multiple years,
   create a short template that captures the core topic of the query.
   Use <company> and <year> as placeholders — these will be filled for each combination.
   The template should preserve the specific topic from the original query (e.g., "AI risks",
   "competitive risks", "headcount") — not generic terms like "data" or "information".
   If the query targets a single company AND single year, set to null.

   Examples:
   "How did Microsoft's AI risk evolve from 2022 to 2023?" → "<company> AI risk disclosures in <year>"
   "Compare Apple and Microsoft's competitive risks in 2023" → "<company> competitive risks in <year>"
   "What were Apple's risk factors in 2022?" → null

Return ONLY valid JSON in this exact format. No explanation, no markdown fences:
{{
    "is_valid": true or false,
    "rejection_reason": null or "brief reason",
    "tickers": [],
    "years": [],
    "sections": [],
    "sub_query_template": null or "template string"
}}

Query: {query}"""

        if logger:
            logger.info(f"RETRIEVER | filter_extraction | Groq call | model={GROQ_MODEL}")

        response = self.groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=250,
        )

        raw = response.choices[0].message.content.strip()

        if logger:
            logger.info(f"RETRIEVER | filter_extraction | Groq response | raw={raw!r}")

        # Strip markdown code fences if the LLM added them despite instructions
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw   = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Safe fallback: treat as valid, no filters — never block the user on a parse error
            if logger:
                logger.warning("RETRIEVER | filter_extraction | JSON parse failed — falling back to no filters")
            return {
                "is_valid":         True,
                "rejection_reason": None,
                "tickers":          [],
                "years":            [],
                "sections":         [],
                "sub_query_template": None,
            }

        # Sanitise — silently drop values outside our bounded dataset
        parsed["tickers"]  = [t for t in parsed.get("tickers",  []) if t in TICKER_SET]
        parsed["years"]    = [y for y in parsed.get("years",    []) if y in VALID_YEARS]
        parsed["sections"] = [s for s in parsed.get("sections", []) if s in VALID_SECTIONS]

        # Validate sub_query_template
        template = parsed.get("sub_query_template")
        if isinstance(template, str):
            template = template.strip()
            if not template:
                template = None
            elif "<company>" not in template and "<year>" not in template:
                template = None
        else:
            template = None
        parsed["sub_query_template"] = template

        if logger:
            logger.info(
                f"RETRIEVER | filter_extraction | EXIT | "
                f"is_valid={parsed.get('is_valid')} "
                f"tickers={parsed.get('tickers')} "
                f"years={parsed.get('years')} "
                f"sections={parsed.get('sections')} "
                f"sub_query_template={parsed.get('sub_query_template')!r} "
                f"rejection_reason={parsed.get('rejection_reason')!r}"
            )

        return parsed

    # -------------------------------------------------------------------
    # Private: Cartesian product of filter combinations
    # -------------------------------------------------------------------

    @staticmethod
    def _build_combinations(
        tickers:  list,
        years:    list,
        sections: list,
    ) -> list:
        """
        Generate every combination of filter values across the three dimensions.
        Each combination is a dict ready for use as a ChromaDB where clause.

        Empty lists are skipped — that dimension is left unconstrained.

        Examples:
            tickers=["AAPL","MSFT"], years=[2022], sections=["Item 1A"]
            → [{"ticker":"AAPL","year":2022,"section":"Item 1A"},
               {"ticker":"MSFT","year":2022,"section":"Item 1A"}]

            tickers=["AAPL"], years=[2020,2023], sections=[]
            → [{"ticker":"AAPL","year":2020},
               {"ticker":"AAPL","year":2023}]

            tickers=[], years=[], sections=[]
            → [{}]   ← one empty combo = pure semantic search, no where clause
        """
        dims = []
        if tickers:
            dims.append([("ticker",  t) for t in tickers])
        if years:
            dims.append([("year",    y) for y in years])
        if sections:
            dims.append([("section", s) for s in sections])

        if not dims:
            return [{}]  # no filters → single pure semantic query

        return [dict(combo) for combo in itertools.product(*dims)]

    # -------------------------------------------------------------------
    # Public: retrieve
    # -------------------------------------------------------------------

    @observe(name="retrieval")
    def retrieve(self, query: str, top_k: int = TOP_K, logger=None):
        """
        Full retrieval pipeline for a raw user query.

        Args:
            query:  natural language question from the user
            top_k:  results per filter combination (default: TOP_K from config)
            logger: optional logger from logger.py — pass None to disable logging

        Returns:
            dict  {"error": str}           — if query is invalid / off-topic
            list  of result dicts          — sorted by similarity_score descending

        Result dict schema:
            {
                "text":             str,    # chunk text
                "similarity_score": float,  # 1 - chromadb_distance, higher = better
                "chunk_id":         str,
                "ticker":           str,
                "year":             int,
                "section":          str,
                "company":          str,
                "section_name":     str,
                "filing_type":      str,
                "source_file":      str,
            }
        """
        if logger:
            logger.info(f"RETRIEVER | ENTER | query={query!r} top_k={top_k}")

        # ── Step 1: validate + extract filters ─────────────────────────
        filters = self._extract_filters(query, logger)
        print(f"\nQuery parser output:\n{json.dumps(filters, indent=2)}")

        if not filters.get("is_valid", True):
            reason = filters.get("rejection_reason") or "Query not answerable from SEC 10-K filings."
            if logger:
                logger.warning(f"RETRIEVER | EXIT | query rejected | reason={reason!r}")
            return {"error": reason}

        # ── Step 2: embed query with BGE instruction prefix ────────────
        prefixed_query  = BGE_QUERY_PREFIX + query
        query_embedding = self.model.encode(
            prefixed_query,
            normalize_embeddings=True,
        ).tolist()

        if logger:
            logger.info("RETRIEVER | query_embedded | model=BAAI/bge-base-en prefix=True vector_dim=768")

        # ── Step 3: build Cartesian product of filter combinations ─────
        combinations = self._build_combinations(
            filters.get("tickers",  []),
            filters.get("years",    []),
            filters.get("sections", []),
        )
        sub_query_template = filters.get("sub_query_template")
        print(f"\nFilter combinations ({len(combinations)}): {combinations}")
        if sub_query_template:
            print(f"Sub-query template: {sub_query_template}")

        if logger:
            logger.info(f"RETRIEVER | combinations | count={len(combinations)} combos={combinations}")

        # ── Step 4: one ChromaDB query per combination ─────────────────
        combo_results  = []
        seen_chunk_ids = set()

        for combo in combinations:
            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results":        top_k,
                "include":          ["documents", "metadatas", "distances"],
            }
            if combo:
                conditions = [{k: {"$eq": v}} for k, v in combo.items()]
                query_kwargs["where"] = (
                    conditions[0] if len(conditions) == 1
                    else {"$and": conditions}
                )

            if logger:
                logger.info(f"RETRIEVER | ChromaDB call | combo={combo} n_results={top_k}")

            chroma_result = self.collection.query(**query_kwargs)

            documents = chroma_result["documents"][0]
            metadatas = chroma_result["metadatas"][0]
            distances = chroma_result["distances"][0]
            ids       = chroma_result["ids"][0]

            if logger:
                logger.info(f"RETRIEVER | ChromaDB result | combo={combo} chunks_returned={len(documents)}")

            group = []
            for doc, meta, dist, chunk_id in zip(documents, metadatas, distances, ids):
                if chunk_id in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(chunk_id)

                group.append({
                    "text":             doc,
                    "similarity_score": round(1.0 - dist, 4),
                    "chunk_id":         chunk_id,
                    "ticker":           meta.get("ticker"),
                    "year":             meta.get("year"),
                    "section":          meta.get("section"),
                    "company":          meta.get("company"),
                    "section_name":     meta.get("section_name"),
                    "filing_type":      meta.get("filing_type"),
                    "source_file":      meta.get("source_file"),
                })

            combo_results.append((combo, group))

        # ── Step 5: rerank ────────────────────────────────────────────
        use_per_combo_rerank = (
            len(combinations) > 1
            and sub_query_template is not None
        )

        if use_per_combo_rerank:
            all_results = []
            for combo, group in combo_results:
                company = TICKER_TO_COMPANY.get(combo.get("ticker", ""), "")
                year = str(combo.get("year", ""))
                filled = sub_query_template.replace("<company>", company).replace("<year>", year)
                print(f"  Reranking combo {combo} with: {filled!r}")
                if logger:
                    logger.info(f"RETRIEVER | per-combo rerank | combo={combo} sub_query={filled!r}")
                reranked = self.reranker.rerank(filled, group, logger)
                for chunk in reranked:
                    chunk["group"] = filled
                all_results.extend(reranked)
        else:
            all_results = []
            for _, group in combo_results:
                all_results.extend(group)
            all_results = self.reranker.rerank(query, all_results, logger)
            for chunk in all_results:
                chunk["group"] = None

        if logger:
            logger.info(f"RETRIEVER | EXIT | total_chunks={len(all_results)} (after dedup + rerank)")

        return all_results


# -----------------------------------------------------------------------
# Script entry point — manual test on AAPL 2020
# -----------------------------------------------------------------------

if __name__ == "__main__":

    retriever = Retriever()

    test_queries = [
        # Fully specified — should filter to AAPL, 2020, Item 1A
        "What were Apple's main risk factors in 2020?",

        # Partially specified — should filter to AAPL only, no year or section
        "Describe Apple's business and products",

        # Multi-value — should produce 2 combinations: AAPL+2020, MSFT+2020
        "Compare Apple and Microsoft's risk factors in 2020",

        # Invalid — completely off-topic
        "What is the weather forecast for New York tomorrow?",
    ]

    for query in test_queries:
        print("\n" + "=" * 70)
        print(f"QUERY: {query}")
        print("=" * 70)

        results = retriever.retrieve(query, top_k=TOP_K)

        if isinstance(results, dict) and "error" in results:
            print(f"  REJECTED: {results['error']}")
            continue

        print(f"\n  Returned {len(results)} result(s)\n")
        for i, r in enumerate(results, 1):
            print(
                f"  [{i}] score={r['similarity_score']:.4f}  "
                f"{r['ticker']} {r['year']} | {r['section']} | {r['chunk_id']}"
            )
            print(f"       {r['text'][:220].strip()}...")
            print()
