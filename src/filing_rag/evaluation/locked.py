"""The locked benchmark: the 150 FinanceBench questions.

Rules (docs/v3/evaluation.md):
- Opened only at M3 and M6. Never used to tune anything.
- `lock()` runs once: it records the file checksum and the evidence pages (for the leakage guard).
- `open_locked()` refuses unless the caller passes `allow=True`, checks the checksum,
  and appends one line to the committed open register, so every opening is on record.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from filing_rag.config import Settings
from filing_rag.data.financebench import QUESTIONS_FILENAME, read_jsonl, sha256_file

EXPECTED_COUNT = 150
MANIFEST_NAME = "locked_manifest.json"
REGISTER_NAME = "locked_register.jsonl"
EVIDENCE_PAGES_NAME = "locked_evidence_pages.json"
ALLOWED_MILESTONES = ("M3", "M6")


class LockedSetError(RuntimeError):
    """Raised when the locked set is opened without permission or has changed."""


def locked_file(settings: Settings) -> Path:
    return settings.locked_dir / QUESTIONS_FILENAME


def evidence_pages(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unique (doc_name, page) pairs used as evidence by the locked questions."""
    pairs: set[tuple[str, int]] = set()
    for row in rows:
        for ev in row.get("evidence", []):
            pairs.add((str(ev["doc_name"]), int(ev["evidence_page_num"])))
    return [{"doc_name": d, "page": p} for d, p in sorted(pairs)]


def lock(settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    """Record checksum + evidence pages. Re-running is safe only if the file is unchanged."""
    path = locked_file(settings)
    if not path.exists():
        raise LockedSetError(f"{path} not found. Run the download first.")
    rows = read_jsonl(path)
    if len(rows) != EXPECTED_COUNT:
        raise LockedSetError(f"expected {EXPECTED_COUNT} questions, found {len(rows)}")

    digest = sha256_file(path)
    manifest_path = settings.eval_dir / MANIFEST_NAME
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing["sha256"] != digest:
            raise LockedSetError("locked file differs from the manifest; refusing to re-lock")
        return dict(existing)

    manifest = {
        "file": f"{settings.locked_dir.name}/{QUESTIONS_FILENAME}",
        "sha256": digest,
        "count": len(rows),
        "source_commit": settings.financebench_commit,
        "locked_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "allowed_milestones": list(ALLOWED_MILESTONES),
    }
    settings.eval_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (settings.eval_dir / EVIDENCE_PAGES_NAME).write_text(
        json.dumps(evidence_pages(rows), indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def load_locked_evidence_pages(settings: Settings) -> set[tuple[str, int]]:
    """Leakage guard input: pages that tools and prompts must never be chosen on (Q21)."""
    path = settings.eval_dir / EVIDENCE_PAGES_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(str(x["doc_name"]), int(x["page"])) for x in data}


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def open_locked(
    settings: Settings,
    *,
    allow: bool,
    milestone: str,
    reason: str,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if not allow:
        raise LockedSetError("the locked set is closed; pass allow=True at M3/M6 only")
    if milestone not in ALLOWED_MILESTONES:
        raise LockedSetError(f"milestone must be one of {ALLOWED_MILESTONES}, got {milestone!r}")
    if not reason.strip():
        raise LockedSetError("a reason is required")

    manifest_path = settings.eval_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise LockedSetError("no lock manifest; run lock() first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    path = locked_file(settings)
    if sha256_file(path) != manifest["sha256"]:
        raise LockedSetError("locked file changed since it was locked")

    entry = {
        "opened_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "milestone": milestone,
        "reason": reason,
        "git_commit": _git_commit(),
    }
    with (settings.eval_dir / REGISTER_NAME).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return read_jsonl(path)
