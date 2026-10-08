"""
Test chunker logic on AAPL_2020 before scaling to all 25 filings.
Parameters: 300-word chunks, 50-word overlap, sentence-aware splitting.
Run from project root: python test_chunker.py
"""

import json
import re


CHUNK_SIZE = 300   # words
OVERLAP = 50       # words


def split_into_sentences(text):
    """Split text into sentences using regex on .!? boundaries."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]


def chunk_section(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    """
    Pack sentences greedily into chunks of ~chunk_size words.
    When a chunk is full, start the next chunk by backtracking
    overlap words worth of sentences from the end of the current chunk.
    """
    sentences = split_into_sentences(text)
    chunks = []
    i = 0

    while i < len(sentences):
        current_chunk = []
        current_word_count = 0

        # Pack sentences until we hit the word limit
        j = i
        while j < len(sentences):
            sentence_words = len(sentences[j].split())
            if current_word_count + sentence_words > chunk_size and current_chunk:
                break
            current_chunk.append(sentences[j])
            current_word_count += sentence_words
            j += 1

        chunks.append(" ".join(current_chunk))

        # If we didn't advance, force progress to avoid infinite loop
        if j == i:
            j = i + 1

        # Backtrack overlap: find how many sentences from the end
        # cover ~overlap words, and start next chunk from there
        overlap_words = 0
        backtrack = j
        while backtrack > i + 1:
            overlap_words += len(sentences[backtrack - 1].split())
            if overlap_words >= overlap:
                break
            backtrack -= 1

        i = backtrack

    # Merge tiny tail chunks into the previous chunk
    MIN_WORDS = 50
    while len(chunks) > 1 and len(chunks[-1].split()) < MIN_WORDS:
        chunks[-2] = chunks[-2] + " " + chunks[-1]
        chunks.pop()

    return chunks


def test_one_file(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ticker = data["ticker"]
    year = data["year"]
    sections = data["sections"]

    print(f"\n{'='*60}")
    print(f"  File: {ticker} {year}")
    print(f"{'='*60}")

    all_chunks = []

    for section_name, section_text in sections.items():
        word_count = len(section_text.split())
        chunks = chunk_section(section_text)

        print(f"\n--- {section_name} ---")
        print(f"  Section word count : {word_count}")
        print(f"  Chunks produced    : {len(chunks)}")

        for idx, chunk in enumerate(chunks):
            wc = len(chunk.split())
            chunk_id = f"{ticker}_{year}_{section_name.replace(' ', '_')}_chunk_{idx+1:03d}"
            all_chunks.append({
                "chunk_id": chunk_id,
                "ticker": ticker,
                "year": year,
                "section": section_name,
                "chunk_index": idx + 1,
                "total_chunks": len(chunks),
                "word_count": wc,
            })
            print(f"  Chunk {idx+1:03d} — {wc} words")

        # Preview first and last chunk text
        print(f"\n  [First chunk preview]")
        print(f"  {chunks[0][:300]}...")
        if len(chunks) > 1:
            print(f"\n  [Last chunk preview]")
            print(f"  {chunks[-1][:300]}...")

    print(f"\n{'='*60}")
    print(f"  Total chunks across all sections: {len(all_chunks)}")
    print(f"{'='*60}\n")

    return all_chunks


if __name__ == "__main__":
    test_one_file("data/processed/AAPL_2020_sections.json")
