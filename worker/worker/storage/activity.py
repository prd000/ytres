"""
Worker-side writes to worker_activity and subtopics.status.

The worker bypasses RLS (asyncpg direct connection) and owns all data writes
for the research pipeline. The web owns status transitions triggered by user
actions (see decisions.md Decision 4).
"""
from __future__ import annotations
import asyncpg


async def upsert_activity(
    conn: asyncpg.Connection,
    *,
    subtopic_id: str,
    project_id: str,
    latest_activity: str,
    sources_stored: int,
    status: str,
    why_nothing_report: str | None = None,
) -> None:
    """Insert or update the worker_activity row for a subtopic.

    Uses ON CONFLICT (subtopic_id) DO UPDATE so callers can write progress
    updates without managing whether the row already exists.
    """
    await conn.execute(
        """
        INSERT INTO worker_activity
            (subtopic_id, project_id, latest_activity, sources_stored, status, why_nothing_report)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5::subtopic_status, $6)
        ON CONFLICT (subtopic_id) DO UPDATE SET
            latest_activity    = EXCLUDED.latest_activity,
            sources_stored     = EXCLUDED.sources_stored,
            status             = EXCLUDED.status,
            why_nothing_report = COALESCE(EXCLUDED.why_nothing_report, worker_activity.why_nothing_report),
            updated_at         = now()
        """,
        subtopic_id,
        project_id,
        latest_activity,
        sources_stored,
        status,
        why_nothing_report,
    )


async def set_subtopic_status(
    conn: asyncpg.Connection,
    subtopic_id: str,
    status: str,
) -> None:
    """Update subtopics.status (enum: queued/running/complete/failed/cancelled)."""
    await conn.execute(
        "UPDATE subtopics SET status = $1::subtopic_status WHERE id = $2::uuid",
        status,
        subtopic_id,
    )
