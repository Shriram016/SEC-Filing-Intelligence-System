"""Offline tests for ingestion/section_detector.py — fake filings built in code, no data/ needed."""

from ingestion.section_detector import extract_sections, find_section_starts

ORDER = ["Item 1", "Item 1A", "Item 2", "Item 7", "Item 7A", "Item 8"]
GAP = 60  # larger than MIN_SECTION_GAP (50), so real headings are far apart


def header(item: str, with_title: bool) -> str:
    return f"{item}. Some Title" if with_title else f"{item}."


def build(items, with_title, prefix=None):
    """Return (lines, positions): each heading followed by GAP body lines."""
    lines = list(prefix or [])
    positions = {}
    for item in items:
        positions[item] = len(lines)
        lines.append(header(item, with_title))
        lines.extend(f"{item} text {i}" for i in range(GAP))
    return lines, positions


def test_format_a_headings_found():
    lines, pos = build(ORDER, with_title=True)
    assert find_section_starts(lines) == pos


def test_format_b_skips_table_of_contents():
    toc = [header(item, with_title=False) for item in ORDER]  # bunched together at the top
    lines, pos = build(ORDER, with_title=False, prefix=toc)
    starts = find_section_starts(lines)
    assert starts == pos
    assert all(start >= len(toc) for start in starts.values())


def test_sections_stop_at_the_right_boundaries():
    lines, _ = build(ORDER, with_title=True)
    sections = extract_sections(lines, find_section_starts(lines))
    assert set(sections) == {"Item 1", "Item 1A", "Item 7", "Item 7A"}
    assert sections["Item 1"].startswith("Item 1. Some Title")
    assert "Item 1A" not in sections["Item 1"]
    # Item 1A ends at Item 2, so Items 2-6 (and Item 7) never leak in
    assert "Item 2" not in sections["Item 1A"]
    assert "Item 7" not in sections["Item 1A"]
    assert "Item 8" not in sections["Item 7A"]


def test_missing_section_gives_none():
    lines, _ = build(["Item 1", "Item 1A"], with_title=True)
    starts = find_section_starts(lines)
    assert starts["Item 7"] is None
    sections = extract_sections(lines, starts)
    assert sections["Item 7"] is None
    assert sections["Item 1"] is not None


def test_last_section_runs_to_end_when_item_8_missing():
    lines, _ = build(["Item 7", "Item 7A"], with_title=True)
    sections = extract_sections(lines, find_section_starts(lines))
    assert lines[-1] in sections["Item 7A"]


def test_headings_are_case_insensitive():
    lines = ["ITEM 1A. RISK FACTORS"] + [f"text {i}" for i in range(5)]
    assert find_section_starts(lines)["Item 1A"] == 0
