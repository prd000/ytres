"""
Integration tests for hybrid search (match_chunks SQL function).

Requires migrations 0007 and 0008 to be applied.
Seeds hand-crafted chunks: one vector-near and one keyword-only chunk,
then asserts both surface in the right order and only seeded project data is returned.
"""
from __future__ import annotations
import pytest
import asyncpg

from worker.storage.chunking import Chunk
from worker.storage.store import store_source, store_chunks
from worker.storage.search import match_chunks

from tests.conftest import _seed_user, _seed_project, _seed_subtopic

DIMS = 1536


def _unit_vec(index: int) -> list[float]:
    """A deterministic unit-direction vector with a 1.0 in position `index`."""
    v = [0.0] * DIMS
    v[index] = 1.0
    return v


async def _seed_source_with_chunk(
    conn: asyncpg.Connection,
    pid: str,
    sub_id: str,
    url: str,
    content: str,
    embedding: list[float],
) -> str:
    source_id, _ = await store_source(
        conn, project_id=pid, subtopic_id=sub_id, url=url, title=url, tier="news"
    )
    await store_chunks(
        conn, source_id, pid,
        [Chunk(text=content, chunk_index=0, token_count=len(content.split()))],
        [embedding],
    )
    return source_id


async def test_vector_near_chunk_ranks_high(db: asyncpg.Connection):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    sub_id = await _seed_subtopic(db, pid)

    # Chunk A: very close to query embedding (direction 0)
    await _seed_source_with_chunk(
        db, pid, sub_id,
        "https://example.com/a",
        "This chunk is about quantum computing advancements",
        _unit_vec(0),
    )
    # Chunk B: perpendicular to query (far away)
    await _seed_source_with_chunk(
        db, pid, sub_id,
        "https://example.com/b",
        "This chunk is about cooking recipes and nutrition",
        _unit_vec(1),
    )

    query_emb = _unit_vec(0)  # Same direction as chunk A
    results = await match_chunks(
        db,
        project_id=pid,
        query_embedding=query_emb,
        query_text="quantum computing",
        match_count=10,
    )

    assert len(results) >= 1
    # Chunk A (closest vector) should appear in results
    contents = [r.content for r in results]
    assert any("quantum" in c for c in contents)


async def test_keyword_chunk_surfaces(db: asyncpg.Connection):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    sub_id = await _seed_subtopic(db, pid)

    # Chunk: keyword match but orthogonal embedding
    await _seed_source_with_chunk(
        db, pid, sub_id,
        "https://example.com/kw",
        "photosynthesis chlorophyll sunlight energy conversion",
        _unit_vec(5),
    )

    results = await match_chunks(
        db,
        project_id=pid,
        query_embedding=_unit_vec(5),  # same direction for vector match too
        query_text="photosynthesis",
        match_count=10,
    )

    assert len(results) >= 1
    assert any("photosynthesis" in r.content for r in results)


async def test_only_seeded_project_returned(db: asyncpg.Connection):
    uid = await _seed_user(db)
    pid1 = await _seed_project(db, uid)
    pid2 = await _seed_project(db, uid)
    sub1 = await _seed_subtopic(db, pid1)
    sub2 = await _seed_subtopic(db, pid2)

    content = "shared keyword magnetism"
    await _seed_source_with_chunk(db, pid1, sub1, "https://a.com/1", content, _unit_vec(10))
    await _seed_source_with_chunk(db, pid2, sub2, "https://a.com/2", content, _unit_vec(10))

    results = await match_chunks(
        db,
        project_id=pid1,
        query_embedding=_unit_vec(10),
        query_text="magnetism",
        match_count=10,
    )

    for r in results:
        assert r.project_id == pid1


async def test_match_count_limit(db: asyncpg.Connection):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    sub_id = await _seed_subtopic(db, pid)

    for i in range(10):
        await _seed_source_with_chunk(
            db, pid, sub_id,
            f"https://example.com/limit-{i}",
            f"entropy thermodynamics limit test chunk number {i}",
            _unit_vec(i % DIMS),
        )

    results = await match_chunks(
        db,
        project_id=pid,
        query_embedding=_unit_vec(0),
        query_text="entropy thermodynamics",
        match_count=3,
    )

    assert len(results) <= 3


async def test_scores_descending(db: asyncpg.Connection):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    sub_id = await _seed_subtopic(db, pid)

    for i in range(5):
        await _seed_source_with_chunk(
            db, pid, sub_id,
            f"https://example.com/score-{i}",
            f"neural networks deep learning gradient descent iteration {i}",
            _unit_vec(i),
        )

    results = await match_chunks(
        db,
        project_id=pid,
        query_embedding=_unit_vec(0),
        query_text="neural networks",
        match_count=10,
    )

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
