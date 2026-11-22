"""M1a step 5a: read all pages of the 5 test documents and make simple test chunks.

Same simple method for every model (the real chunk method is decided in M1b):
- page text = pdfplumber layout text (tables keep their column alignment);
- embed text = the same text with runs of spaces collapsed (alignment matters for reading,
  not for embedding);
- "small" chunks: about 280 words (~400 tokens) with a 40-word overlap, never across pages;
- "page" chunks: one chunk per page (variant: shows what input limits cut off).

Run: uv run python experiments/m1a/build_chunks.py
Writes: experiments/m1a/results/pages.json, chunks_small.json, chunks_page.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pdfplumber

from filing_rag.config import get_settings

HERE = Path(__file__).parent
RESULTS = HERE / "results"
CHUNK_WORDS = 280
OVERLAP_WORDS = 40


def collapse(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def split_words(text: str, size: int, overlap: int) -> list[str]:
    lines = text.splitlines()
    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for line in lines:
        n = len(line.split())
        if current and count + n > size:
            chunks.append("\n".join(current))
            tail: list[str] = []
            tail_count = 0
            for prev in reversed(current):  # keep whole lines for the overlap
                tail_count += len(prev.split())
                tail.insert(0, prev)
                if tail_count >= overlap:
                    break
            current, count = tail, tail_count
        current.append(line)
        count += n
    if current:
        chunks.append("\n".join(current))
    return chunks


def main() -> None:
    settings = get_settings()
    test_pages = json.loads((HERE / "test_pages.json").read_text(encoding="utf-8"))
    docs = sorted({p["doc_name"] for p in test_pages})
    pages: list[dict[str, Any]] = []
    for doc in docs:
        with pdfplumber.open(settings.pdf_dir / f"{doc}.pdf") as pdf:
            for i, page in enumerate(pdf.pages):
                layout = page.extract_text(layout=True) or ""
                pages.append({"doc_name": doc, "page_number": i + 1, "text": collapse(layout)})
        print(f"{doc}: {sum(p['doc_name'] == doc for p in pages)} pages")

    small: list[dict[str, Any]] = []
    page_chunks: list[dict[str, Any]] = []
    for p in pages:
        if not p["text"].strip():
            continue
        base = {"doc_name": p["doc_name"], "page_number": p["page_number"]}
        page_chunks.append(
            {**base, "chunk_id": f"{p['doc_name']}|{p['page_number']}", "text": p["text"]}
        )
        for j, text in enumerate(split_words(p["text"], CHUNK_WORDS, OVERLAP_WORDS)):
            small.append(
                {**base, "chunk_id": f"{p['doc_name']}|{p['page_number']}|{j}", "text": text}
            )

    RESULTS.mkdir(exist_ok=True)
    for name, data in [("pages", pages), ("chunks_small", small), ("chunks_page", page_chunks)]:
        (RESULTS / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
    words = [len(c["text"].split()) for c in page_chunks]
    print(f"pages={len(pages)} small_chunks={len(small)} page_chunks={len(page_chunks)}")
    print(f"words per page: median={sorted(words)[len(words) // 2]} max={max(words)}")


if __name__ == "__main__":
    main()
