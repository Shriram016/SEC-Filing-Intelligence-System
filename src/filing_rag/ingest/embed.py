"""Local embedding model (Q89): bge-base-en-v1.5, fp16 on the GPU.

The heavy libraries (torch, sentence-transformers) are in the optional `embed` group and are
imported only when the model loads, so the rest of the package and the unit tests run without
them (CI does not install them).
"""

from __future__ import annotations

from typing import Any, Protocol


class Embedder(Protocol):
    dim: int

    def count_tokens(self, text: str) -> int: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class BgeEmbedder:
    """Documents are embedded as they are; queries get the bge search prefix."""

    def __init__(self, model_id: str, query_prefix: str, batch_size: int = 32) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        kwargs: dict[str, Any] = {"torch_dtype": torch.float16} if device == "cuda" else {}
        self._model = SentenceTransformer(model_id, device=device, model_kwargs=kwargs)
        self._tok = self._model.tokenizer
        self.max_tokens = int(self._model.max_seq_length or 512)
        self.query_prefix = query_prefix
        self.batch_size = batch_size
        get_dim = getattr(self._model, "get_embedding_dimension", None) or (
            self._model.get_sentence_embedding_dimension
        )
        dim = get_dim()
        if dim is None:
            raise RuntimeError("embedding model has no fixed dimension")
        self.dim = int(dim)
        self.device = device

    def count_tokens(self, text: str) -> int:
        """Tokens incl. the special tokens, without truncation (same count the model sees)."""
        return len(self._tok(text, add_special_tokens=True, truncation=False)["input_ids"])

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False
        )
        return [[float(x) for x in v] for v in vecs]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([self.query_prefix + text])[0]
