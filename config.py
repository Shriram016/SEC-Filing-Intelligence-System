# Paths
RAW_DATA_DIR = "data/raw"
PROCESSED_DATA_DIR = "data/processed"
CHROMA_PERSIST_DIR = "chroma_db"

# Embedding model
EMBEDDING_MODEL = "BAAI/bge-base-en"
EMBEDDING_BATCH_SIZE = 32
EMBEDDING_DIMENSION = 768

# LLM
# Groq retired llama-4-scout-17b and llama-3.3-70b-versatile (found 2026-10-13); replacements below.
# qwen3.8-27b is the only candidate that works as a drop-in (gpt-oss models spend the small token
# limits on reasoning and return empty/truncated output without code changes).
GROQ_MODEL     = "qwen/qwen3.8-27b"   # Q&A pipeline — query parsing, synthesis, scoring.
CONFLICT_MODEL = "qwen/qwen3.8-27b"   # Conflict analysis. Placeholder: NOT re-validated after the model change.
JUDGE_MODEL    = "openai/gpt-oss-120b"  # RAGAS eval judge. Different family from the pipeline model.

# Answer style for the synthesizer. "concise" adds a length/format instruction to the system prompt;
# "free" is the original prompt with no format guidance (kept so before/after runs can be compared).
ANSWER_STYLE = "concise"

# Groq prices in USD per 1M tokens (input, output), used by the evaluator to report run cost.
# Source: console.groq.com/docs/models. Check again before trusting the totals.
PRICES_PER_M_TOKENS = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "qwen/qwen3.8-27b":    (0.80, 4.00),
}
PRICES_CHECKED = "2026-10-13"

# Retrieval
TOP_K = 10                      # results per filter combination
RERANKER_MODEL = "BAAI/bge-reranker-base"
MAX_CONTEXT_CHUNKS = 30

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
