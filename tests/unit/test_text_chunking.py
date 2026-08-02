import pytest

from gamecrafter.application.text_chunking import DeterministicTextChunker


def test_chunker_is_repeatable_prefers_paragraphs_and_preserves_exact_offsets() -> None:
    text = "Alpha sentence.\n\nBeta 😀 sentence continues.\nGamma ending."
    chunker = DeterministicTextChunker(max_chars=32, overlap_chars=6)

    first = chunker.split(text)
    second = chunker.split(text)

    assert first == second
    assert first[0].end_offset == text.index("\n\n") + 2
    assert all(chunk.text == text[chunk.start_offset : chunk.end_offset] for chunk in first)
    assert all(len(chunk.text) <= 32 for chunk in first)
    assert all(
        previous.text[-6:] == current.text[:6]
        for previous, current in zip(first, first[1:], strict=False)
    )
    assert len({chunk.chunk_id for chunk in first}) == len(first)


def test_chunker_hard_splits_oversized_text_and_validates_configuration() -> None:
    chunks = DeterministicTextChunker(max_chars=10, overlap_chars=2).split("x" * 23)

    assert [(chunk.start_offset, chunk.end_offset) for chunk in chunks] == [
        (0, 10),
        (8, 18),
        (16, 23),
    ]
    with pytest.raises(ValueError, match="smaller"):
        DeterministicTextChunker(max_chars=10, overlap_chars=10)
    with pytest.raises(ValueError, match="must not be blank"):
        DeterministicTextChunker().split(" \n ")


def test_chunk_id_binds_unicode_text_offsets_and_configuration() -> None:
    text = "异环😀 evidence sentence. Another sentence."

    base = DeterministicTextChunker(max_chars=24, overlap_chars=4).split(text)
    changed_text = DeterministicTextChunker(max_chars=24, overlap_chars=4).split(f"!{text}")
    changed_config = DeterministicTextChunker(max_chars=25, overlap_chars=4).split(text)

    assert base[0].end_offset == len(base[0].text)
    assert base[0].chunk_id != changed_text[0].chunk_id
    assert base[0].chunk_id != changed_config[0].chunk_id
