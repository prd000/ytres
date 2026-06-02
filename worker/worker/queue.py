"""
Thin async wrappers around the Postgres queue RPCs.
All claim/heartbeat/complete/fail logic lives in SQL (see 0006_rpc.sql);
these wrappers keep the Python side thin and testable.
"""
from __future__ import annotations
import asyncpg
from typing import Any
from worker.db import get_pool


async def claim_job(worker_id: str) -> dict[str, Any] | None:
    """Claim the oldest queued job. Returns None if the queue is empty."""
    pool = await get_pool()
    row = await pool.fetchrow("select * from claim_job($1)", worker_id)
    return dict(row) if row else None


async def heartbeat_job(job_id: str, payload: dict[str, Any] | None = None) -> str | None:
    """
    Bump heartbeat_at; optionally checkpoint payload.
    Returns the current job status so the caller can detect a cancellation flip.
    """
    pool = await get_pool()
    # payload is passed as a dict (or None); the pool's jsonb codec encodes it.
    # None binds as SQL NULL, preserving heartbeat_job's coalesce() semantics.
    row = await pool.fetchrow("select status from heartbeat_job($1, $2)", job_id, payload)
    return str(row["status"]) if row else None


async def complete_job(job_id: str) -> None:
    pool = await get_pool()
    await pool.execute("select complete_job($1::uuid)", job_id)


async def fail_job(job_id: str, error: str) -> None:
    pool = await get_pool()
    await pool.execute("select fail_job($1::uuid, $2)", job_id, error)


async def reclaim_stale_jobs(timeout_seconds: int) -> None:
    pool = await get_pool()
    await pool.execute("select reclaim_stale_jobs($1)", timeout_seconds)


async def cancel_project_jobs(project_id: str) -> None:
    pool = await get_pool()
    await pool.execute("select cancel_project_jobs($1::uuid)", project_id)


async def enqueue_ready_coordinator_reviews() -> int:
    """Call the barrier RPC; returns the number of coordinator_review jobs enqueued."""
    pool = await get_pool()
    row = await pool.fetchrow("select enqueue_ready_coordinator_reviews()")
    return int(row[0]) if row else 0


async def complete_research(project_id: str) -> None:
    """Transition project status researching → complete via the SECURITY DEFINER RPC."""
    pool = await get_pool()
    await pool.execute("select complete_research($1::uuid)", project_id)


async def enqueue_job(
    conn: asyncpg.Connection,
    project_id: str,
    job_type: str,
    payload: dict,
) -> str:
    """Insert a new job row via an existing connection and return its id.

    Accepts a connection (not the pool) so callers can enqueue within an
    existing transaction context. Used by handlers to enqueue continuation jobs
    (e.g. context-window handoff in the research pipeline).
    """
    row = await conn.fetchrow(
        "INSERT INTO jobs (project_id, type, payload) VALUES ($1::uuid, $2, $3) RETURNING id",
        project_id,
        job_type,
        payload,
    )
    return str(row["id"])
