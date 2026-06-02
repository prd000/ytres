"""
Integration tests for the coordinator barrier RPC and complete_research RPC.

Exercises: enqueue_ready_coordinator_reviews() + complete_research() against
real Postgres via the `db` fixture. Requires migration 0011 applied.

NOTE: No local Supabase on this machine — verified statically; live run pending.
"""
from __future__ import annotations
import pytest
import asyncpg

from tests.conftest import _seed_user, _seed_project, _seed_subtopic, _enqueue_job


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _count_coordinator_jobs(conn: asyncpg.Connection, project_id: str) -> int:
    row = await conn.fetchrow(
        "SELECT count(*) AS n FROM jobs WHERE project_id = $1 AND type = 'coordinator_review'",
        project_id,
    )
    return int(row["n"])


async def _finish_job(conn: asyncpg.Connection, job_id: str) -> None:
    """Mark a job complete (simulate the worker finishing it)."""
    await conn.execute(
        "UPDATE jobs SET status = 'complete', completed_at = now() WHERE id = $1", job_id
    )


async def _fail_job(conn: asyncpg.Connection, job_id: str) -> None:
    """Mark a job failed (terminal state)."""
    await conn.execute(
        "UPDATE jobs SET status = 'failed', completed_at = now() WHERE id = $1", job_id
    )


async def _call_barrier(conn: asyncpg.Connection) -> int:
    row = await conn.fetchrow("SELECT enqueue_ready_coordinator_reviews()")
    return int(row[0])


async def _call_complete_research(conn: asyncpg.Connection, project_id: str) -> None:
    await conn.execute("SELECT complete_research($1::uuid)", project_id)


async def _set_status(conn: asyncpg.Connection, project_id: str, status: str) -> None:
    await conn.execute("UPDATE projects SET status = $1 WHERE id = $2", status, project_id)


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_barrier_enqueues_wave1_when_research_done(db: asyncpg.Connection):
    """After last research_subtopic job completes, barrier enqueues exactly one wave=1 review."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _set_status(db, pid, "researching")

    job_id = await _enqueue_job(
        db, pid, "research_subtopic", {"project_id": pid, "subtopic_id": "x"}
    )
    await _finish_job(db, job_id)

    n = await _call_barrier(db)
    assert n == 1

    count = await _count_coordinator_jobs(db, pid)
    assert count == 1

    # Confirm wave=1
    row = await db.fetchrow(
        "SELECT payload FROM jobs WHERE project_id = $1 AND type = 'coordinator_review'", pid
    )
    assert row["payload"]["wave"] == 1


async def test_barrier_idempotent_wave1(db: asyncpg.Connection):
    """Calling barrier twice does not create a duplicate wave=1 review."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _set_status(db, pid, "researching")

    job_id = await _enqueue_job(
        db, pid, "research_subtopic", {"project_id": pid, "subtopic_id": "x"}
    )
    await _finish_job(db, job_id)

    await _call_barrier(db)
    n = await _call_barrier(db)  # second call — review already pending (status queued)
    assert n == 0

    count = await _count_coordinator_jobs(db, pid)
    assert count == 1


async def test_barrier_waits_while_research_in_flight(db: asyncpg.Connection):
    """Does not enqueue if any research_subtopic job is still queued or running."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _set_status(db, pid, "researching")

    # Job still queued
    await _enqueue_job(db, pid, "research_subtopic", {"project_id": pid, "subtopic_id": "x"})

    n = await _call_barrier(db)
    assert n == 0
    assert await _count_coordinator_jobs(db, pid) == 0


async def test_barrier_fires_when_all_subtopics_failed(db: asyncpg.Connection):
    """If all research jobs failed (terminal), the barrier still fires."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _set_status(db, pid, "researching")

    job_id = await _enqueue_job(
        db, pid, "research_subtopic", {"project_id": pid, "subtopic_id": "x"}
    )
    await _fail_job(db, job_id)

    n = await _call_barrier(db)
    assert n == 1


async def test_barrier_skips_cancelled_project(db: asyncpg.Connection):
    """Cancelled project status → barrier does not enqueue."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _set_status(db, pid, "cancelled")

    job_id = await _enqueue_job(
        db, pid, "research_subtopic", {"project_id": pid, "subtopic_id": "x"}
    )
    await _finish_job(db, job_id)

    n = await _call_barrier(db)
    assert n == 0


async def test_barrier_enqueues_wave2_after_gap_fill_done(db: asyncpg.Connection):
    """After a wave=1 review is done and gap-fill jobs finish, barrier enqueues wave=2."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _set_status(db, pid, "researching")

    # Original research done
    r_job = await _enqueue_job(
        db, pid, "research_subtopic", {"project_id": pid, "subtopic_id": "x"}
    )
    await _finish_job(db, r_job)

    # Wave=1 review created and completed
    await _call_barrier(db)
    rev1 = await db.fetchrow(
        "SELECT id FROM jobs WHERE project_id = $1 AND type = 'coordinator_review'", pid
    )
    await _finish_job(db, str(rev1["id"]))

    # Gap-fill job enqueued and finished
    gap_job = await _enqueue_job(
        db, pid, "research_subtopic", {"project_id": pid, "subtopic_id": "y"}
    )
    await _finish_job(db, gap_job)

    n = await _call_barrier(db)
    assert n == 1

    # Confirm wave=2 enqueued
    rows = await db.fetch(
        "SELECT payload FROM jobs WHERE project_id = $1 AND type = 'coordinator_review' ORDER BY created_at",
        pid,
    )
    assert len(rows) == 2
    assert rows[1]["payload"]["wave"] == 2


async def test_barrier_no_wave3(db: asyncpg.Connection):
    """After wave=2 review exists, barrier never enqueues wave=3."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _set_status(db, pid, "researching")

    r_job = await _enqueue_job(
        db, pid, "research_subtopic", {"project_id": pid, "subtopic_id": "x"}
    )
    await _finish_job(db, r_job)

    # Wave 1
    await _call_barrier(db)
    rev1 = await db.fetchrow(
        "SELECT id FROM jobs WHERE project_id = $1 AND type = 'coordinator_review'", pid
    )
    await _finish_job(db, str(rev1["id"]))

    # Gap fill
    gap_job = await _enqueue_job(
        db, pid, "research_subtopic", {"project_id": pid, "subtopic_id": "y"}
    )
    await _finish_job(db, gap_job)

    # Wave 2
    await _call_barrier(db)
    rev2 = await db.fetchrow(
        "SELECT id FROM jobs WHERE project_id = $1 AND type = 'coordinator_review' AND (payload->>'wave')::int = 2",
        pid,
    )
    await _finish_job(db, str(rev2["id"]))

    # Wave 3 should NOT fire
    n = await _call_barrier(db)
    assert n == 0
    count = await _count_coordinator_jobs(db, pid)
    assert count == 2


async def test_complete_research_transitions_status(db: asyncpg.Connection):
    """complete_research() changes status from researching → complete."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    await _set_status(db, pid, "researching")

    await _call_complete_research(db, pid)

    row = await db.fetchrow("SELECT status FROM projects WHERE id = $1", pid)
    assert row["status"] == "complete"


async def test_complete_research_noop_on_non_researching(db: asyncpg.Connection):
    """complete_research() is a no-op if status != 'researching'."""
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)
    # Status is 'draft'

    await _call_complete_research(db, pid)

    row = await db.fetchrow("SELECT status FROM projects WHERE id = $1", pid)
    assert row["status"] == "draft"
