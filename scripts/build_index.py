"""
scripts/build_index.py

Build everything from scratch: download -> parse -> sections -> chunks -> tags -> embeddings -> index.

    python scripts/build_index.py                  # all steps (about 10-15 min on a fresh checkout)
    python scripts/build_index.py --start-at embed # resume from a later step

Each step skips work whose output file already exists, so re-running is safe.
The steps print "FAIL" instead of raising, so after every step this script checks that
all expected output files exist and stops with a clear message if any are missing.
"""

import argparse
import importlib
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)  # the pipeline uses paths relative to the project root
sys.path.insert(0, ROOT)

from config import CHROMA_PERSIST_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR, TICKERS, YEARS

# (name, module, function, folder with the outputs, output file suffix)
STEPS = [
    ("download", "ingestion.downloader",        "download_all", RAW_DATA_DIR,       ".htm"),
    ("parse",    "ingestion.parser",            "parse_all",    PROCESSED_DATA_DIR, "_parsed.json"),
    ("sections", "ingestion.section_detector",  "detect_all",   PROCESSED_DATA_DIR, "_sections.json"),
    ("chunk",    "ingestion.chunker",           "chunk_all",    PROCESSED_DATA_DIR, "_chunks.json"),
    ("tag",      "ingestion.metadata_tagger",   "tag_all",      PROCESSED_DATA_DIR, "_tagged.json"),
    ("embed",    "embeddings.embedder",         "main",         PROCESSED_DATA_DIR, "_embedded.json"),
    ("index",    "embeddings.indexer",          "main",         None,               None),
]


def missing_outputs(folder: str, suffix: str) -> list[str]:
    expected = [os.path.join(folder, f"{t}_{y}{suffix}") for t in TICKERS for y in YEARS]
    return [path for path in expected if not os.path.exists(path)]


def indexed_chunk_count() -> int:
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return client.get_collection("sec_filings").count()


def main() -> None:
    names = [step[0] for step in STEPS]
    parser = argparse.ArgumentParser(description="Build the SEC filing index from scratch.")
    parser.add_argument("--start-at", choices=names, default=names[0], help="resume from this step")
    args = parser.parse_args()

    for name, module, func, folder, suffix in STEPS[names.index(args.start_at):]:
        print(f"\n{'#' * 60}\n# STEP: {name}\n{'#' * 60}")
        started = time.time()
        getattr(importlib.import_module(module), func)()

        if folder:
            missing = missing_outputs(folder, suffix)
            if missing:
                sys.exit(f"\nSTOPPED after '{name}': {len(missing)} expected file(s) missing, e.g. {missing[0]}")
        else:
            count = indexed_chunk_count()
            if count == 0:
                sys.exit(f"\nSTOPPED after '{name}': the Chroma collection is empty")
            print(f"  Chroma collection 'sec_filings' holds {count:,} chunks")

        print(f"  Step '{name}' finished in {time.time() - started:.0f}s")

    print("\nBuild complete.")


if __name__ == "__main__":
    main()
