"""Offline tests for conflict/conflict_analyzer.py — fake section files, LLM call stubbed out."""

import json

import pytest

import conflict.conflict_analyzer as ca


@pytest.fixture
def fake_sections(tmp_path, monkeypatch):
    """Point the analyzer at a temp folder and return a helper that writes AAPL section files."""
    monkeypatch.setattr(ca, "PROCESSED_DATA_DIR", str(tmp_path))

    def write(year: int, text: str, section: str = "Item 1A"):
        path = tmp_path / f"AAPL_{year}_sections.json"
        path.write_text(json.dumps({"ticker": "AAPL", "year": year, "sections": {section: text}}))

    return write


# ── Pair generation (real analyze_conflicts, stubbed LLM + sleep) ────────────

@pytest.mark.parametrize("start, end, expected_pairs", [(2020, 2021, 1), (2020, 2022, 3), (2020, 2024, 10)])
def test_pair_count_and_order(monkeypatch, start, end, expected_pairs):
    seen, sleeps = [], []
    monkeypatch.setattr(ca, "_load_section_text", lambda *args, **kwargs: "text")
    monkeypatch.setattr(ca.time, "sleep", lambda seconds: sleeps.append(seconds))

    def fake_analyze_pair(company, section, year_a, year_b, text_a, text_b, logger=None):
        seen.append((year_a, year_b))
        return {"conflict_count": 0}

    monkeypatch.setattr(ca, "analyze_pair", fake_analyze_pair)

    results = ca.analyze_conflicts("Apple", "Item 1A", start, end)

    assert len(results) == expected_pairs
    assert all(a < b for a, b in seen)
    assert len(set(seen)) == expected_pairs
    assert sleeps == [ca.INTER_CALL_DELAY] * (expected_pairs - 1)


# ── Loading section text ─────────────────────────────────────────────────────

def test_invalid_section_raises_value_error(fake_sections):
    fake_sections(2020, "some risk text")
    with pytest.raises(ValueError):
        ca._load_section_text("Apple", "Item 99", 2020)


def test_invalid_company_raises_key_error(fake_sections):
    with pytest.raises(KeyError):
        ca._load_section_text("Tesla", "Item 1A", 2020)


def test_short_section_is_untouched(fake_sections):
    fake_sections(2020, "short risk text")
    assert ca._load_section_text("Apple", "Item 1A", 2020) == "short risk text"


def test_long_section_is_cut_to_word_cap(fake_sections):
    # KNOWN BUG 2 (docs/V2_POLISH_PLAN.md): real sections are far longer than the cap, so
    # the analyzer sees only the first MAX_WORDS_PER_YEAR words. This records today's
    # behaviour; the fix and its measured before/after belong to V3.
    fake_sections(2020, " ".join(f"w{i}" for i in range(ca.MAX_WORDS_PER_YEAR + 500)))
    text = ca._load_section_text("Apple", "Item 1A", 2020)
    assert len(text.split()) == ca.MAX_WORDS_PER_YEAR


# ── Word-overlap helper ──────────────────────────────────────────────────────

def test_word_overlap():
    assert ca._word_overlap("supply chain concentration risk", "supply chain concentration risk") == 1.0
    assert ca._word_overlap("", "some source text here") == 0.0
    assert ca._word_overlap("quantum physics thermodynamics", "apple revenue iphone sales") < 0.20
    partial = ca._word_overlap("supply concentration thermodynamics", "supply concentration risk")
    assert 0.0 < partial < 1.0
