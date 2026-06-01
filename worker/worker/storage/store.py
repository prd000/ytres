"""
pgvector storage writes — sources, chunks.

Uses asyncpg directly (bypasses RLS). Vectors are inserted as string-literal
casts ($N::vector) — no codec registration required.
"""
from __future__ import annotations
import logging

import asyncpg

from worker.storage.chunking import Chunk

log = logging.getLogger(__name__)


def _vector_literal(vec: list[float]) -> str:
    """Convert a float list to a pgvector text literal: '[1.0,2.0,...]'."""
    return "[" + ",".join(str(v) for v in vec) + "]"


async def store_source(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    subtopic_id: str,
    url: str,
    title: str,
    full_text: str = "",
    tier: str,
    key_takeaway: str = "",
    score_relevance: float = 0.0,
    score_credibility: float = 0.0,
    score_uniqueness: float = 0.0,
    score_actionability: float = 0.0,
) -> tuple[str, bool]:
    """Upsert a source row and link it to a subtopic.

    The unique(project_id, url) constraint deduplicates across subtopics.
    Returns (source_id, created) where created=True means this is a new row.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO sources (
            project_id, url, title, full_text, tier, key_takeaway,
            score_relevance, score_credibility, score_uniqueness, score_actionability
        )
        VALUES ($1, $2, $3, $4, $5::text::source_tier, $6, $7, $8, $9, $10)
        ON CONFLICT (project_id, url) DO UPDATE SET url = sources.url
        RETURNING id, (xmax = 0) AS created
        """,
        project_id,
        url,
        title,
        full_text,
        tier,
        key_takeaway,
        score_relevance,
        score_credibility,
        score_uniqueness,
        score_actionability,
    )
    source_id = str(row["id"])
    created = bool(row["created"])

    await conn.execute(
        """
        INSERT INTO source_subtopics (source_id, subtopic_id, project_id)
        VALUES ($1, $2, $3)
        ON CONFLICT DO NOTHING
        """,
        source_id,
        subtopic_id,
        project_id,
    )

    return source_id, created


async def store_chunks(
    conn: asyncpg.Connection,
    source_id: str,
    project_id: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> int:
    """Insert source_chunks rows with vector embeddings.

    Uses executemany for efficiency. Returns the number of rows inserted.
    """
    if not chunks:
        return 0

    records = [
        (
            source_id,
            project_id,
            chunk.chunk_index,
            chunk.text,
            _vector_literal(emb),
            chunk.token_count,
        )
        for chunk, emb in zip(chunks, embeddings)
    ]

    await conn.executemany(
        """
        INSERT INTO source_chunks (source_id, project_id, chunk_index, content, embedding, token_count)
        VALUES ($1, $2, $3, $4, $5::vector, $6)
        """,
        records,
    )

    return len(records)
