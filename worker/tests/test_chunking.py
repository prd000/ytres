"""
Unit tests for worker.storage.chunking — pure, no I/O.
"""
from __future__ import annotations
import pytest

from worker.storage.chunking import chunk_text, count_tokens, Chunk


def test_empty_text_returns_empty():
    assert chunk_text("") == []


def test_short_text_produces_single_chunk():
    text = "Hello world, this is a short sentence."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].token_count > 0
    assert chunks[0].text == text or text in chunks[0].text


def test_token_count_consistent():
    text = "The quick brown fox jumps over the lazy dog."
    chunks = chunk_text(text)
    assert chunks[0].token_count == count_tokens(chunks[0].text)


def test_long_text_produces_multiple_overlapping_chunks():
    # ~1000 tokens of repetitive text
    word = "research "
    text = word * 150
    chunks = chunk_text(text, chunk_tokens=100, overlap_tokens=20)
    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert chunk.token_count <= 100


def test_chunk_indices_are_sequential():
    text = " ".join(["word"] * 600)
    chunks = chunk_text(text, chunk_tokens=50, overlap_tokens=10)
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_overlap_equal_to_chunk_tokens_raises():
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_tokens=100, overlap_tokens=100)


def test_overlap_greater_than_chunk_tokens_raises():
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_tokens=50, overlap_tokens=60)


def test_all_chunks_within_token_limit():
    text = " ".join(["tokenword"] * 500)
    for chunk_tokens, overlap_tokens in [(100, 20), (200, 50), (500, 100)]:
        chunks = chunk_text(text, chunk_tokens=chunk_tokens, overlap_tokens=overlap_tokens)
        for chunk in chunks:
            assert chunk.token_count <= chunk_tokens
