"""Ingestion pipeline (docs/v3/ingestion.md): PDF → pages → period → blocks → sections →
chunks → embeddings → Qdrant, plus the document catalog and a run report.

Rules (spec §6): idempotent (a re-run replaces a document's chunks); one bad file never stops
the run (skip + log); size and type checks before reading; no AI cost.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from filing_rag.config import Settings
from filing_rag.ingest.blocks import Block, body_font_size, join_continued, page_blocks
from filing_rag.ingest.catalog import (
    CatalogRow,
    DocInfo,
    DocumentError,
    check_pdf_file,
    file_checksum,
    load_document_list,
    resolve_pdf,
    write_catalog,
)
from filing_rag.ingest.chunker import Chunk, ChunkConfig, Chunker, Placed, TokenCounter
from filing_rag.ingest.embed import Embedder
from filing_rag.ingest.label_checks import check_labels, summarise
from filing_rag.ingest.labels import DocMeta
from filing_rag.ingest.layout import Page, read_pdf
from filing_rag.ingest.period import find_period
from filing_rag.ingest.sections import SectionTracker, is_toc_page
from filing_rag.ingest.store import QdrantStore

log = logging.getLogger(__name__)

Reader = Callable[[Path], list[Page]]
COVER_PAGES = 3
MIN_ITEMS = {"10-K": 5, "annual report": 5, "10-Q": 3, "8-K": 1}
OVERRIDES_FILE = "pdf_overrides.json"
INGEST_VERSION = "m2-tables"  # bump when the chunk or label logic changes (Q106: tables)


@dataclass
class DocResult:
    row: CatalogRow
    chunks: list[Chunk] = field(default_factory=list)
    label_flags: list[dict[str, Any]] = field(default_factory=list)


def unrecoverable_docs(settings: Settings) -> dict[str, str]:
    path = settings.eval_dir / OVERRIDES_FILE
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: str(v.get("reason", "")) for k, v in data.get("unrecoverable", {}).items()}


COLLECTION_FILE = "collection.txt"


class IngestDirMismatch(RuntimeError):
    pass


def check_ingest_dir(settings: Settings, collection: str) -> None:
    """One ingest folder belongs to one Qdrant collection (Q105).

    The folder holds the catalog, chunk files and report of its collection. The first run
    writes the collection name into the folder; a later run with another collection stops
    before it changes any file."""
    path = settings.ingest_dir / COLLECTION_FILE
    if path.exists():
        owner = path.read_text(encoding="utf-8").strip()
        if owner != collection:
            raise IngestDirMismatch(
                f"{settings.ingest_dir} belongs to collection {owner!r}, not {collection!r}; "
                "set FILING_RAG_INGEST_DIR_NAME to a folder for this collection"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(collection + "\n", encoding="utf-8")


def place_sections(doc_type: str, blocks: list[Block]) -> tuple[list[Placed], SectionTracker]:
    tracker = SectionTracker(doc_type)
    placed = []
    for b in blocks:
        if b.kind == "heading":
            tracker.update(b.text, b.level, b.page)
        placed.append(Placed(b, tracker.section, tracker.subsection, tracker.heading))
    return placed, tracker


def process_document(
    info: DocInfo,
    settings: Settings,
    count_tokens: TokenCounter,
    reader: Reader = read_pdf,
) -> DocResult:
    """Read and chunk one document. Never raises for a bad file: the row says why it skipped."""
    row = CatalogRow.from_info(info)
    path, source = resolve_pdf(settings, info.doc_name)
    row.source, row.pdf_path = source, path.as_posix()
    try:
        check_pdf_file(path, settings.max_pdf_bytes)
        row.sha256 = file_checksum(path)
        pages = reader(path)
    except DocumentError as e:
        return _skip(row, str(e))
    except Exception as e:  # noqa: BLE001 - any parser failure skips the file
        return _skip(row, f"{type(e).__name__}: {e}")
    row.pages = len(pages)
    if not any(p.lines for p in pages):
        return _skip(row, "no text layer (scanned?)")

    cover = pages if info.doc_type == "annual report" else pages[:COVER_PAGES]
    period = find_period(
        info.doc_type,
        info.doc_name,
        info.fiscal_year,
        "\n".join(ln.text for p in cover for ln in p.lines),
    )
    row.warnings.extend(period.warnings)
    row.list_fiscal_year = info.fiscal_year
    row.fiscal_year = period.fiscal_year
    row.fiscal_quarter = period.fiscal_quarter
    row.period_end = period.period_end.isoformat() if period.period_end else None
    row.report_date = period.report_date.isoformat() if period.report_date else None
    row.period_source = period.source

    row.toc_pages = [p.number for p in pages if is_toc_page([ln.text for ln in p.lines])]
    body = body_font_size(pages)
    blocks: list[Block] = []
    for p in pages:
        if p.number not in row.toc_pages:
            blocks.extend(page_blocks(p, body))
    blocks = join_continued(blocks)
    placed, tracker = place_sections(info.doc_type, blocks)
    items = tracker.items_found
    row.sections_found = len(items)
    row.rejected_headings = len(tracker.rejected)
    need = MIN_ITEMS.get(info.doc_type)
    if need and len(items) < need:
        row.warnings.append(f"few sections found ({len(items)} Items); page headings used")
    two_col = sum(p.two_column for p in pages)
    if two_col:
        row.warnings.append(f"{two_col} two-column pages read column by column")

    meta = DocMeta(
        doc_name=info.doc_name,
        company=info.company,
        doc_type=info.doc_type,
        fiscal_year=period.fiscal_year,
        list_fiscal_year=info.fiscal_year,
        fiscal_quarter=period.fiscal_quarter,
        period_end=period.period_end,
        report_date=period.report_date,
        period_source=period.source,
    )
    cfg = ChunkConfig(
        target=settings.chunk_target_tokens,
        max=settings.chunk_max_tokens,
        overlap=settings.chunk_overlap_tokens,
        label_depth=settings.label_depth,
    )
    chunks = Chunker(meta, count_tokens, cfg).run(placed)
    row.chunks = len(chunks)
    row.table_chunks = sum(c.is_table for c in chunks)
    flags = check_labels(info.doc_type, chunks)
    row.label_flags = {k: v["count"] for k, v in summarise(flags).items()}
    res_flags = flags
    row.status = "ok" if chunks else "skipped"
    if not chunks:
        row.error = "no chunks made"
    return DocResult(row, chunks, res_flags)


def _skip(row: CatalogRow, reason: str) -> DocResult:
    row.status, row.error = "skipped", reason
    log.warning("skipped %s: %s", row.doc_name, reason)
    return DocResult(row)


def write_chunks(settings: Settings, doc_name: str, chunks: list[Chunk]) -> None:
    """Chunks as JSONL for review (data/v3/chunks/<doc>.jsonl)."""
    out = settings.ingest_dir / "chunks"
    out.mkdir(parents=True, exist_ok=True)
    with (out / f"{doc_name}.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps({**c.payload(), "embed_text": c.embed_text}, ensure_ascii=False))
            f.write("\n")


def settings_fingerprint(settings: Settings) -> str:
    """Everything that changes the chunks or vectors. Bump INGEST_VERSION when the logic changes."""
    keys = {
        "version": INGEST_VERSION,
        "target": settings.chunk_target_tokens,
        "max": settings.chunk_max_tokens,
        "overlap": settings.chunk_overlap_tokens,
        "label_depth": settings.label_depth,
        "model": settings.embedding_model,
    }
    return hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()[:16]


def _read_catalog(settings: Settings) -> dict[str, dict[str, Any]]:
    path = settings.ingest_dir / "catalog.json"
    if not path.exists():
        return {}
    return {r["doc_name"]: r for r in json.loads(path.read_text(encoding="utf-8"))}


def _unchanged(
    settings: Settings,
    old: dict[str, Any] | None,
    fingerprint: str,
    store: QdrantStore | None,
) -> DocResult | None:
    """The saved result of a document when its PDF and the settings did not change, else None.

    Also checks that the chunk file exists and that Qdrant still holds the same number of
    points (a deleted collection is noticed)."""
    if not old or old.get("status") != "ok" or old.get("ingest_fingerprint") != fingerprint:
        return None
    name = old["doc_name"]
    path, _ = resolve_pdf(settings, name)
    chunk_file = settings.ingest_dir / "chunks" / f"{name}.jsonl"
    if not path.exists() or not chunk_file.exists() or file_checksum(path) != old.get("sha256"):
        return None
    if store is not None and store.count(name) != old.get("chunks"):
        return None
    chunks = [
        Chunk(**json.loads(x)) for x in chunk_file.read_text(encoding="utf-8").splitlines() if x
    ]
    row = CatalogRow(**old)
    return DocResult(row, chunks, check_labels(row.doc_type, chunks))


# ---------- worker processes (parallel reading) ----------
_worker_settings: Settings | None = None
_worker_count: TokenCounter | None = None


def _init_worker(settings: Settings) -> None:
    """Each worker loads only the tokenizer (to count tokens), not the embedding model."""
    global _worker_settings, _worker_count
    from transformers import AutoTokenizer

    logging.getLogger("transformers").setLevel(logging.ERROR)  # long texts are only counted
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    tok = AutoTokenizer.from_pretrained(settings.embedding_model)
    _worker_settings = settings

    def count(text: str) -> int:
        return len(tok(text, add_special_tokens=True, truncation=False)["input_ids"])

    _worker_count = count


def _work(info: DocInfo) -> DocResult:
    assert _worker_settings is not None and _worker_count is not None
    return process_document(info, _worker_settings, _worker_count)


def run(
    doc_names: list[str],
    settings: Settings,
    embedder: Embedder,
    store: QdrantStore | None,
    reader: Reader = read_pdf,
    workers: int = 0,
    force: bool = False,
) -> dict[str, Any]:
    """Ingest documents. `workers` > 1 reads PDFs in parallel processes (embedding and storing
    stay in this process, on the GPU). Progress is saved after each document; a document whose
    PDF and settings did not change is skipped unless `force`."""
    docs = load_document_list(settings)
    known_bad = unrecoverable_docs(settings)
    if store is not None:
        check_ingest_dir(settings, store.collection)
        store.ensure_collection()
    fingerprint = settings_fingerprint(settings)
    saved = _read_catalog(settings)
    rows: list[CatalogRow] = []
    all_chunks: list[Chunk] = []
    all_flags: list[dict[str, Any]] = []
    todo: list[DocInfo] = []
    total = len(doc_names)

    def record(res: DocResult, new: bool) -> None:
        name = res.row.doc_name
        if new:
            res.row.ingest_fingerprint = fingerprint
            if res.chunks:
                vectors = embedder.embed_documents([c.embed_text for c in res.chunks])
                if store is not None:
                    store.replace_document(name, res.chunks, vectors)
                write_chunks(settings, name, res.chunks)
            write_catalog(settings, [res.row])  # progress is saved after each document
        rows.append(res.row)
        all_chunks.extend(res.chunks)
        all_flags.extend({**f, "doc_name": name} for f in res.label_flags)
        log.info(
            "[%d/%d] %s: %s%s, %d pages, %d chunks (%d tables), %d Items",
            len(rows), total, name, res.row.status, "" if new else " (unchanged, skipped)",
            res.row.pages, res.row.chunks, res.row.table_chunks, res.row.sections_found,
        )  # fmt: skip

    for name in doc_names:
        info = docs.get(name)
        if info is None:
            log.error("not in the document list: %s", name)
            total -= 1
            continue
        if name in known_bad:
            record(_skip(CatalogRow.from_info(info), f"unrecoverable: {known_bad[name]}"), True)
            continue
        old = None if force else _unchanged(settings, saved.get(name), fingerprint, store)
        if old is not None:
            record(old, False)
        else:
            todo.append(info)

    if workers > 1 and todo:
        with ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(settings,)) as ex:
            futures = {ex.submit(_work, info): info for info in todo}
            for fut in as_completed(futures):
                try:
                    res = fut.result()
                except Exception as e:  # noqa: BLE001 - a crashed worker skips the file
                    row = CatalogRow.from_info(futures[fut])
                    res = _skip(row, f"worker failed: {type(e).__name__}: {e}")
                record(res, True)
    else:
        for info in todo:
            record(process_document(info, settings, embedder.count_tokens, reader), True)

    report = build_report(rows, all_chunks, settings.chunk_max_tokens)
    report["label_checks"] = summarise(all_flags)
    path = settings.ingest_dir / "report.json"
    path.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return report


def build_report(rows: list[CatalogRow], chunks: list[Chunk], max_tokens: int) -> dict[str, Any]:
    ids = Counter(c.chunk_id for c in chunks)
    tokens = sorted(c.n_tokens for c in chunks)
    return {
        "documents": len(rows),
        "ok": sum(r.status == "ok" for r in rows),
        "skipped": {r.doc_name: r.error for r in rows if r.status != "ok"},
        "chunks": len(chunks),
        "table_chunks": sum(c.is_table for c in chunks),
        "tokens": {
            "median": tokens[len(tokens) // 2] if tokens else 0,
            "max": tokens[-1] if tokens else 0,
            "over_limit": sum(t > max_tokens for t in tokens),
        },
        "checks": {
            "duplicate_chunk_ids": sum(1 for v in ids.values() if v > 1),
            "chunks_over_limit": sum(t > max_tokens for t in tokens),
            "chunks_without_period_date": sum(
                1 for c in chunks if not (c.period_end or c.report_date)
            ),
            "chunks_without_section": sum(1 for c in chunks if not c.section),
        },
        "per_document": {
            r.doc_name: {
                "status": r.status,
                "pages": r.pages,
                "chunks": r.chunks,
                "table_chunks": r.table_chunks,
                "items": r.sections_found,
                "period_end": r.period_end,
                "report_date": r.report_date,
                "period_source": r.period_source,
                "warnings": r.warnings,
                "rejected_headings": r.rejected_headings,
                "label_flags": r.label_flags,
            }
            for r in rows
        },
    }
