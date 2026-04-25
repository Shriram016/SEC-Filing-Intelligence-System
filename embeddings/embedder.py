import json
import os
import sys
from pathlib import Path

from sentence_transformers import SentenceTransformer

sys.path.append(str(Path(__file__).parent.parent))
from config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
    PROCESSED_DATA_DIR,
    TICKERS,
    YEARS,
)


def load_chunks(tagged_path):
    with open(tagged_path, "r", encoding="utf-8") as f:
        return json.load(f)


def embed_chunks(model, chunks):
    texts = [chunk["text"] for chunk in chunks]
    embeddings = model.encode(
        texts,
        batch_size=EMBEDDING_BATCH_SIZE,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding.tolist()
    return chunks


def save_embedded(chunks, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f)


def main():
    print(f"Loading model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("Model loaded.\n")

    total_chunks = 0
    files_embedded = 0
    files_skipped = 0

    for ticker in TICKERS:
        for year in YEARS:
            tagged_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_tagged.json")
            output_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_embedded.json")

            if not os.path.exists(tagged_path):
                print(f"  MISSING: {ticker}_{year}_tagged.json — skipping")
                continue

            if os.path.exists(output_path):
                print(f"  SKIP: {ticker}_{year}_embedded.json already exists")
                files_skipped += 1
                continue

            chunks = load_chunks(tagged_path)
            print(f"  Embedding {ticker}_{year}... ({len(chunks)} chunks)", end="", flush=True)

            chunks = embed_chunks(model, chunks)
            save_embedded(chunks, output_path)

            total_chunks += len(chunks)
            files_embedded += 1
            print(" done")

    print(f"\nFinished.")
    print(f"  Files embedded : {files_embedded}")
    print(f"  Files skipped  : {files_skipped}")
    print(f"  Total chunks   : {total_chunks}")


if __name__ == "__main__":
    main()
