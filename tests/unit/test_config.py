from pathlib import Path

import pytest

from filing_rag.config import Settings


def test_defaults_and_derived_paths() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.pdf_dir == Path("data/financebench/pdfs")
    assert s.locked_dir == Path("data/locked")
    assert len(s.financebench_commit) == 40
    assert s.ingest_dir == Path("data/v3_v2")
    assert s.qdrant_collection == "chunks_v2"  # Q106
    other = Settings(_env_file=None, ingest_dir_name="v3_chunks_v2")  # type: ignore[call-arg]
    assert other.ingest_dir == Path("data/v3_chunks_v2")


def test_env_overrides_and_secret_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILING_RAG_DATA_DIR", "/tmp/x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.data_dir == Path("/tmp/x")
    assert s.anthropic_api_key is not None
    assert "sk-test-123" not in repr(s)
    assert s.anthropic_api_key.get_secret_value() == "sk-test-123"
