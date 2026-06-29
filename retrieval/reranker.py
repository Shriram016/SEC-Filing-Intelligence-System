import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentence_transformers import CrossEncoder
from langfuse import observe
from config import RERANKER_MODEL


class Reranker:
    def __init__(self):
        self.model = CrossEncoder(RERANKER_MODEL)

    @observe(name="rerank")
    def rerank(self, query, chunks, logger=None):
        if not chunks:
            return chunks

        if logger:
            logger.info(f"RERANKER | ENTER | query={query!r} chunks={len(chunks)}")
            top3_before = [
                f"{c.get('chunk_id','?')} cosine={c.get('similarity_score',0):.4f}"
                for c in chunks[:3]
            ]
            logger.info(f"RERANKER | before | top3={top3_before}")

        before_order = [c.get("chunk_id", i) for i, c in enumerate(chunks)]

        pairs = [[query, chunk["text"]] for chunk in chunks]
        scores = self.model.predict(pairs)

        for chunk, score in zip(chunks, scores):
            chunk["reranker_score"] = float(score)

        chunks.sort(key=lambda x: x["reranker_score"], reverse=True)

        if logger:
            after_order = [c.get("chunk_id", i) for i, c in enumerate(chunks)]
            moved = sum(1 for a, b in zip(before_order, after_order) if a != b)
            top3_after = [
                f"{c.get('chunk_id','?')} reranker={c.get('reranker_score',0):.4f}"
                for c in chunks[:3]
            ]
            logger.info(f"RERANKER | after | top3={top3_after}")
            logger.info(f"RERANKER | EXIT | chunks={len(chunks)} positions_changed={moved}/{len(chunks)}")

        return chunks


if __name__ == "__main__":
    sample_chunks = [
        {"text": "Apple reported revenue of $394 billion in fiscal year 2022, driven by strong iPhone sales.", "similarity_score": 0.85},
        {"text": "The company faces risks related to supply chain disruptions and geopolitical tensions.", "similarity_score": 0.79},
        {"text": "Weather patterns in the midwest affected corn yields during the summer months.", "similarity_score": 0.82},
        {"text": "Apple's risk factors include dependence on single-source suppliers for key components.", "similarity_score": 0.77},
    ]

    query = "What are Apple's main risk factors?"
    reranker = Reranker()

    print("BEFORE reranking (cosine order):")
    for i, c in enumerate(sample_chunks):
        print(f"  {i+1}. [cosine={c['similarity_score']:.3f}] {c['text'][:80]}...")

    reranked = reranker.rerank(query, sample_chunks)

    print("\nAFTER reranking (cross-encoder order):")
    for i, c in enumerate(reranked):
        print(f"  {i+1}. [reranker={c['reranker_score']:.4f}, cosine={c['similarity_score']:.3f}] {c['text'][:80]}...")
