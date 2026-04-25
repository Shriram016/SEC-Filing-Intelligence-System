import json
import os
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

sys.path.append(str(Path(__file__).parent.parent))
from config import (
    BGE_QUERY_PREFIX,
    CHROMA_PERSIST_DIR,
    EMBEDDING_MODEL,
    PROCESSED_DATA_DIR,
    TICKERS,
    YEARS,
)

COLLECTION_NAME = "sec_filings"


def load_embedded(ticker, year):
    path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_embedded.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def index_chunks(collection, chunks):
    ids        = [c["chunk_id"] for c in chunks]
    embeddings = [c["embedding"] for c in chunks]
    documents  = [c["text"] for c in chunks]
    metadatas  = [
        {
            "ticker":       c["ticker"],
            "year":         c["year"],
            "section":      c["section"],
            "chunk_index":  c["chunk_index"],
            "total_chunks": c["total_chunks"],
            "word_count":   c["word_count"],
            "company":      c["company"],
            "section_name": c["section_name"],
            "filing_type":  c["filing_type"],
            "source_file":  c["source_file"],
        }
        for c in chunks
    ]
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )


def main():
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    total_indexed = 0
    for ticker in TICKERS:
        for year in YEARS:
            embedded_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_embedded.json")
            if not os.path.exists(embedded_path):
                print(f"  MISSING: {ticker}_{year}_embedded.json — skipping")
                continue

            chunks = load_embedded(ticker, year)
            print(f"  Indexing {ticker}_{year}... ({len(chunks)} chunks)", end="", flush=True)
            index_chunks(collection, chunks)
            total_indexed += len(chunks)
            print(" done")

    print(f"\nIndexing complete.")
    print(f"  Total chunks indexed : {total_indexed}")
    print(f"  Collection count     : {collection.count()}")

    # sanity search — embed query with BGE, pass vector to ChromaDB
    model = SentenceTransformer(EMBEDDING_MODEL)
    query = BGE_QUERY_PREFIX + "risk factors supply chain"
    query_vector = model.encode(query, normalize_embeddings=True).tolist()

    print("\nSanity search — 'risk factors supply chain':")
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=3,
        include=["documents", "metadatas", "distances"],
    )
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )):
        print(f"\n  Result {i+1}")
        print(f"  Company : {meta['company']} | Year: {meta['year']} | Section: {meta['section_name']}")
        print(f"  Distance: {dist:.4f}")
        print(f"  Text    : {doc[:120]}...")


if __name__ == "__main__":
    main()
