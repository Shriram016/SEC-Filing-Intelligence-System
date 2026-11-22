import pytest
from qdrant_client import QdrantClient, models

from filing_rag.search.searcher import Hit, Searcher

DIM = 3
VECTORS = {"revenue": [1.0, 0.0, 0.0], "debt": [0.0, 1.0, 0.0]}


class FakeEmbedder:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return VECTORS[text]


def make_searcher() -> tuple[Searcher, FakeEmbedder]:
    client = QdrantClient(":memory:")
    client.create_collection(
        "chunks", vectors_config=models.VectorParams(size=DIM, distance=models.Distance.COSINE)
    )
    rows = [  # id, vector, company, page, page_end, text
        (1, [1.0, 0.0, 0.0], "A", 5, 5, "rev A"),
        (2, [0.9, 0.1, 0.0], "B", 7, 8, "rev B"),
        (3, [0.0, 1.0, 0.0], "A", 9, 9, "debt A"),
    ]
    points = [
        models.PointStruct(
            id=i,
            vector=v,
            payload={"doc_name": f"{c}_10K", "company": c, "page": p, "page_end": pe, "text": t},
        )
        for i, v, c, p, pe, t in rows
    ]
    client.upsert("chunks", points=points)
    emb = FakeEmbedder()
    return Searcher(client, "chunks", emb), emb


def test_search_ranks_by_similarity_without_filter() -> None:
    searcher, emb = make_searcher()
    hits = searcher.search("revenue", k=3)
    assert [h.payload["text"] for h in hits] == ["rev A", "rev B", "debt A"]
    assert hits[0].score >= hits[1].score >= hits[2].score
    assert emb.queries == ["revenue"]


def test_company_is_a_hard_filter() -> None:
    searcher, _ = make_searcher()
    hits = searcher.search("revenue", company="B", k=3)
    assert [h.doc_name for h in hits] == ["B_10K"]


def test_unknown_company_returns_nothing() -> None:
    searcher, _ = make_searcher()
    assert searcher.search("revenue", company="Z", k=3) == []


def test_k_limits_results_and_must_be_positive() -> None:
    searcher, _ = make_searcher()
    assert len(searcher.search("revenue", k=1)) == 1
    with pytest.raises(ValueError):
        searcher.search("revenue", k=0)


def test_no_filter_when_company_is_empty() -> None:
    assert Searcher.build_filter(None) is None
    assert Searcher.build_filter("") is None


def test_doc_names_filter_one_document() -> None:
    searcher, _ = make_searcher()
    hits = searcher.search("revenue", k=3, doc_names=["B_10K"])
    assert [h.doc_name for h in hits] == ["B_10K"]


def test_doc_names_filter_two_documents() -> None:
    searcher, _ = make_searcher()
    hits = searcher.search("revenue", k=3, doc_names=["A_10K", "B_10K"])
    assert [h.payload["text"] for h in hits] == ["rev A", "rev B", "debt A"]


def test_doc_names_none_or_empty_means_no_filter() -> None:
    assert Searcher.build_filter(None, None) is None
    assert Searcher.build_filter(None, []) is None
    searcher, _ = make_searcher()
    assert len(searcher.search("revenue", k=3, doc_names=[])) == 3


def test_company_and_doc_names_combine() -> None:
    f = Searcher.build_filter("A", ["A_10K"])
    assert f is not None and f.must is not None and len(f.must) == 2  # type: ignore[arg-type]
    searcher, _ = make_searcher()
    assert searcher.search("revenue", company="A", k=3, doc_names=["B_10K"]) == []


def test_hit_covers_page_range() -> None:
    hit = Hit(0.5, {"doc_name": "B_10K", "page": 7, "page_end": 8})
    assert hit.covers("B_10K", 7) and hit.covers("B_10K", 8)
    assert not hit.covers("B_10K", 9)
    assert not hit.covers("A_10K", 7)


def test_hit_without_page_end_uses_page() -> None:
    hit = Hit(0.5, {"doc_name": "A", "page": 3})
    assert hit.page_end == 3


def test_table_parts_returns_all_parts_in_order() -> None:
    s, _ = make_searcher()
    parts = [  # stored out of order, plus a part of another table
        (10, 3, "T1"), (11, 1, "T1"), (12, 2, "T1"), (13, 1, "T2"),
    ]  # fmt: skip
    s.client.upsert(
        "chunks",
        points=[
            models.PointStruct(
                id=i,
                vector=[0.0, 0.0, 1.0],
                payload={
                    "doc_name": "A_10K",
                    "page": 3,
                    "is_table": True,
                    "table_id": t,
                    "table_part": n,
                    "table_parts": 3 if t == "T1" else 1,
                },
            )  # fmt: skip
            for i, n, t in parts
        ],
    )
    got = s.table_parts("T1")
    assert [h.payload["table_part"] for h in got] == [1, 2, 3]
    assert all(h.payload["table_id"] == "T1" for h in got)
    assert s.table_parts("missing") == []
