"""Run ingestion.

    docker compose up -d qdrant
    uv run --group embed python -m filing_rag.ingest --docs-file experiments/m1b/documents.json
    uv run --group embed python -m filing_rag.ingest --all --workers 6

`--workers N` reads PDFs in N parallel processes. A document whose PDF and settings did not
change since the last run is skipped (progress is saved after each document); `--force`
does every document again.
`--no-store` makes chunks and embeddings but does not write to Qdrant (dry run).
`--label-depth none|section|full` sets the embedded label (Q99); for a test, use a
separate collection: FILING_RAG_QDRANT_COLLECTION=chunks_full.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from filing_rag.config import get_settings
from filing_rag.ingest.catalog import load_document_list
from filing_rag.ingest.embed import BgeEmbedder
from filing_rag.ingest.labels import LABEL_DEPTHS
from filing_rag.ingest.pipeline import run
from filing_rag.ingest.store import QdrantStore


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="filing_rag.ingest")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--docs-file", type=Path, help='JSON with {"documents": [{"doc_name": ...}]}')
    src.add_argument("--docs", nargs="+", help="document names")
    src.add_argument("--all", action="store_true", help="every document in the document list")
    ap.add_argument("--no-store", action="store_true", help="do not write to Qdrant")
    ap.add_argument("--workers", type=int, default=0, help="parallel PDF readers (0 = none)")
    ap.add_argument("--force", action="store_true", help="do not skip unchanged documents")
    ap.add_argument("--label-depth", choices=LABEL_DEPTHS, help="embedded label (Q99)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    s = get_settings()
    if args.label_depth:
        s = s.model_copy(update={"label_depth": args.label_depth})
    if args.all:
        names = list(load_document_list(s))
    elif args.docs_file:
        data = json.loads(args.docs_file.read_text(encoding="utf-8"))
        names = [d["doc_name"] for d in data["documents"]]
    else:
        names = list(args.docs)

    embedder = BgeEmbedder(s.embedding_model, s.embedding_query_prefix)
    store = None
    if not args.no_store:
        from qdrant_client import QdrantClient

        store = QdrantStore(
            QdrantClient(url=s.qdrant_url, timeout=s.qdrant_timeout_s),
            s.qdrant_collection,
            embedder.dim,
        )
    report = run(names, s, embedder, store, workers=args.workers, force=args.force)
    print(json.dumps({k: v for k, v in report.items() if k != "per_document"}, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
