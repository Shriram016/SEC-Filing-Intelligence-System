"""Download the FinanceBench corpus (PDFs + document list) and the 150 questions.

The questions go straight to the locked folder; see `filing_rag.evaluation.locked`.
Every file gets a sha256 checksum in a committed manifest, so a later download can be verified.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from filing_rag.config import Settings

log = logging.getLogger(__name__)

DOC_INFO_PATH = "data/financebench_document_information.jsonl"
QUESTIONS_PATH = "data/financebench_open_source.jsonl"
QUESTIONS_FILENAME = "financebench_open_source.jsonl"
DOC_INFO_FILENAME = "document_information.jsonl"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def raw_url(settings: Settings, repo_path: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{settings.financebench_repo}/"
        f"{settings.financebench_commit}/{repo_path}"
    )


def unique_doc_names(rows: Iterable[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Return (unique doc names in first-seen order, names that appeared more than once)."""
    seen: set[str] = set()
    unique: list[str] = []
    dupes: list[str] = []
    for row in rows:
        name = str(row["doc_name"])
        if name in seen:
            dupes.append(name)
            continue
        seen.add(name)
        unique.append(name)
    return unique, dupes


def needs_download(dest: Path, expected_sha256: str | None) -> bool:
    """A file is downloaded when it is missing, or when it differs from the manifest checksum."""
    if not dest.exists():
        return True
    if expected_sha256 is None:
        return False
    return sha256_file(dest) != expected_sha256


def download_file(client: httpx.Client, url: str, dest: Path) -> None:
    """Stream to a temp file, then rename, so a crash never leaves a half-written file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    tmp.replace(dest)


@dataclass
class DownloadReport:
    downloaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    duplicate_doc_names: list[str] = field(default_factory=list)


def load_manifest(path: Path) -> dict[str, Any]:
    if path.exists():
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data
    return {"files": {}}


def build_manifest(settings: Settings, files: dict[str, Path]) -> dict[str, Any]:
    """`files` maps a stable key (for example `pdfs/3M_2018_10K.pdf`) to the local path."""
    return {
        "source": f"https://github.com/{settings.financebench_repo}",
        "commit": settings.financebench_commit,
        "files": {
            key: {"sha256": sha256_file(p), "bytes": p.stat().st_size}
            for key, p in sorted(files.items())
            if p.exists()
        },
    }


def download_financebench(
    settings: Settings, client: httpx.Client, manifest_path: Path
) -> DownloadReport:
    report = DownloadReport()
    previous = load_manifest(manifest_path)
    old: dict[str, Any] = previous.get("files", {})
    if previous.get("commit") not in (None, settings.financebench_commit):
        old = {}  # a different source commit: do not trust old checksums

    targets: dict[str, tuple[str, Path]] = {
        f"data/{DOC_INFO_FILENAME}": (DOC_INFO_PATH, settings.financebench_dir / DOC_INFO_FILENAME),
        f"locked/{QUESTIONS_FILENAME}": (QUESTIONS_PATH, settings.locked_dir / QUESTIONS_FILENAME),
    }

    # The document list decides which PDFs belong to the corpus.
    for key, (repo_path, dest) in targets.items():
        _fetch(client, settings, key, repo_path, dest, old, report)
    doc_info = settings.financebench_dir / DOC_INFO_FILENAME
    if not doc_info.exists():
        return report

    names, report.duplicate_doc_names = unique_doc_names(read_jsonl(doc_info))
    for name in names:
        key = f"pdfs/{name}.pdf"
        targets[key] = (key, settings.pdf_dir / f"{name}.pdf")
        _fetch(client, settings, key, key, settings.pdf_dir / f"{name}.pdf", old, report)

    manifest = build_manifest(settings, {k: dest for k, (_, dest) in targets.items()})
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return report


def _fetch(
    client: httpx.Client,
    settings: Settings,
    key: str,
    repo_path: str,
    dest: Path,
    old: dict[str, Any],
    report: DownloadReport,
) -> None:
    expected = old.get(key, {}).get("sha256")
    if not needs_download(dest, expected):
        report.skipped.append(key)
        return
    try:
        download_file(client, raw_url(settings, repo_path), dest)
        report.downloaded.append(key)
        log.info("downloaded %s", key)
    except httpx.HTTPError as exc:  # one bad file never stops the run
        report.failed[key] = str(exc)
        log.warning("failed %s: %s", key, exc)
