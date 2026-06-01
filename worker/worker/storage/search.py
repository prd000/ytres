"""
Hybrid search wrapper — calls the match_chunks SQL function (migration 0008).
"""
from __future__ import annotations
from dataclasses import dataclass

import asyncpg

from worker.storage.store import _vector_literal


@dataclass
class ChunkMatch:
    chunk_id: str
    source_id: str
    project_id: str
    chunk_index: int
    content: str
    token_count: int | None
    score: float


async def match_chunks(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    query_embedding: list[float],
    query_text: str,
    match_count: int = 12,
) -> list[ChunkMatch]:
    """Hybrid vector + keyword search scoped to a single project.

    Calls the match_chunks SQL function which applies Reciprocal Rank Fusion.
    Results are ordered by descending score.
    """
    rows = await conn.fetch(
        "SELECT * FROM match_chunks($1, $2::vector, $3, $4)",
        project_id,
        _vector_literal(query_embedding),
        query_text,
        match_count,
    )
    return [
        ChunkMatch(
            chunk_id=str(row["id"]),
            source_id=str(row["source_id"]),
            project_id=str(row["project_id"]),
            chunk_index=int(row["chunk_index"]),
            content=str(row["content"]),
            token_count=row["token_count"],
            score=float(row["score"]),
        )
        for row in rows
    ]
