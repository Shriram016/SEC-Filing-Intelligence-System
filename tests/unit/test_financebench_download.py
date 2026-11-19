import json
from pathlib import Path

import httpx

from filing_rag.config import Settings
from filing_rag.data.financebench import (
    download_financebench,
    needs_download,
    sha256_file,
    unique_doc_names,
)

DOCS = [{"doc_name": "A_2020_10K"}, {"doc_name": "B_2021_10Q"}, {"doc_name": "A_2020_10K"}]
QUESTIONS = [{"financebench_id": "q1"}]


def _transport(fail: set[str] | None = None) -> httpx.MockTransport:
    failing = fail or set()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if any(path.endswith(f) for f in failing):
            return httpx.Response(404)
        if path.endswith("document_information.jsonl"):
            return httpx.Response(200, text="\n".join(json.dumps(d) for d in DOCS))
        if path.endswith("open_source.jsonl"):
            return httpx.Response(200, text="\n".join(json.dumps(q) for q in QUESTIONS))
        return httpx.Response(200, content=b"%PDF-" + path.encode())

    return httpx.MockTransport(handler)


def test_unique_doc_names_reports_duplicates() -> None:
    names, dupes = unique_doc_names(DOCS)
    assert names == ["A_2020_10K", "B_2021_10Q"]
    assert dupes == ["A_2020_10K"]


def test_needs_download(tmp_path: Path) -> None:
    f = tmp_path / "x.pdf"
    assert needs_download(f, None)
    f.write_bytes(b"abc")
    assert not needs_download(f, None)
    assert not needs_download(f, sha256_file(f))
    assert needs_download(f, "0" * 64)


def test_download_writes_files_manifest_and_is_idempotent(
    settings: Settings, tmp_path: Path
) -> None:
    manifest = tmp_path / "manifest.json"
    with httpx.Client(transport=_transport()) as c:
        r1 = download_financebench(settings, c, manifest)
    assert sorted(r1.downloaded) == [
        "data/document_information.jsonl",
        "locked/financebench_open_source.jsonl",
        "pdfs/A_2020_10K.pdf",
        "pdfs/B_2021_10Q.pdf",
    ]
    assert r1.duplicate_doc_names == ["A_2020_10K"]
    assert (settings.locked_dir / "financebench_open_source.jsonl").exists()
    data = json.loads(manifest.read_text())
    assert data["commit"] == settings.financebench_commit
    assert set(data["files"]) == set(r1.downloaded)

    with httpx.Client(transport=_transport()) as c:
        r2 = download_financebench(settings, c, manifest)
    assert r2.downloaded == []
    assert len(r2.skipped) == 4


def test_redownloads_file_that_changed(settings: Settings, tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    with httpx.Client(transport=_transport()) as c:
        download_financebench(settings, c, manifest)
    (settings.pdf_dir / "A_2020_10K.pdf").write_bytes(b"corrupted")
    with httpx.Client(transport=_transport()) as c:
        r = download_financebench(settings, c, manifest)
    assert r.downloaded == ["pdfs/A_2020_10K.pdf"]


def test_one_failed_file_does_not_stop_the_run(settings: Settings, tmp_path: Path) -> None:
    with httpx.Client(transport=_transport(fail={"A_2020_10K.pdf"})) as c:
        r = download_financebench(settings, c, tmp_path / "m.json")
    assert list(r.failed) == ["pdfs/A_2020_10K.pdf"]
    assert "pdfs/B_2021_10Q.pdf" in r.downloaded
    assert not (settings.pdf_dir / "A_2020_10K.pdf.part").exists()
