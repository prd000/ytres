"""
Integration tests for worker.storage.store — requires a running local Supabase
stack with migrations applied (supabase start + supabase db push).
"""
from __future__ import annotations
import pytest
import asyncpg

from worker.storage.chunking import Chunk
from worker.storage.store import store_source, store_chunks

from tests.conftest import _seed_user, _seed_project, _seed_subtopic


async def test_store_source_insert_returns_created_true(db: asyncpg.Connection):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    sub_id = await _seed_subtopic(db, pid)

    source_id, created = await store_source(
        db,
        project_id=pid,
        subtopic_id=sub_id,
        url="https://example.com/paper",
        title="Test Paper",
        full_text="Full content here.",
        tier="academic",
        key_takeaway="A useful finding.",
        score_relevance=4.0,
        score_credibility=4.0,
        score_uniqueness=3.0,
        score_actionability=3.5,
    )

    assert source_id
    assert created is True


async def test_store_source_duplicate_url_returns_created_false(db: asyncpg.Connection):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    sub_id = await _seed_subtopic(db, pid)

    url = "https://example.com/dup-paper"
    id1, created1 = await store_source(
        db, project_id=pid, subtopic_id=sub_id, url=url,
        title="Paper", full_text="", tier="academic",
    )
    id2, created2 = await store_source(
        db, project_id=pid, subtopic_id=sub_id, url=url,
        title="Paper Again", full_text="", tier="academic",
    )

    assert id1 == id2
    assert created1 is True
    assert created2 is False


async def test_store_source_idempotent_subtopic_link(db: asyncpg.Connection):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    sub_id = await _seed_subtopic(db, pid)

    url = "https://example.com/idempotent"
    # Store twice — second should not raise from ON CONFLICT DO NOTHING
    await store_source(db, project_id=pid, subtopic_id=sub_id, url=url, title="T", tier="news")
    await store_source(db, project_id=pid, subtopic_id=sub_id, url=url, title="T", tier="news")

    row = await db.fetchrow(
        "SELECT count(*) AS n FROM source_subtopics WHERE subtopic_id = $1",
        sub_id,
    )
    assert int(row["n"]) == 1


async def test_store_chunks_writes_rows_with_embeddings(db: asyncpg.Connection):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    sub_id = await _seed_subtopic(db, pid)
    source_id, _ = await store_source(
        db, project_id=pid, subtopic_id=sub_id,
        url="https://example.com/chunks", title="Chunked Source", tier="industry",
    )

    dims = 1536
    chunks = [
        Chunk(text="First chunk of text.", chunk_index=0, token_count=5),
        Chunk(text="Second chunk of text.", chunk_index=1, token_count=5),
    ]
    embeddings = [[0.1] * dims, [0.2] * dims]

    count = await store_chunks(db, source_id, pid, chunks, embeddings)
    assert count == 2

    rows = await db.fetch(
        "SELECT chunk_index, token_count, content, embedding FROM source_chunks WHERE source_id = $1",
        source_id,
    )
    assert len(rows) == 2
    indices = {int(r["chunk_index"]) for r in rows}
    assert indices == {0, 1}
    for row in rows:
        assert row["embedding"] is not None
        assert row["token_count"] == 5


async def test_store_chunks_empty_list(db: asyncpg.Connection):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    sub_id = await _seed_subtopic(db, pid)
    source_id, _ = await store_source(
        db, project_id=pid, subtopic_id=sub_id,
        url="https://example.com/nochunks", title="No Chunks", tier="government",
    )
    count = await store_chunks(db, source_id, pid, [], [])
    assert count == 0
