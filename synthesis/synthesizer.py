"""
synthesis/synthesizer.py

Component 10 — Answer synthesis from retrieved chunks.

Responsibilities:
  1. Accept a user query + list of retrieved chunks (from retriever.retrieve())
  2. Select top-N chunks by similarity score (cap at MAX_CONTEXT_CHUNKS)
  3. Assemble a numbered context window with source labels
  4. Call Groq API (temperature=0) with a strict grounded-answer prompt
  5. Return structured output: answer + sources + metadata

Input:
    query  (str)   — raw user question
    chunks (list)  — result dicts from Retriever.retrieve(), sorted by similarity desc

Output dict:
    {
        "query":          str,
        "answer":         str,
        "sources":        list[dict],   # chunks sent to LLM, similarity_score included
        "model_used":     str,
        "context_chunks": int
    }

Run from project root:
    python synthesis/synthesizer.py
"""

import os
import sys

from dotenv import load_dotenv
from groq import Groq

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GROQ_MODEL

load_dotenv()

MAX_CONTEXT_CHUNKS = 10

SYSTEM_PROMPT = (
    "You are a financial analyst assistant specialising in SEC 10-K filings. "
    "Answer the question strictly from the provided filing excerpts. "
    "If the answer is not contained in the excerpts, say exactly: "
    "\"The provided context does not contain enough information to answer this question.\" "
    "Do not use any knowledge outside the provided passages."
)


class Synthesizer:

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not found. "
                "Create a .env file at project root with: GROQ_API_KEY=your_key"
            )
        self.groq_client = Groq(api_key=api_key)
        print("Synthesizer ready.\n")

    # ------------------------------------------------------------------
    # Private: build the user-facing prompt from chunks
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context(chunks: list) -> str:
        lines = ["Context passages:\n"]
        for i, chunk in enumerate(chunks, 1):
            label = (
                f"[{i}] {chunk.get('company', chunk.get('ticker'))} | "
                f"{chunk.get('year')} | "
                f"{chunk.get('section_name', chunk.get('section'))}"
            )
            lines.append(label)
            lines.append(f"\"{chunk['text'].strip()}\"\n")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public: synthesize
    # ------------------------------------------------------------------

    def synthesize(self, query: str, chunks: list, max_context: int = MAX_CONTEXT_CHUNKS, logger=None) -> dict:
        """
        Generate a grounded answer from retrieved chunks.

        Args:
            query:       raw user question
            chunks:      list of result dicts from Retriever.retrieve()
            max_context: max chunks to include in the LLM context window
            logger:      optional logger from logger.py — pass None to disable logging

        Returns:
            {
                "query":          str,
                "answer":         str,
                "sources":        list[dict],
                "model_used":     str,
                "context_chunks": int
            }
        """
        if logger:
            logger.info(f"SYNTHESIZER | ENTER | query={query!r} chunks_received={len(chunks)}")

        # chunks arrive pre-sorted by similarity desc from the retriever
        selected = chunks[:max_context]

        if not selected:
            if logger:
                logger.warning("SYNTHESIZER | EXIT | no chunks received — returning refusal string")
            return {
                "query":          query,
                "answer":         "The provided context does not contain enough information to answer this question.",
                "sources":        [],
                "model_used":     GROQ_MODEL,
                "context_chunks": 0,
            }

        if logger:
            logger.info(f"SYNTHESIZER | context | chunks_selected={len(selected)} (cap={max_context})")
            source_labels = [
                f"{c.get('company','?')} {c.get('year','?')} {c.get('section','?')}"
                for c in selected
            ]
            logger.info(f"SYNTHESIZER | context | sources={source_labels}")

        context = self._build_context(selected)
        user_prompt = f"{context}\nQuestion: {query}"

        if logger:
            logger.info(f"SYNTHESIZER | Groq call | model={GROQ_MODEL} max_tokens=1024 temperature=0")

        response = self.groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0,
            max_tokens=1024,
        )

        answer = response.choices[0].message.content.strip()

        if logger:
            logger.info(f"SYNTHESIZER | Groq response | answer_length={len(answer)} chars")
            logger.info(f"SYNTHESIZER | Groq response | answer=\n{answer}")
            logger.info(
                f"SYNTHESIZER | EXIT | model={GROQ_MODEL} context_chunks={len(selected)}"
            )

        return {
            "query":          query,
            "answer":         answer,
            "sources":        selected,
            "model_used":     GROQ_MODEL,
            "context_chunks": len(selected),
        }
