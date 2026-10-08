"""Offline tests for ingestion/chunker.py — fake sections built in code, no data/ needed."""

from ingestion.chunker import CHUNK_SIZE, MIN_CHUNK, chunk_section


def make_text(n_sentences: int) -> str:
    """n sentences of exactly 10 words each, e.g. 'Alpha7 word word word word word word word word end.'"""
    return " ".join(f"Alpha{i} " + "word " * 8 + "end." for i in range(n_sentences))


def test_short_text_stays_one_chunk():
    assert chunk_section("One. Two. Three.") == ["One. Two. Three."]


def test_empty_text_gives_no_chunks():
    assert chunk_section("") == []
    assert chunk_section("   ") == []


def test_chunks_are_not_much_over_chunk_size():
    chunks = chunk_section(make_text(100))
    assert len(chunks) >= 3
    # a merged tail can add up to MIN_CHUNK words on top of CHUNK_SIZE
    assert all(len(c.split()) <= CHUNK_SIZE + MIN_CHUNK for c in chunks)


def test_every_chunk_ends_at_a_sentence_boundary():
    chunks = chunk_section(make_text(100))
    assert all(c[-1] in ".!?" for c in chunks)


def test_neighbouring_chunks_overlap_and_nothing_is_lost():
    chunks = chunk_section(make_text(100))
    for previous, current in zip(chunks, chunks[1:]):
        first_word_of_current = current.split()[0]  # e.g. 'Alpha25'
        assert first_word_of_current in previous.split()
    for i in range(100):
        assert any(f"Alpha{i} " in c for c in chunks)


def test_tiny_tail_is_merged_into_previous_chunk():
    text = make_text(31)  # 310 words: 30 sentences fill chunk 1, 1 sentence (10 words) is left over
    merged = chunk_section(text, overlap=0)
    assert len(merged) == 1
    assert len(merged[0].split()) == 310

    unmerged = chunk_section(text, overlap=0, min_chunk=0)
    assert len(unmerged) == 2
    assert len(unmerged[1].split()) == 10
