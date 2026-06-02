"""
Tests for the coordinator handler — LLM and complete_research are mocked.

DB writes (subtopic inserts, job inserts) use the real local PG stack via the
`db` fixture. complete_research is monkeypatched to an AsyncMock so we can assert
call / no-call without touching the projects table (whose status is not 'researching'
in the seeded test data anyway — projects are seeded as 'draft').

To run: from worker/ → pytest tests/test_coordinator.py
Requires: SUPABASE_DB_URL env var + supabase start + migrations through 0011 applied.
"""
from __future__ import annotations
import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
import asyncpg

from worker.loop import JobContext
from worker.llm.schemas import CoverageReview, PlannedSubtopic
import worker.handlers.coordinator as coordinator_module

from tests.conftest import _seed_user, _seed_project, _seed_subtopic, _enqueue_job


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ctx(
    project_id: str,
    wave: int = 1,
    cancelled: bool = False,
) -> tuple[JobContext, list[dict]]:
    job = {
        "id": str(uuid.uuid4()),
        "type": "coordinator_review",
        "payload": {"project_id": project_id, "wave": wave},
    }
    cancel_event = asyncio.Event()
    if cancelled:
        cancel_event.set()
    checkpoints: list[dict] = []

    async def _cp(payload: dict) -> None:
        checkpoints.append(dict(payload))

    return JobContext(job, _cp, cancel_event), checkpoints


def _make_review(is_complete: bool, n_gaps: int = 0) -> CoverageReview:
    gaps = [
        PlannedSubtopic(
            title=f"Gap subtopic {i}",
            information_objective=f"Fill gap {i}",
            source_tier_preferences=["news"],
        )
        for i in range(n_gaps)
    ]
    return CoverageReview(
        is_complete=is_complete,
        summary="Coverage review summary.",
        gap_subtopics=gaps,
    )


def _mock_invoke(review: CoverageReview):
    async def _invoke(llm, schema, messages, run_name):
        return review
    return _invoke


async def _set_project_researching(conn: asyncpg.Connection, project_id: str) -> None:
    await conn.execute(
        "UPDATE projects SET status = 'researching' WHERE id = $1", project_id
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_wave1_gaps_inserts_subtopics_and_jobs(db: asyncpg.Connection, monkeypatch):
    """wave=1 + is_complete=False + 2 gaps → 2 new wave=1 subtopics + 2 research_subtopic jobs."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _seed_subtopic(db, pid)
    await _set_project_researching(db, pid)

    monkeypatch.setattr(coordinator_module, "invoke_structured", _mock_invoke(_make_review(False, 2)))
    complete_mock = AsyncMock()
    monkeypatch.setattr(coordinator_module, "complete_research", complete_mock)

    ctx, _ = _make_ctx(pid, wave=1)
    await coordinator_module.handle(ctx)

    # Two new wave=1 subtopics appended
    gap_rows = await db.fetch(
        "SELECT id, wave, status FROM subtopics WHERE project_id = $1 AND wave = 1", pid
    )
    assert len(gap_rows) == 2
    for row in gap_rows:
        assert row["wave"] == 1
        assert row["status"] == "queued"

    # Two new research_subtopic jobs enqueued
    job_rows = await db.fetch(
        "SELECT type, payload FROM jobs WHERE project_id = $1 AND type = 'research_subtopic'", pid
    )
    assert len(job_rows) == 2

    # complete_research NOT called
    complete_mock.assert_not_called()

    # Project still researching (not completed)
    row = await db.fetchrow("SELECT status FROM projects WHERE id = $1", pid)
    assert row["status"] == "researching"


async def test_wave1_no_gaps_calls_complete_research(db: asyncpg.Connection, monkeypatch):
    """wave=1 + is_complete=True → no new rows, complete_research called."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _seed_subtopic(db, pid)
    await _set_project_researching(db, pid)

    monkeypatch.setattr(coordinator_module, "invoke_structured", _mock_invoke(_make_review(True, 0)))
    complete_mock = AsyncMock()
    monkeypatch.setattr(coordinator_module, "complete_research", complete_mock)

    ctx, _ = _make_ctx(pid, wave=1)
    await coordinator_module.handle(ctx)

    gap_rows = await db.fetch(
        "SELECT id FROM subtopics WHERE project_id = $1 AND wave = 1", pid
    )
    assert len(gap_rows) == 0
    complete_mock.assert_called_once_with(pid)


async def test_wave2_always_completes(db: asyncpg.Connection, monkeypatch):
    """wave=2 even with gaps in review → no gap inserts, complete_research called."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _seed_subtopic(db, pid)
    await _set_project_researching(db, pid)

    # is_complete=False with gaps, but wave=2 → must complete anyway
    monkeypatch.setattr(coordinator_module, "invoke_structured", _mock_invoke(_make_review(False, 3)))
    complete_mock = AsyncMock()
    monkeypatch.setattr(coordinator_module, "complete_research", complete_mock)

    ctx, _ = _make_ctx(pid, wave=2)
    await coordinator_module.handle(ctx)

    gap_rows = await db.fetch(
        "SELECT id FROM subtopics WHERE project_id = $1 AND wave = 1", pid
    )
    assert len(gap_rows) == 0
    complete_mock.assert_called_once_with(pid)


async def test_cancel_before_llm_no_writes(db: asyncpg.Connection, monkeypatch):
    """Cancellation before LLM call → no DB writes, invoke_structured not called."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _seed_subtopic(db, pid)
    await _set_project_researching(db, pid)

    invoke_called = False

    async def spy_invoke(llm, schema, messages, run_name):
        nonlocal invoke_called
        invoke_called = True
        return _make_review(True)

    monkeypatch.setattr(coordinator_module, "invoke_structured", spy_invoke)
    complete_mock = AsyncMock()
    monkeypatch.setattr(coordinator_module, "complete_research", complete_mock)

    ctx, _ = _make_ctx(pid, wave=1, cancelled=True)
    await coordinator_module.handle(ctx)

    assert not invoke_called
    complete_mock.assert_not_called()
    # No gap subtopics or jobs created
    gap_rows = await db.fetch(
        "SELECT id FROM subtopics WHERE project_id = $1 AND wave = 1", pid
    )
    assert len(gap_rows) == 0


async def test_cancel_after_llm_no_writes(db: asyncpg.Connection, monkeypatch):
    """Cancellation after LLM call → no DB writes."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _seed_subtopic(db, pid)
    await _set_project_researching(db, pid)

    ctx, _ = _make_ctx(pid, wave=1)

    async def cancel_after_invoke(llm, schema, messages, run_name):
        ctx._cancelled.set()
        return _make_review(False, 2)

    monkeypatch.setattr(coordinator_module, "invoke_structured", cancel_after_invoke)
    complete_mock = AsyncMock()
    monkeypatch.setattr(coordinator_module, "complete_research", complete_mock)

    await coordinator_module.handle(ctx)

    gap_rows = await db.fetch(
        "SELECT id FROM subtopics WHERE project_id = $1 AND wave = 1", pid
    )
    assert len(gap_rows) == 0
    complete_mock.assert_not_called()


async def test_non_researching_project_skipped(db: asyncpg.Connection, monkeypatch):
    """If project.status != 'researching', handler exits early without LLM call."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)  # status = 'draft'

    invoke_called = False

    async def spy_invoke(llm, schema, messages, run_name):
        nonlocal invoke_called
        invoke_called = True
        return _make_review(True)

    monkeypatch.setattr(coordinator_module, "invoke_structured", spy_invoke)
    complete_mock = AsyncMock()
    monkeypatch.setattr(coordinator_module, "complete_research", complete_mock)

    ctx, _ = _make_ctx(pid, wave=1)
    await coordinator_module.handle(ctx)

    assert not invoke_called
    complete_mock.assert_not_called()


async def test_load_coverage_assembly(db: asyncpg.Connection):
    """_load_coverage returns takeaways from linked sources and why_nothing from worker_activity."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)

    # Subtopic with 2 sources
    sub_id1 = await _seed_subtopic(db, pid)
    # Subtopic with no sources but a why_nothing_report
    sub_id2_row = await db.fetchrow(
        """
        INSERT INTO subtopics (project_id, title, information_objective, sort_order)
        VALUES ($1, 'Barren subtopic', 'Find nothing', 1)
        RETURNING id
        """,
        pid,
    )
    sub_id2 = str(sub_id2_row["id"])

    # Insert 2 sources and link to sub_id1
    for i in range(2):
        src_row = await db.fetchrow(
            """
            INSERT INTO sources
                (project_id, url, title, full_text, tier, key_takeaway,
                 score_relevance, score_credibility, score_uniqueness, score_actionability)
            VALUES ($1, $2, $3, 'Full text', 'news', $4, 4, 4, 4, 4)
            RETURNING id
            """,
            pid,
            f"https://example.com/{i}",
            f"Source {i}",
            f"Takeaway {i}",
        )
        src_id = str(src_row["id"])
        await db.execute(
            "INSERT INTO source_subtopics (source_id, subtopic_id) VALUES ($1, $2)",
            src_id, sub_id1,
        )

    # Insert worker_activity for sub_id2 with why_nothing_report
    await db.execute(
        """
        INSERT INTO worker_activity
            (subtopic_id, project_id, latest_activity, sources_stored, status, why_nothing_report)
        VALUES ($1, $2, 'Searched everywhere', 0, 'complete', 'No relevant sources found.')
        """,
        sub_id2, pid,
    )

    async with (await coordinator_module.get_pool()).acquire() as conn:
        # Re-use the same underlying pool but route through _load_coverage
        # In tests, we call it directly with the transaction connection.
        rows = await coordinator_module._load_coverage(db, pid)

    assert len(rows) == 2
    rich_row = next(r for r in rows if r["id"] == uuid.UUID(sub_id1))
    assert len(rich_row["takeaways"]) == 2

    barren_row = next(r for r in rows if r["id"] == uuid.UUID(sub_id2))
    assert barren_row["why_nothing_report"] == "No relevant sources found."
    assert (barren_row["takeaways"] or []) == []
