import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from filing_rag.config import Settings
from filing_rag.evaluation.locked import (
    REGISTER_NAME,
    SPLIT_NAME,
    LockedSetError,
    label_counts,
    label_row,
    load_fb_dev,
    lock,
    locked_file,
    open_locked,
    read_labels,
    stratified_split,
    write_fb_dev,
)

TYPES = ["metrics-generated"] * 60 + ["domain-relevant"] * 45 + ["novel-generated"] * 45


def _rows() -> list[dict[str, Any]]:
    return [
        {
            "financebench_id": f"fb_{i:03d}",
            "question_type": t,
            "question_reasoning": [
                "Numerical reasoning",
                "Information extraction",
                "Logical reasoning",
            ][i % 3],
            "doc_type": "10k" if i % 4 else "10q",
            "gics_sector": f"S{i % 5}",
            "doc_period": str(2015 + i % 8),
            "company": f"C{i % 40}",
            "question": "SECRET QUESTION",
            "answer": "SECRET ANSWER",
            "justification": "SECRET",
            "evidence": [{"doc_name": "D", "evidence_page_num": 1, "evidence_text": "SECRET"}]
            * (1 + i % 2),
        }  # fmt: skip
        for i, t in enumerate(TYPES)
    ]


def test_label_row_drops_every_text_field() -> None:
    row = label_row(_rows()[1])
    assert "SECRET" not in json.dumps(row)
    assert row["financebench_id"] == "fb_001" and row["evidence_pages"] == 2
    assert set(row) == {"financebench_id", "question_type", "question_reasoning", "doc_type",
                        "gics_sector", "doc_period", "company", "evidence_pages"}  # fmt: skip


def test_split_sizes_are_exact_and_parts_do_not_overlap() -> None:
    rows = [label_row(r) for r in _rows()]
    dev, closed = stratified_split(rows, 50, seed=1)
    assert len(dev) == 50 and len(closed) == 100
    assert not set(dev) & set(closed)
    assert set(dev) | set(closed) == {r["financebench_id"] for r in rows}


def test_split_keeps_the_type_shares_and_the_other_mixes() -> None:
    rows = [label_row(r) for r in _rows()]
    dev, _ = stratified_split(rows, 50, seed=1)
    picked = [r for r in rows if r["financebench_id"] in set(dev)]
    assert Counter(r["question_type"] for r in picked) == {
        "metrics-generated": 20, "domain-relevant": 15, "novel-generated": 15}  # fmt: skip
    reasoning = Counter(r["question_reasoning"] for r in picked)
    assert all(15 <= n <= 19 for n in reasoning.values())  # about 1/3 each
    pages = Counter(r["evidence_pages"] for r in picked)
    assert all(23 <= n <= 27 for n in pages.values())  # about 1/2 each


def test_split_is_the_same_for_the_same_seed() -> None:
    rows = [label_row(r) for r in _rows()]
    assert stratified_split(rows, 50, seed=7) == stratified_split(rows, 50, seed=7)
    assert stratified_split(rows, 50, seed=7) != stratified_split(rows, 50, seed=8)


def test_largest_remainder_with_uneven_types() -> None:
    rows = [{"financebench_id": f"x{i}", "question_type": t}
            for i, t in enumerate(["a"] * 7 + ["b"] * 7 + ["c"] * 7)]  # fmt: skip
    dev, closed = stratified_split(rows, 10, seed=3)
    got = Counter(r["question_type"] for r in rows if r["financebench_id"] in set(dev))
    assert sum(got.values()) == 10 and sorted(got.values()) == [3, 3, 4]


def test_label_counts_count_values_only() -> None:
    counts = label_counts([label_row(r) for r in _rows()])
    assert counts["question_type"] == {"metrics-generated": 60, "domain-relevant": 45,
                                       "novel-generated": 45}  # fmt: skip
    assert "SECRET" not in json.dumps(counts)


def test_read_labels_needs_allow_and_is_registered(settings: Settings) -> None:
    p = locked_file(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in _rows()) + "\n", encoding="utf-8")
    lock(settings)
    with pytest.raises(LockedSetError, match="allow=True"):
        read_labels(settings, allow=False, reason="x")
    with pytest.raises(LockedSetError, match="reason"):
        read_labels(settings, allow=True, reason=" ")
    rows = read_labels(settings, allow=True, reason="Q112 split")
    assert len(rows) == 150 and "SECRET" not in json.dumps(rows)
    lines = (settings.eval_dir / REGISTER_NAME).read_text().splitlines()
    assert json.loads(lines[-1])["milestone"] == "Q112-labels"


def _locked_with_split(settings: Settings) -> list[str]:
    p = locked_file(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in _rows()) + "\n", encoding="utf-8")
    lock(settings)
    dev, closed = stratified_split([label_row(r) for r in _rows()], 50, seed=1)
    (settings.eval_dir / SPLIT_NAME).write_text(
        json.dumps({"dev_ids": dev, "closed_ids": closed}), encoding="utf-8"
    )
    return dev


def test_fb_dev_file_holds_only_the_50_dev_rows(settings: Settings) -> None:
    dev = _locked_with_split(settings)
    with pytest.raises(LockedSetError, match="allow=True"):
        write_fb_dev(settings, allow=False, reason="x")
    out = write_fb_dev(settings, allow=True, reason="Q112 FB-dev copy")
    rows = load_fb_dev(settings)
    assert out == settings.fb_dev_file
    assert sorted(r["financebench_id"] for r in rows) == dev
    assert rows[0]["question"] == "SECRET QUESTION"  # dev rows are open: full text
    lines = (settings.eval_dir / REGISTER_NAME).read_text().splitlines()
    assert json.loads(lines[-1])["milestone"] == "Q112-fb-dev"
    with pytest.raises(LockedSetError, match="written once"):
        write_fb_dev(settings, allow=True, reason="again")


def test_fb_dev_survives_moving_the_locked_file_out(settings: Settings) -> None:
    _locked_with_split(settings)
    write_fb_dev(settings, allow=True, reason="copy")
    locked_file(settings).unlink()  # moved to the vault
    assert len(load_fb_dev(settings)) == 50
    with pytest.raises(LockedSetError, match="FILING_RAG_LOCKED_VAULT_DIR"):
        open_locked(settings, allow=True, milestone="M6", reason="final")


def test_vault_dir_setting_moves_the_locked_file(settings: Settings, tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    s2 = settings.model_copy(update={"locked_vault_dir": vault})
    assert locked_file(s2) == vault / locked_file(settings).name
