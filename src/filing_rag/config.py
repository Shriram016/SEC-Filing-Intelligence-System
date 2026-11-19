"""Settings for filing_rag, read from environment variables or `.env`. Nothing is hard-coded."""

from functools import lru_cache
from pathlib import Path

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
    def locked_dir(self) -> Path:
        return self.data_dir / "locked"


@lru_cache
def get_settings() -> Settings:
    return Settings()
