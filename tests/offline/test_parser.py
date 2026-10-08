"""Offline tests for ingestion/parser.py — run on a tiny fake filing, no data/ needed."""

from pathlib import Path

import pytest

from ingestion.parser import extract_text, strip_page_artifacts

FIXTURE = Path(__file__).parent.parent / "fixtures" / "mini_10k.htm"


@pytest.fixture(scope="module")
def parsed_text():
    return extract_text(str(FIXTURE), "AAPL")


def test_noise_blocks_removed(parsed_text):
    assert "HIDDEN_XBRL_METADATA" not in parsed_text
    assert "var x" not in parsed_text
    assert "color:red" not in parsed_text


def test_footer_and_company_header_lines_removed(parsed_text):
    assert "Form 10-K" not in parsed_text
    assert "Apple Inc." not in parsed_text.splitlines()


def test_real_content_kept_with_newlines(parsed_text):
    lines = parsed_text.splitlines()
    assert "Item 1. Business" in lines
    assert "Supply chain risk is significant." in lines


def test_spaces_and_tabs_collapse(parsed_text):
    assert "We design smartphones and computers." in parsed_text.splitlines()


def test_strip_page_artifacts_only_strips_own_company():
    text = "Apple Inc.\nApple Inc. announced a new product.\nBody line"
    # For MSFT, Apple's legal name is not a header, so nothing is removed
    assert strip_page_artifacts(text, "MSFT") == text
    # For AAPL, only the lone header line goes; the sentence containing the name stays
    assert strip_page_artifacts(text, "AAPL") == "Apple Inc. announced a new product.\nBody line"
