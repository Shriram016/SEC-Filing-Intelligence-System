import json
from pathlib import Path

import pytest
from qdrant_client import QdrantClient

from filing_rag.config import Settings
from filing_rag.ingest.layout import Page
from filing_rag.ingest.pipeline import (
    COLLECTION_FILE,
    IngestDirMismatch,
    check_ingest_dir,
    run,
)
from filing_rag.ingest.store import QdrantStore
from tests.unit.ingest_helpers import line, page_of, text_line, word_count
from tests.unit.test_ingest_catalog import row, write_doc_list


class FakeEmbedder:
    dim = 3

    def count_tokens(self, text: str) -> int:
        return word_count(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, float(len(t) % 7), 0.5] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


def fake_reader(path: Path) -> list[Page]:
    p1 = page_of(
        [
            text_line("FORM 10-K", 50, bold=True),
            text_line("For the fiscal year ended December 31, 2019", 70),
            text_line("Item 7. Management's Discussion and Analysis", 120, bold=True),
            text_line("Revenue grew because customers bought more products this year.", 140),
        ],
        1,
    )
    p2 = page_of(
        [
            text_line("Item 8. Financial Statements and Supplementary Data", 50, bold=True),
            text_line("CONSOLIDATED BALANCE SHEETS", 70),
            line((300, "2019"), (400, "2018"), top=90),
            line((60, "Cash"), (300, "48,844"), (400, "25,913"), top=102),
            line((60, "Receivables"), (300, "22,926"), (400, "23,186"), top=114),
        ],
        2,
    )
    return [p1, p2]


def setup_docs(settings: Settings) -> None:
    write_doc_list(settings, [row("GOOD_2019_10K"), row("MISSING_2019_10K"), row("BAD_2023_8K")])
    settings.pdf_dir.mkdir(parents=True)
    (settings.pdf_dir / "GOOD_2019_10K.pdf").write_bytes(b"%PDF-1.7 fake")
    settings.eval_dir.mkdir(parents=True, exist_ok=True)
    (settings.eval_dir / "pdf_overrides.json").write_text(
        json.dumps({"unrecoverable": {"BAD_2023_8K": {"reason": "truncated"}}})
    )


def test_run_end_to_end_with_fakes(settings: Settings) -> None:
    setup_docs(settings)
    store = QdrantStore(QdrantClient(":memory:"), "chunks", FakeEmbedder.dim)
    names = ["GOOD_2019_10K", "MISSING_2019_10K", "BAD_2023_8K", "NOT_IN_LIST"]
    report = run(names, settings, FakeEmbedder(), store, reader=fake_reader)

    assert report["ok"] == 1
    assert set(report["skipped"]) == {"MISSING_2019_10K", "BAD_2023_8K"}
    assert "not found" in report["skipped"]["MISSING_2019_10K"]
    assert "unrecoverable" in report["skipped"]["BAD_2023_8K"]
    assert report["checks"]["duplicate_chunk_ids"] == 0
    assert report["checks"]["chunks_over_limit"] == 0
    assert report["checks"]["chunks_without_period_date"] == 0
    assert report["table_chunks"] == 1

    good = report["per_document"]["GOOD_2019_10K"]
    assert good["period_end"] == "2019-12-31"
    assert store.count("GOOD_2019_10K") == report["chunks"]

    lines = (settings.ingest_dir / "chunks" / "GOOD_2019_10K.jsonl").read_text().splitlines()
    chunks = [json.loads(x) for x in lines]
    sections = {c["section"] for c in chunks}
    assert "Item 8. Financial Statements and Supplementary Data" in sections
    table = next(c for c in chunks if c["is_table"])
    assert table["section"].startswith("Item 8")
    assert "48,844" in table["text"]

    catalog = json.loads((settings.ingest_dir / "catalog.json").read_text())
    assert {r["doc_name"] for r in catalog} == {"GOOD_2019_10K", "MISSING_2019_10K", "BAD_2023_8K"}

    # re-run: same chunks, no duplicates in the store
    run(["GOOD_2019_10K"], settings, FakeEmbedder(), store, reader=fake_reader)
    assert store.count("GOOD_2019_10K") == report["chunks"]


def test_reader_failure_skips_the_document(settings: Settings) -> None:
    setup_docs(settings)

    def broken(path: Path) -> list[Page]:
        raise RuntimeError("parser crashed")

    report = run(["GOOD_2019_10K"], settings, FakeEmbedder(), None, reader=broken)
    assert report["ok"] == 0
    assert "parser crashed" in report["skipped"]["GOOD_2019_10K"]


def test_unchanged_documents_are_skipped_and_force_redoes_them(settings: Settings) -> None:
    setup_docs(settings)
    store = QdrantStore(QdrantClient(":memory:"), "chunks", FakeEmbedder.dim)
    calls: list[Path] = []

    def counting_reader(path: Path) -> list[Page]:
        calls.append(path)
        return fake_reader(path)

    first = run(["GOOD_2019_10K"], settings, FakeEmbedder(), store, reader=counting_reader)
    assert len(calls) == 1

    again = run(["GOOD_2019_10K"], settings, FakeEmbedder(), store, reader=counting_reader)
    assert len(calls) == 1  # same PDF + same settings: skipped
    assert again["chunks"] == first["chunks"]  # the report still counts its chunks

    run(["GOOD_2019_10K"], settings, FakeEmbedder(), store, reader=counting_reader, force=True)
    assert len(calls) == 2

    changed = settings.model_copy(update={"label_depth": "full"})
    run(["GOOD_2019_10K"], changed, FakeEmbedder(), store, reader=counting_reader)
    assert len(calls) == 3  # settings changed: redone

    store.client.delete_collection("chunks")
    run(["GOOD_2019_10K"], changed, FakeEmbedder(), store, reader=counting_reader)
    assert len(calls) == 4  # points missing in Qdrant: redone
    assert store.count("GOOD_2019_10K") == first["chunks"]

    (settings.pdf_dir / "GOOD_2019_10K.pdf").write_bytes(b"%PDF-1.7 fake, new version")
    run(["GOOD_2019_10K"], changed, FakeEmbedder(), store, reader=counting_reader)
    assert len(calls) == 5  # PDF changed: redone


def test_settings_fingerprint_changes_with_chunk_settings(settings: Settings) -> None:
    from filing_rag.ingest.pipeline import settings_fingerprint

    base = settings_fingerprint(settings)
    assert base == settings_fingerprint(settings.model_copy())
    for update in ({"label_depth": "none"}, {"chunk_target_tokens": 300}, {"embedding_model": "x"}):
        assert settings_fingerprint(settings.model_copy(update=update)) != base


def test_an_ingest_folder_belongs_to_one_collection(settings: Settings) -> None:
    """Q105: a run for another collection stops before it changes the folder's files."""
    setup_docs(settings)
    first = QdrantStore(QdrantClient(":memory:"), "chunks", FakeEmbedder.dim)
    run(["GOOD_2019_10K"], settings, FakeEmbedder(), first, reader=fake_reader)
    assert (settings.ingest_dir / COLLECTION_FILE).read_text().strip() == "chunks"
    catalog = (settings.ingest_dir / "catalog.json").read_text()

    other = QdrantStore(QdrantClient(":memory:"), "chunks_v2", FakeEmbedder.dim)
    with pytest.raises(IngestDirMismatch, match="belongs to collection 'chunks'"):
        run(["GOOD_2019_10K"], settings, FakeEmbedder(), other, reader=fake_reader, force=True)
    assert (settings.ingest_dir / "catalog.json").read_text() == catalog
    assert not other.client.collection_exists("chunks_v2")

    own = settings.model_copy(update={"ingest_dir_name": "v3_chunks_v2"})
    run(["GOOD_2019_10K"], own, FakeEmbedder(), other, reader=fake_reader)
    assert (own.ingest_dir / COLLECTION_FILE).read_text().strip() == "chunks_v2"
    assert other.count("GOOD_2019_10K") > 0


def test_check_ingest_dir_writes_the_owner_once(settings: Settings) -> None:
    check_ingest_dir(settings, "chunks")
    check_ingest_dir(settings, "chunks")  # same owner: no error
    with pytest.raises(IngestDirMismatch):
        check_ingest_dir(settings, "other")
