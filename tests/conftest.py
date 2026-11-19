from pathlib import Path

import pytest

from filing_rag.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", eval_dir=tmp_path / "eval", _env_file=None)  # type: ignore[call-arg]
