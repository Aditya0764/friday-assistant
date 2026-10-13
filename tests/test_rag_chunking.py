import pytest

from friday.rag.chunking import chunk_text


def _words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def test_empty_text_gives_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_short_text_is_one_chunk():
    assert chunk_text("hello there friday") == ["hello there friday"]


def test_long_text_splits_with_overlap():
    chunks = chunk_text(_words(1200), size=500, overlap=50)
    assert len(chunks) == 3
    assert len(chunks[0].split()) == 500
    # the last 50 words of one chunk are the first 50 words of the next
    assert chunks[0].split()[-50:] == chunks[1].split()[:50]


def test_every_word_is_covered_and_nothing_is_cut():
    chunks = chunk_text(_words(1200), size=500, overlap=50)
    assert chunks[0].split()[0] == "w0"
    assert chunks[-1].split()[-1] == "w1199"


def test_exact_size_text_is_one_chunk():
    assert len(chunk_text(_words(500), size=500, overlap=50)) == 1


def test_bad_settings_raise():
    with pytest.raises(ValueError):
        chunk_text("a b c", size=10, overlap=10)
    with pytest.raises(ValueError):
        chunk_text("a b c", size=0, overlap=0)