"""
chunker.py
----------
Reads each _sections.json from data/processed/,
splits each section into overlapping sentence-aware chunks,
and saves chunk-level JSON to data/processed/{TICKER}_{YEAR}_chunks.json.

Chunking strategy: sentence-aware (regex on .!? boundaries), greedy packing.
Chosen over hard word-split because mid-sentence cuts degrade embedding quality.
See learning.md for full comparison of chunking strategies.

Parameters:
    CHUNK_SIZE  = 300 words
    OVERLAP     = 50 words
    MIN_CHUNK   = 50 words  (tail chunks below this are merged into previous)

Run from project root:
    python ingestion/chunker.py
"""

import os
import re
import json

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROCESSED_DATA_DIR = os.path.join("data", "processed")

CHUNK_SIZE = 300
OVERLAP    = 50
MIN_CHUNK  = 50

COMPANIES = {
    "Apple":     {"ticker": "AAPL"},
    "Microsoft": {"ticker": "MSFT"},
    "Amazon":    {"ticker": "AMZN"},
    "Google":    {"ticker": "GOOGL"},
    "Meta":      {"ticker": "META"},
}

YEARS = [2020, 2021, 2022, 2023, 2024]


# ---------------------------------------------------------------------------
# Core chunking logic
# ---------------------------------------------------------------------------

def split_into_sentences(text):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]


def chunk_section(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP, min_chunk=MIN_CHUNK):
    """
    Split section text into overlapping chunks using sentence-aware packing.

    1. Split text into sentences on .!? boundaries
    2. Greedily pack sentences until chunk_size words is reached
    3. Backtrack ~overlap words to find start of next chunk
    4. Merge any tail chunk below min_chunk words into the previous chunk
    """
    sentences = split_into_sentences(text)

    if not sentences:
        return []

    # If entire section is below chunk_size — return as single chunk
    total_words = sum(len(s.split()) for s in sentences)
    if total_words <= chunk_size:
        return [" ".join(sentences)]

    chunks = []
    i = 0

    while i < len(sentences):
        current_chunk = []
        current_word_count = 0

        j = i
        while j < len(sentences):
            sentence_words = len(sentences[j].split())
            if current_word_count + sentence_words > chunk_size and current_chunk:
                break
            current_chunk.append(sentences[j])
            current_word_count += sentence_words
            j += 1

        chunks.append(" ".join(current_chunk))

        if j == i:
            j = i + 1

        overlap_words = 0
        backtrack = j
        while backtrack > i + 1:
            overlap_words += len(sentences[backtrack - 1].split())
            if overlap_words >= overlap:
                break
            backtrack -= 1

        i = backtrack

    # Merge tiny tail chunks into the previous chunk
    while len(chunks) > 1 and len(chunks[-1].split()) < min_chunk:
        chunks[-2] = chunks[-2] + " " + chunks[-1]
        chunks.pop()

    return chunks


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def chunk_all():
    total   = 0
    success = 0
    skipped = 0
    failed  = 0

    for company, info in COMPANIES.items():
        ticker = info["ticker"]

        for year in YEARS:
            total += 1
            src_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_sections.json")
            out_path = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_chunks.json")

            print(f"\n{'='*55}")
            print(f"  {company} ({ticker}) — {year}")
            print(f"{'='*55}")

            if os.path.exists(out_path):
                print(f"  [SKIP] Already exists: {out_path}")
                skipped += 1
                continue

            if not os.path.exists(src_path):
                print(f"  [FAIL] Source not found: {src_path}")
                failed += 1
                continue

            try:
                with open(src_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                sections = data["sections"]
                all_chunks = []

                for section_name, section_text in sections.items():
                    chunks = chunk_section(section_text)
                    total_chunks = len(chunks)

                    for idx, chunk_text in enumerate(chunks):
                        chunk_id = (
                            f"{ticker}_{year}_"
                            f"{section_name.replace(' ', '_')}_"
                            f"chunk_{idx + 1:03d}"
                        )
                        all_chunks.append({
                            "chunk_id":     chunk_id,
                            "ticker":       ticker,
                            "year":         year,
                            "section":      section_name,
                            "chunk_index":  idx + 1,
                            "total_chunks": total_chunks,
                            "word_count":   len(chunk_text.split()),
                            "text":         chunk_text,
                        })

                    print(f"  {section_name}: {total_chunks} chunks")

                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(all_chunks, f, ensure_ascii=False, indent=2)

                print(f"  [OK] {len(all_chunks)} total chunks → {out_path}")
                success += 1

            except Exception as e:
                print(f"  [FAIL] {company} {year} — {e}")
                failed += 1

    print(f"\n{'='*55}")
    print(f"  CHUNK SUMMARY")
    print(f"{'='*55}")
    print(f"  Total    : {total}")
    print(f"  Success  : {success}")
    print(f"  Skipped  : {skipped}  (already chunked)")
    print(f"  Failed   : {failed}")
    print(f"{'='*55}")


if __name__ == "__main__":
    print("Starting chunker...")
    chunk_all()
