"""Offline tests for ingestion/metadata_tagger.py — hand-made chunks, no data/ needed."""

import copy

import pytest

from ingestion.metadata_tagger import tag_chunks


def make_chunk(section: str = "Item 1A") -> dict:
    return {
        "chunk_id": "AAPL_2023_Item_1A_chunk_001",
        "ticker": "AAPL",
        "year": 2023,
        "section": section,
        "chunk_index": 1,
        "total_chunks": 1,
        "word_count": 3,
        "text": "Some risk text.",
    }


def test_four_fields_are_added():
    [tagged] = tag_chunks([make_chunk()], "AAPL", 2023)
    assert tagged["company"] == "Apple"
    assert tagged["section_name"] == "Risk Factors"
    assert tagged["filing_type"] == "10-K"
    assert tagged["source_file"] == "AAPL_2023.htm"


def test_original_chunks_are_not_changed():
    chunks = [make_chunk()]
    before = copy.deepcopy(chunks)
    tagged = tag_chunks(chunks, "AAPL", 2023)
    assert chunks == before
    assert all(tagged[0][key] == value for key, value in before[0].items())


@pytest.mark.parametrize("section, name", [
    ("Item 1", "Business"),
    ("Item 1A", "Risk Factors"),
    ("Item 7", "MD&A"),
    ("Item 7A", "Market Risk"),
])
def test_section_names(section, name):
    [tagged] = tag_chunks([make_chunk(section)], "AAPL", 2023)
    assert tagged["section_name"] == name


def test_unknown_ticker_and_section_give_unknown():
    [tagged] = tag_chunks([make_chunk("Item 99")], "TSLA", 2023)
    assert tagged["company"] == "Unknown"
    assert tagged["section_name"] == "Unknown"
