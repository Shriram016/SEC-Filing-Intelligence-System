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
    path = _checked_locked_file(settings, manifest)

    entry = {
        "opened_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "milestone": milestone,
        "reason": reason,
        "git_commit": _git_commit(),
    }
    _register(settings, entry)
    return read_jsonl(path)


def _checked_locked_file(settings: Settings, manifest: dict[str, Any]) -> Path:
    path = locked_file(settings)
    if not path.exists():
        raise LockedSetError(
            f"{path} not found. After Q112 the file is kept outside the project: set "
            "FILING_RAG_LOCKED_VAULT_DIR to its folder for the final runs only."
        )
    if sha256_file(path) != manifest["sha256"]:
        raise LockedSetError("locked file changed since it was locked")
    return path


def _register(settings: Settings, entry: dict[str, Any]) -> None:
    with (settings.eval_dir / REGISTER_NAME).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------- Q112: label-only read + stratified split (50 FB-dev / 100 closed) ----------

ID_FIELD = "financebench_id"
# Only these fields leave `read_labels`. Never the question, answer, justification or evidence.
LABEL_FIELDS = ("question_type", "question_reasoning", "doc_type", "gics_sector", "doc_period",
                "company")  # fmt: skip
SPLIT_NAME = "locked_split.json"
SPLIT_SEED = 20261126
DEV_SIZE = 50


def read_labels(settings: Settings, *, allow: bool, reason: str) -> list[dict[str, Any]]:
    """The label fields of the 150 questions, plus `evidence_pages` (a count). On the register."""
    if not allow:
        raise LockedSetError("reading the locked labels needs allow=True (Q112 split only)")
    if not reason.strip():
        raise LockedSetError("a reason is required")
    manifest = json.loads((settings.eval_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    path = _checked_locked_file(settings, manifest)
    _register(settings, {"opened_at": datetime.now(UTC).isoformat(timespec="seconds"),
                         "milestone": "Q112-labels", "reason": reason,
                         "git_commit": _git_commit()})  # fmt: skip
    return [label_row(r) for r in read_jsonl(path)]


def label_row(row: dict[str, Any]) -> dict[str, Any]:
    """Keep the ID and the label fields only (missing label → None)."""
    out: dict[str, Any] = {ID_FIELD: str(row[ID_FIELD])}
    out |= {f: (None if row.get(f) is None else str(row.get(f))) for f in LABEL_FIELDS}
    out["evidence_pages"] = len(row.get("evidence") or [])
    return out


def _largest_remainder(counts: dict[str, int], total: int, size: int) -> dict[str, int]:
    exact = {k: n * size / total for k, n in counts.items()}
    share = {k: int(v) for k, v in exact.items()}
    left = size - sum(share.values())
    for k in sorted(exact, key=lambda k: (-(exact[k] - share[k]), k))[:left]:
        share[k] += 1
    return share


def stratified_split(
    rows: list[dict[str, Any]], size: int = DEV_SIZE, seed: int = SPLIT_SEED
) -> tuple[list[str], list[str]]:
    """(dev IDs, closed IDs). Per question type: a share of `size` by largest remainder. Inside
    a type: sort by the other labels, then take every n-th question from a seeded start, so the
    dev part keeps the mix of reasoning, doc type, evidence-page count, sector and period."""
    import random

    rng = random.Random(seed)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_type.setdefault(str(r.get("question_type")), []).append(r)
    share = _largest_remainder({k: len(v) for k, v in by_type.items()}, len(rows), size)
    dev: list[str] = []
    for qtype in sorted(by_type):
        group = sorted(by_type[qtype], key=lambda r: (
            str(r.get("question_reasoning")), str(r.get("doc_type")),
            r.get("evidence_pages", 0) > 1, str(r.get("gics_sector")), str(r.get("doc_period")),
            r[ID_FIELD]))  # fmt: skip
        n = share[qtype]
        if n == 0:
            continue
        step = len(group) / n
        start = rng.random() * step
        dev += [group[int(start + i * step)][ID_FIELD] for i in range(n)]
    dev_set = set(dev)
    closed = [r[ID_FIELD] for r in rows if r[ID_FIELD] not in dev_set]
    return sorted(dev), sorted(closed)


def label_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Counts per label value (no text)."""
    out: dict[str, dict[str, int]] = {}
    for f in (*LABEL_FIELDS, "evidence_pages"):
        c: dict[str, int] = {}
        for r in rows:
            c[str(r.get(f))] = c.get(str(r.get(f)), 0) + 1
        out[f] = dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))
    return out


def load_split(settings: Settings) -> dict[str, Any]:
    path = settings.eval_dir / SPLIT_NAME
    if not path.exists():
        raise LockedSetError(f"{path} not found; make the Q112 split first")
    return dict(json.loads(path.read_text(encoding="utf-8")))


def write_fb_dev(settings: Settings, *, allow: bool, reason: str) -> Path:
    """Copy the 50 FB-dev rows (full text) to `settings.fb_dev_file`, once. On the register.

    Only rows whose ID is in the split's `dev_ids` are written; the closed 100 are never
    returned or written."""
    if not allow:
        raise LockedSetError("writing the FB-dev file needs allow=True (Q112)")
    if not reason.strip():
        raise LockedSetError("a reason is required")
    out = settings.fb_dev_file
    if out.exists():
        raise LockedSetError(f"{out} exists; it is written once")
    dev_ids = set(load_split(settings)["dev_ids"])
    manifest = json.loads((settings.eval_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    path = _checked_locked_file(settings, manifest)
    rows = [r for r in read_jsonl(path) if str(r[ID_FIELD]) in dev_ids]
    if {str(r[ID_FIELD]) for r in rows} != dev_ids or len(rows) != len(dev_ids):
        raise LockedSetError("the FB-dev IDs do not match the locked file")
    _register(settings, {"opened_at": datetime.now(UTC).isoformat(timespec="seconds"),
                         "milestone": "Q112-fb-dev", "reason": reason,
                         "git_commit": _git_commit()})  # fmt: skip
    out.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    out.write_text(text, encoding="utf-8")
    return out


def load_fb_dev(settings: Settings) -> list[dict[str, Any]]:
    """The 50 FB-dev questions (open dev set, Q112). Reads only the FB-dev file."""
    path = settings.fb_dev_file
    if not path.exists():
        raise LockedSetError(f"{path} not found; run write_fb_dev once")
    rows = read_jsonl(path)
    dev_ids = set(load_split(settings)["dev_ids"])
    if {str(r[ID_FIELD]) for r in rows} != dev_ids:
        raise LockedSetError("the FB-dev file does not match the split")
    return rows
