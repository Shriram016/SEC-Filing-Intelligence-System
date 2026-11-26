"""Settings for filing_rag, read from environment variables or `.env`. Nothing is hard-coded."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FILING_RAG_", extra="ignore")

    # Paths
    data_dir: Path = Path("data")
    eval_dir: Path = Path("eval")  # committed eval metadata: lock manifest, register, dev set

    # FinanceBench source, pinned to one commit so downloads are reproducible
    financebench_repo: str = "patronus-ai/financebench"
    financebench_commit: str = "cc39aeb4afdf33909ee1412188bf89035950c2eb"
    http_user_agent: str = "filing-rag/0.1 (portfolio project)"
    http_timeout_s: float = 120.0

    # Ingestion (docs/v3/ingestion.md)
    qdrant_url: str = "http://localhost:6333"
    # Q106 (2026-11-22): chunks_v2 = fixed table reader; the old "chunks" (folder "v3")
    # is kept for rollback: set both settings back together.
    qdrant_collection: str = "chunks_v2"
    qdrant_timeout_s: int = 60
    # Folder under data_dir for the catalog, chunk files and report of `qdrant_collection`.
    # Each collection has its own folder, so a test or new collection never overwrites the
    # files of another one (the router catalog and the skip rule read them).
    ingest_dir_name: str = "v3_v2"
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_query_prefix: str = "Represent this sentence for searching relevant passages: "
    chunk_target_tokens: int = 350
    chunk_max_tokens: int = 480  # bge-base reads 512 tokens; keep room
    chunk_overlap_tokens: int = 50
    label_depth: Literal["none", "section", "full"] = "section"  # Q99
    max_pdf_bytes: int = 100_000_000

    # Answer model (docs/v3/engine.md §5, ADR-0005). Prices in USD per 1M tokens.
    answer_model: str = "claude-sonnet-5-5"
    answer_price_in_per_mtok: float = 2.0
    answer_price_out_per_mtok: float = 10.0
    answer_max_tokens: int = 1024
    checked_max_tokens: int = 2048  # Q107: claims with quotes are longer than the baseline answer
    # Sonnet 5.5: "between_tools" is the lowest thinking setting (no extended thinking);
    # "disabled" is rejected on this model. None = do not send the field.
    answer_thinking: str | None = "between_tools"
    answer_effort: str | None = None  # None = do not send (API default)

    # Router model (docs/v3/router.md, Q34). Haiku 5.5: adaptive thinking only (on by default;
    # "between_tools" is rejected); effort is the lever. Thinking counts toward max_tokens.
    # Prices: $0.10/$0.50 per 1M tokens for prompts up to 100K tokens (checked 2026-11-21).
    router_model: str = "claude-haiku-5-5"
    router_price_in_per_mtok: float = 0.10
    router_price_out_per_mtok: float = 0.50
    router_max_tokens: int = 2048
    router_thinking: str | None = None
    router_effort: str | None = "low"
    router_year_rule: Literal["A", "B"] = "A"  # Q104: Y else Y+1 (A) or always Y and Y+1 (B)

    # Plain-RAG baseline (docs/v3/evaluation.md §3)
    baseline_top_k: int = 5
    table_parts_max_extra: int = 3  # Q105: parts of a split table added after the search
    # Reranker (Q111): a local cross-encoder sorts `reranker_candidates` search results per
    # step and keeps the best top_k. On by default (user decision 2026-11-26, Q111);
    # FILING_RAG_RERANKER_MODEL="" turns it off (for example a server without a GPU: about
    # 1 s per step on the RTX 3060, much slower on a CPU). Used by the routed engine only
    # (the M1 baseline stays frozen).
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_candidates: int = 100
    reranker_max_length: int = 512
    reranker_batch_size: int = 32
    baseline_max_cost_usd: float = 2.0  # a run stops when its cost goes above this

    # API service (docs/v3/api.md, Q108). M2 guards; full rate limits come in M5.
    # The server makes real (paid) LLM calls only when allow_paid is true; else demo mode.
    allow_paid: bool = False
    api_max_question_chars: int = 1000
    api_max_turn_chars: int = 2000
    api_max_history_turns: int = 6
    api_max_concurrent: int = 2  # questions at the same time; more gives HTTP 503
    api_timeout_s: float = 60.0  # total time per question
    api_daily_cost_cap_usd: float = 1.0  # in memory (one process); M5: shared store
    api_retry_after_s: int = 5

    # Q112: the file of the 150 locked questions lives outside the project after the split.
    # Set FILING_RAG_LOCKED_VAULT_DIR only for the final (closed 100) runs.
    locked_vault_dir: Path | None = None

    # API keys: optional until the components that need them exist. Read without the prefix.
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")

    @property
    def financebench_dir(self) -> Path:
        return self.data_dir / "financebench"

    @property
    def pdf_dir(self) -> Path:
        return self.financebench_dir / "pdfs"

    @property
    def pdf_override_dir(self) -> Path:
        return self.financebench_dir / "pdf_overrides"

    @property
    def ingest_dir(self) -> Path:
        return self.data_dir / self.ingest_dir_name

    @property
    def locked_dir(self) -> Path:
        return self.locked_vault_dir or self.data_dir / "locked"

    @property
    def fb_dev_file(self) -> Path:
        """Q112: the 50 FB-dev questions (full rows), copied once from the locked file."""
        return self.data_dir / "fb_dev" / "fb_dev_50.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
