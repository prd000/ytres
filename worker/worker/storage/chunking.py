"""
Fixed-size text chunking with token overlap.

Pure module — no I/O, no DB, fully unit-testable. Uses tiktoken cl100k_base
(same tokeniser as OpenAI text-embedding-3-small).
"""
from __future__ import annotations
from dataclasses import dataclass

import tiktoken


@dataclass
class Chunk:
    text: str
    chunk_index: int
    token_count: int


def _get_encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Return the number of cl100k_base tokens in text."""
    return len(_get_encoding().encode(text))


def chunk_text(
    text: str,
    *,
    chunk_tokens: int = 500,
    overlap_tokens: int = 100,
) -> list[Chunk]:
    """Split text into overlapping fixed-size chunks.

    Args:
        text: Input text to chunk.
        chunk_tokens: Max tokens per chunk.
        overlap_tokens: Token overlap between consecutive chunks.

    Returns:
        List of Chunk objects; empty list if text is empty.

    Raises:
        ValueError: If overlap_tokens >= chunk_tokens.
    """
    if overlap_tokens >= chunk_tokens:
        raise ValueError(
            f"overlap_tokens ({overlap_tokens}) must be less than chunk_tokens ({chunk_tokens})"
        )
    if not text:
        return []

    enc = _get_encoding()
    tokens = enc.encode(text)
    if not tokens:
        return []

    stride = chunk_tokens - overlap_tokens
    chunks: list[Chunk] = []
    i = 0
    chunk_index = 0

    while i < len(tokens):
        end = min(i + chunk_tokens, len(tokens))
        chunk_token_ids = tokens[i:end]
        chunk_str = enc.decode(chunk_token_ids)
        chunks.append(Chunk(
            text=chunk_str,
            chunk_index=chunk_index,
            token_count=len(chunk_token_ids),
        ))
        if end == len(tokens):
            break
        i += stride
        chunk_index += 1

    return chunks
