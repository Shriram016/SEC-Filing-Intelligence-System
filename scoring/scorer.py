"""
scoring/scorer.py

Components 12+13 (merged) — Faithfulness Judge + Confidence Scorer.

Responsibilities:
  1. Accept the output dict from Synthesizer.synthesize()
  2. Extract avg retrieval similarity from the sources list
  3. Call Groq (temperature=0) to judge whether the answer stays within
     the retrieved passages — model returns a single integer 1–5
  4. Normalise faithfulness score to 0.0–1.0
  5. Compute weighted confidence score:
         confidence = RETRIEVAL_WEIGHT * avg_similarity
                    + FAITHFULNESS_WEIGHT * faithfulness
  6. Return structured scoring result

Special case:
  If the answer is the standard refusal string (synthesizer could not ground
  an answer), faithfulness is set to 1.0 — the model correctly refused to
  hallucinate, which is the best possible behaviour.

Input:
    synthesizer_result (dict) — output of Synthesizer.synthesize()
    {
        "query":          str,
        "answer":         str,
        "sources":        list[dict],   # chunks with similarity_score field
        "model_used":     str,
        "context_chunks": int
    }

Output:
    {
        "confidence_score":         float,  # 0.0–1.0
        "faithfulness_score":       float,  # 0.0–1.0
        "avg_retrieval_similarity": float,  # mean of similarity_score across sources
        "breakdown": {
            "retrieval_weight":     float,
            "faithfulness_weight":  float,
            "num_sources":          int
        }
    }

Run from project root:
    python scoring/scorer.py
"""

import os
import sys
import re

from dotenv import load_dotenv
from groq import Groq

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GROQ_MODEL, RETRIEVAL_WEIGHT, FAITHFULNESS_WEIGHT

load_dotenv()

# The exact refusal string the synthesizer emits when it cannot ground an answer
REFUSAL_STRING = (
    "The provided context does not contain enough information "
    "to answer this question."
)

# Faithfulness rubric — embedded in the judge prompt
FAITHFULNESS_RUBRIC = """\
Score the answer on a scale of 1 to 5 using this rubric:
  5 = Every claim in the answer is directly supported by the passages
  4 = Most claims are supported; minor inference is present
  3 = Answer is partially supported; some claims go beyond the passages
  2 = Answer makes claims that are not in the passages
  1 = Answer contradicts or ignores the passages entirely

Respond with a single integer (1, 2, 3, 4, or 5) and nothing else."""


class Scorer:
    """
    Judges faithfulness of a synthesized answer and computes a
    weighted confidence score combining retrieval similarity and faithfulness.
    """

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not found. "
                "Create a .env file at project root with: GROQ_API_KEY=your_key"
            )
        self.groq_client = Groq(api_key=api_key)
        print("Scorer ready.\n")

    # ------------------------------------------------------------------
    # Private: build context block for the faithfulness judge
    # ------------------------------------------------------------------

    @staticmethod
    def _build_judge_context(sources: list) -> str:
        """
        Format the source passages the same way the synthesizer does —
        numbered, labelled with company | year | section.
        The judge sees exactly the evidence the synthesizer had.
        """
        lines = ["Source passages:\n"]
        for i, chunk in enumerate(sources, 1):
            label = (
                f"[{i}] {chunk.get('company', chunk.get('ticker'))} | "
                f"{chunk.get('year')} | "
                f"{chunk.get('section_name', chunk.get('section'))}"
            )
            lines.append(label)
            lines.append(f"\"{chunk['text'].strip()}\"\n")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private: call Groq to judge faithfulness
    # ------------------------------------------------------------------

    def _judge_faithfulness(self, answer: str, sources: list) -> float:
        """
        Groq call at temperature=0.
        Sends the passages and the answer; asks for a 1–5 integer score.
        Returns normalised float in [0.0, 1.0].

        Normalisation:  faithfulness = (raw_score - 1) / 4
            1 → 0.00,  2 → 0.25,  3 → 0.50,  4 → 0.75,  5 → 1.00
        """
        context_block = self._build_judge_context(sources)

        prompt = (
            f"{context_block}\n"
            f"Answer to evaluate:\n"
            f"\"{answer.strip()}\"\n\n"
            f"{FAITHFULNESS_RUBRIC}"
        )

        response = self.groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a faithfulness evaluator for an AI question-answering system. "
                        "Your only job is to score whether the given answer is supported by "
                        "the provided source passages. You must respond with a single integer "
                        "from 1 to 5 and nothing else."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=5,   # a single digit is all we need
        )

        raw = response.choices[0].message.content.strip()

        # Extract the first digit 1–5 from the response — handles any stray text
        match = re.search(r"[1-5]", raw)
        if match:
            raw_score = int(match.group())
        else:
            # Fallback: can't parse → assume neutral score (3)
            print(f"  [Scorer] WARNING: could not parse faithfulness score from '{raw}'. Defaulting to 3.")
            raw_score = 3

        return round((raw_score - 1) / 4, 4)   # normalise to [0, 1]

    # ------------------------------------------------------------------
    # Public: score
    # ------------------------------------------------------------------

    def score(self, synthesizer_result: dict) -> dict:
        """
        Compute faithfulness + confidence for one synthesizer output.

        Args:
            synthesizer_result: dict returned by Synthesizer.synthesize()

        Returns:
            {
                "confidence_score":         float,
                "faithfulness_score":       float,
                "avg_retrieval_similarity": float,
                "breakdown": {
                    "retrieval_weight":     float,
                    "faithfulness_weight":  float,
                    "num_sources":          int,
                }
            }
        """
        answer  = synthesizer_result.get("answer", "")
        sources = synthesizer_result.get("sources", [])

        # ── Avg retrieval similarity ────────────────────────────────────
        if sources:
            avg_similarity = round(
                sum(s["similarity_score"] for s in sources) / len(sources), 4
            )
        else:
            avg_similarity = 0.0

        # ── Faithfulness score ──────────────────────────────────────────
        # Refusal = perfect faithfulness (model correctly stayed within context)
        if REFUSAL_STRING in answer:
            faithfulness = 1.0
            print("  [Scorer] Refusal detected — faithfulness set to 1.0 (correct grounding behaviour).")
        elif not sources:
            faithfulness = 0.0
            print("  [Scorer] No sources and no refusal — faithfulness set to 0.0.")
        else:
            print("  [Scorer] Calling Groq faithfulness judge...")
            faithfulness = self._judge_faithfulness(answer, sources)

        # ── Confidence formula ──────────────────────────────────────────
        confidence = round(
            RETRIEVAL_WEIGHT * avg_similarity + FAITHFULNESS_WEIGHT * faithfulness,
            4
        )

        return {
            "confidence_score":         confidence,
            "faithfulness_score":       faithfulness,
            "avg_retrieval_similarity": avg_similarity,
            "breakdown": {
                "retrieval_weight":     RETRIEVAL_WEIGHT,
                "faithfulness_weight":  FAITHFULNESS_WEIGHT,
                "num_sources":          len(sources),
            },
        }


# -----------------------------------------------------------------------
# Script entry point — single test case: AAPL 2020 risk factors
# -----------------------------------------------------------------------

if __name__ == "__main__":

    # Import the pipeline components — must run from project root
    from retrieval.retriever import Retriever
    from synthesis.synthesizer import Synthesizer

    print("=" * 65)
    print("scorer.py — single-file test: AAPL 2020")
    print("=" * 65)

    # Initialise all three components
    retriever   = Retriever()
    synthesizer = Synthesizer()
    scorer      = Scorer()

    query = "What were Apple's main risk factors in 2020?"

    print(f"\nQuery: {query}\n")

    # ── Step 1: retrieve ────────────────────────────────────────────────
    chunks = retriever.retrieve(query)

    if isinstance(chunks, dict) and "error" in chunks:
        print(f"Retriever rejected query: {chunks['error']}")
        sys.exit(1)

    print(f"\nRetrieved {len(chunks)} chunk(s).")

    # ── Step 2: synthesize ──────────────────────────────────────────────
    result = synthesizer.synthesize(query, chunks)

    print("\n--- ANSWER ---")
    print(result["answer"])
    print(f"\nContext chunks used: {result['context_chunks']}")
    sources_span = [f"{s['ticker']} {s['year']}" for s in result['sources']]
    print(f"Sources span: {sources_span}")

    # ── Step 3: score ───────────────────────────────────────────────────
    print("\n--- SCORING ---")
    scoring = scorer.score(result)

    print(f"\n  confidence_score         : {scoring['confidence_score']}")
    print(f"  faithfulness_score       : {scoring['faithfulness_score']}")
    print(f"  avg_retrieval_similarity : {scoring['avg_retrieval_similarity']}")
    print(f"\n  breakdown:")
    for k, v in scoring["breakdown"].items():
        print(f"    {k}: {v}")
