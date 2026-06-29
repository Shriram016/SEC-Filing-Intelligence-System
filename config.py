# Paths
RAW_DATA_DIR = "data/raw"
PROCESSED_DATA_DIR = "data/processed"
CHROMA_PERSIST_DIR = "chroma_db"

# Embedding model
EMBEDDING_MODEL = "BAAI/bge-base-en"
EMBEDDING_BATCH_SIZE = 32
EMBEDDING_DIMENSION = 768

# LLM
GROQ_MODEL     = "meta-llama/llama-4-scout-17b-16e-instruct"  # Q&A pipeline — query parsing, synthesis, scoring.
CONFLICT_MODEL = "llama-3.3-70b-versatile" # Conflict analysis — nuanced reasoning over long legal text. Quality matters.

# Retrieval
TOP_K = 10                      # results per filter combination
RERANKER_MODEL = "BAAI/bge-reranker-base"
MAX_CONTEXT_CHUNKS = 30

# Conflict detection
SIMILARITY_THRESHOLD = 0.85     # TBD — tune after retrieval is validated

# Confidence scoring
RETRIEVAL_WEIGHT = 0.4          # TBD — tune after faithfulness judge is built
FAITHFULNESS_WEIGHT = 0.6       # TBD

# Dataset
COMPANIES = ["Apple", "Microsoft", "Amazon", "Google", "Meta"]
TICKERS = ["AAPL", "MSFT", "AMZN", "GOOGL", "META"]
YEARS = [2020, 2021, 2022, 2023, 2024]

# SEC sections targeted across all filings
TARGET_SECTIONS = {
    "Item 1":  "Business",
    "Item 1A": "Risk Factors",
    "Item 7":  "MD&A",
    "Item 7A": "Market Risk",
}

# BGE query instruction prefix — prepend to queries at retrieval time, not at indexing time
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
