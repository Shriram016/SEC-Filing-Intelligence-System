"""Qdrant vector store (Q86, Q92): server in Docker, `localhost:6333`.

Re-runs are idempotent: all points of a document are deleted, then its chunks are written
again. A point id is derived from the chunk id, so the same chunk always gets the same id.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from qdrant_client import QdrantClient, models

from filing_rag.ingest.chunker import Chunk

ID_NAMESPACE = uuid.UUID("6f3b1c1e-6a5e-4c55-9a43-6a0b3f1d2c11")
INDEXED_FIELDS = {
    "doc_name": models.PayloadSchemaType.KEYWORD,
    "company": models.PayloadSchemaType.KEYWORD,
    "doc_type": models.PayloadSchemaType.KEYWORD,
    "fiscal_year": models.PayloadSchemaType.INTEGER,
    "is_table": models.PayloadSchemaType.BOOL,
    "table_id": models.PayloadSchemaType.KEYWORD,
}
BATCH = 128


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, chunk_id))


class QdrantStore:
    def __init__(self, client: QdrantClient, collection: str, dim: int) -> None:
        self.client = client
        self.collection = collection
        self.dim = dim

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(size=self.dim, distance=models.Distance.COSINE),
            )
            for name, schema in INDEXED_FIELDS.items():
                self.client.create_payload_index(self.collection, name, field_schema=schema)
            return
        info = self.client.get_collection(self.collection)
        params = info.config.params.vectors
        size = params.size if isinstance(params, models.VectorParams) else None
        if size != self.dim:
            raise ValueError(
                f"collection {self.collection!r} has vector size {size}, model gives {self.dim}"
            )

    def _doc_filter(self, doc_name: str) -> models.Filter:
        return models.Filter(
            must=[models.FieldCondition(key="doc_name", match=models.MatchValue(value=doc_name))]
        )

    def replace_document(
        self, doc_name: str, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]
    ) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors differ in length")
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=self._doc_filter(doc_name)),
            wait=True,
        )
        for i in range(0, len(chunks), BATCH):
            points = [
                models.PointStruct(id=point_id(c.chunk_id), vector=list(v), payload=c.payload())
                for c, v in zip(chunks[i : i + BATCH], vectors[i : i + BATCH], strict=True)
            ]
            self.client.upsert(self.collection, points=points, wait=True)
        return len(chunks)

    def count(self, doc_name: str | None = None) -> int:
        flt = self._doc_filter(doc_name) if doc_name else None
        return self.client.count(self.collection, count_filter=flt, exact=True).count
