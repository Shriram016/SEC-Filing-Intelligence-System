import pytest
from qdrant_client import QdrantClient

from filing_rag.ingest.blocks import Block
from filing_rag.ingest.chunker import Chunk, Chunker, Placed
from filing_rag.ingest.labels import DocMeta
from filing_rag.ingest.store import QdrantStore, point_id
from tests.unit.ingest_helpers import word_count

DIM = 4


def chunks_for(doc: str, n: int) -> list[Chunk]:
    meta = DocMeta(doc, "Co", "10-K", 2019)
    items = [Placed(Block("text", i, f"Paragraph {i} of {doc}."), f"Item {i}", None, None)
             for i in range(1, n + 1)]  # fmt: skip
    return Chunker(meta, word_count).run(items)


def vecs(n: int) -> list[list[float]]:
    return [[1.0, float(i), 0.0, 0.5] for i in range(n)]


def make_store() -> QdrantStore:
    store = QdrantStore(QdrantClient(":memory:"), "chunks", DIM)
    store.ensure_collection()
    return store


def test_replace_document_is_idempotent() -> None:
    store = make_store()
    a = chunks_for("A", 3)
    store.replace_document("A", a, vecs(3))
    store.replace_document("A", a, vecs(3))
    assert store.count("A") == 3


def test_replace_removes_stale_chunks_and_keeps_other_documents() -> None:
    store = make_store()
    store.replace_document("A", chunks_for("A", 3), vecs(3))
    store.replace_document("B", chunks_for("B", 2), vecs(2))
    store.replace_document("A", chunks_for("A", 1), vecs(1))
    assert store.count("A") == 1
    assert store.count("B") == 2
    assert store.count() == 3


def test_payload_is_stored() -> None:
    store = make_store()
    a = chunks_for("A", 1)
    store.replace_document("A", a, vecs(1))
    got = store.client.retrieve("chunks", ids=[point_id(a[0].chunk_id)])
    assert got[0].payload is not None
    assert got[0].payload["doc_name"] == "A"
    assert "embed_text" not in got[0].payload


def test_vector_size_mismatch_is_an_error() -> None:
    client = QdrantClient(":memory:")
    QdrantStore(client, "chunks", DIM).ensure_collection()
    with pytest.raises(ValueError, match="vector size"):
        QdrantStore(client, "chunks", 8).ensure_collection()


def test_length_mismatch_is_an_error() -> None:
    store = make_store()
    with pytest.raises(ValueError):
        store.replace_document("A", chunks_for("A", 2), vecs(1))
