"""M1a step 5: compare free local embedding models on the frozen test questions.

Search = exact cosine similarity in numpy (no vector store; tests the model only).
Modes: all 5 documents, and filtered to the question's company.
Chunk sets: "small" (~280 words) and "page" (one chunk per page).

Run: uv run --group embed python experiments/m1a/test_embed.py
Writes: experiments/m1a/results/embed_results.json
"""

from __future__ import annotations

import gc
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

HERE = Path(__file__).parent
RESULTS = HERE / "results"
QUESTIONS = HERE / "embed_questions.json"
FROZEN_SHA256 = "0277b24862e8cddf3f0187391faaaf73593f6d31e1e307ca3ff14d0a5060acf9"

MODELS: dict[str, dict[str, Any]] = {
    "bge-base-en-v1.5": {
        "id": "BAAI/bge-base-en-v1.5",
        "query_prompt": "Represent this sentence for searching relevant passages: ",
        "max_len": 512,
    },
    "bge-m3": {"id": "BAAI/bge-m3", "query_prompt": "", "max_len": 8192},
    "Qwen3-Embedding-0.6B": {
        "id": "Qwen/Qwen3-Embedding-0.6B",
        "query_prompt": (
            "Instruct: Given a question about a company filing, retrieve passages "
            "that answer the question\nQuery:"
        ),
        "max_len": 8192,
    },
}
COMPANY = {
    "ADOBE": "Adobe",
    "JPMORGAN": "JPMorgan",
    "LOCKHEEDMARTIN": "Lockheed Martin",
    "ULTABEAUTY": "Ulta Beauty",
    "WALMART": "Walmart",
}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


def is_hit(q: dict[str, Any], chunk: dict[str, Any]) -> bool:
    if "pages" in q and chunk["page_number"] not in q["pages"]:
        return False
    return norm(q["answer_text"]) in norm(chunk["text"])


def evaluate(
    questions: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    q_emb: np.ndarray,
    c_emb: np.ndarray,
    company_filter: bool,
) -> list[dict[str, Any]]:
    companies = np.array([COMPANY[c["doc_name"].split("_")[0]] for c in chunks])
    out = []
    for i, q in enumerate(questions):
        scores = c_emb @ q_emb[i]
        if company_filter:
            scores = np.where(companies == q["company"], scores, -np.inf)
        order = np.argsort(-scores)[:10]
        rank = next((r + 1 for r, j in enumerate(order) if is_hit(q, chunks[j])), None)
        out.append(
            {
                "id": q["id"],
                "type": q["type"],
                "rank": rank,
                "top3": [chunks[j]["chunk_id"] for j in order[:3]],
            }
        )
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    n = len(rows)
    ranks = [r["rank"] for r in rows]
    return {
        "n": n,
        "hit@1": round(100 * sum(1 for r in ranks if r and r <= 1) / n, 1),
        "hit@5": round(100 * sum(1 for r in ranks if r and r <= 5) / n, 1),
        "hit@10": round(100 * sum(1 for r in ranks if r) / n, 1),
        "mrr@10": round(sum(1 / r for r in ranks if r) / n, 3),
    }


def main() -> None:
    digest = hashlib.sha256(QUESTIONS.read_bytes()).hexdigest()
    if digest != FROZEN_SHA256:
        raise SystemExit(f"question file changed after freezing: {digest}")
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    chunk_sets = {
        name: json.loads((RESULTS / f"chunks_{name}.json").read_text(encoding="utf-8"))
        for name in ("small", "page")
    }
    results: dict[str, Any] = {"questions_sha256": digest, "models": {}}

    for mname, cfg in MODELS.items():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        t0 = time.perf_counter()
        model = SentenceTransformer(
            cfg["id"], device="cuda", model_kwargs={"torch_dtype": torch.float16}
        )
        model.max_seq_length = cfg["max_len"]
        load_s = time.perf_counter() - t0
        mres: dict[str, Any] = {
            "load_seconds": round(load_s, 1),
            "dim": model.get_sentence_embedding_dimension(),
        }
        q_texts = [cfg["query_prompt"] + q["question"] for q in questions]
        t0 = time.perf_counter()
        q_emb = model.encode(q_texts, normalize_embeddings=True, batch_size=16)
        mres["ms_per_query"] = round(1000 * (time.perf_counter() - t0) / len(questions), 1)

        for cname, chunks in chunk_sets.items():
            texts = [c["text"] for c in chunks]
            tok = model.tokenizer(texts, add_special_tokens=True, truncation=False)["input_ids"]
            over = sum(1 for t in tok if len(t) > cfg["max_len"])
            t0 = time.perf_counter()
            c_emb = model.encode(
                texts, normalize_embeddings=True, batch_size=8 if cname == "page" else 32
            )
            secs = time.perf_counter() - t0
            block: dict[str, Any] = {
                "chunks": len(chunks),
                "chunks_cut_by_input_limit": over,
                "median_tokens": int(np.median([len(t) for t in tok])),
                "embed_seconds": round(secs, 1),
                "chunks_per_second": round(len(chunks) / secs, 1),
            }
            for mode, filt in (("all_docs", False), ("company_filter", True)):
                rows = evaluate(questions, chunks, q_emb, c_emb, filt)
                block[mode] = {
                    "overall": summarize(rows),
                    "by_type": {
                        t: summarize([r for r in rows if r["type"] == t])
                        for t in ("table", "text", "hard")
                    },
                    "rows": rows,
                }
            mres[cname] = block
            o = block["all_docs"]["overall"]
            f = block["company_filter"]["overall"]
            print(
                f"{mname:22} {cname:5} hit@5 all={o['hit@5']} filt={f['hit@5']} "
                f"mrr={o['mrr@10']} cut={over}/{len(chunks)} {block['chunks_per_second']} ch/s"
            )
        mres["gpu_peak_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
        results["models"][mname] = mres
        del model
        gc.collect()

    (RESULTS / "embed_results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("wrote results/embed_results.json")


if __name__ == "__main__":
    main()
