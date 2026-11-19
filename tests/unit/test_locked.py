import json
from datetime import UTC, datetime

import pytest

from filing_rag.config import Settings
from filing_rag.evaluation.locked import (
    REGISTER_NAME,
    LockedSetError,
    load_locked_evidence_pages,
    lock,
    locked_file,
    open_locked,
)

NOW = datetime(2026, 11, 19, tzinfo=UTC)


def _write_questions(settings: Settings, n: int = 150) -> None:
    rows = [
        {
            "financebench_id": f"q{i}",
            "question": "?",
            "evidence": [{"doc_name": f"DOC_{i % 3}", "evidence_page_num": str(i % 5)}],
        }
        for i in range(n)
    ]
    p = locked_file(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_lock_writes_manifest_and_evidence_pages(settings: Settings) -> None:
    _write_questions(settings)
    m = lock(settings, now=NOW)
    assert m["count"] == 150
    assert len(m["sha256"]) == 64
    pages = load_locked_evidence_pages(settings)
    assert ("DOC_0", 0) in pages
    assert len(pages) == 15


def test_lock_rejects_wrong_count(settings: Settings) -> None:
    _write_questions(settings, n=149)
    with pytest.raises(LockedSetError, match="expected 150"):
        lock(settings)


def test_relock_same_file_is_safe_changed_file_refused(settings: Settings) -> None:
    _write_questions(settings)
    first = lock(settings, now=NOW)
    assert lock(settings) == first
    with locked_file(settings).open("a") as f:
        f.write("\n")
    with pytest.raises(LockedSetError, match="refusing to re-lock"):
        lock(settings)


@pytest.mark.parametrize(
    ("allow", "milestone", "reason", "msg"),
    [
        (False, "M3", "run 1", "closed"),
        (True, "M2", "run 1", "milestone"),
        (True, "M3", "  ", "reason"),
    ],
)
def test_open_refused(
    settings: Settings, allow: bool, milestone: str, reason: str, msg: str
) -> None:
    _write_questions(settings)
    lock(settings, now=NOW)
    with pytest.raises(LockedSetError, match=msg):
        open_locked(settings, allow=allow, milestone=milestone, reason=reason)
    assert not (settings.eval_dir / REGISTER_NAME).exists()


def test_open_records_every_opening(settings: Settings) -> None:
    _write_questions(settings)
    lock(settings, now=NOW)
    rows = open_locked(settings, allow=True, milestone="M3", reason="locked run 1", now=NOW)
    open_locked(settings, allow=True, milestone="M6", reason="locked run 2", now=NOW)
    assert len(rows) == 150
    lines = (settings.eval_dir / REGISTER_NAME).read_text().splitlines()
    assert [json.loads(x)["milestone"] for x in lines] == ["M3", "M6"]


def test_open_refuses_changed_file(settings: Settings) -> None:
    _write_questions(settings)
    lock(settings, now=NOW)
    locked_file(settings).write_text("tampered\n")
    with pytest.raises(LockedSetError, match="changed"):
        open_locked(settings, allow=True, milestone="M3", reason="x")
