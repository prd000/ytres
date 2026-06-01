"""
Pytest fixtures for worker integration tests.

Requires a running local Supabase stack (`supabase start`, migrations applied).
Set SUPABASE_DB_URL in the environment (or a .env file in worker/) before running.

Typical local URL: postgresql://postgres:postgres@localhost:54322/postgres
"""
from __future__ import annotations
import os
import uuid
import pytest
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DB_URL: str = os.environ.get(
    "SUPABASE_DB_URL", "postgresql://postgres:postgres@localhost:54322/postgres"
)


@pytest.fixture(scope="session")
async def pool() -> asyncpg.Pool:
    # Imported lazily: worker.db pulls in worker.config, which requires
    # SUPABASE_DB_URL at import time. Deferring keeps collection working when
    # the env var is unset; by the time the pool is built it must be set anyway.
    from worker.db import register_json_codecs

    p = await asyncpg.create_pool(
        DB_URL, min_size=1, max_size=5, init=register_json_codecs
    )
    yield p
    await p.close()


@pytest.fixture
async def db(pool: asyncpg.Pool) -> asyncpg.Connection:
    """Single connection — auto-rollbacks after each test via savepoint."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn
            raise asyncpg.InternalClientError("rollback")  # force rollback


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _seed_user(conn: asyncpg.Connection) -> str:
    """Insert a minimal auth.users row and return its id."""
    uid = str(uuid.uuid4())
    await conn.execute(
        """
        insert into auth.users (id, email, created_at, updated_at, aud, role)
        values ($1, $2, now(), now(), 'authenticated', 'authenticated')
        on conflict do nothing
        """,
        uid,
        f"{uid[:8]}@test.example",
    )
    return uid


async def _seed_project(conn: asyncpg.Connection, owner_id: str) -> str:
    """Insert a minimal project row and return its id."""
    row = await conn.fetchrow(
        """
        insert into projects (owner_id, research_question, status)
        values ($1, 'Test question', 'draft')
        returning id
        """,
        owner_id,
    )
    return str(row["id"])


async def _seed_subtopic(conn: asyncpg.Connection, project_id: str) -> str:
    row = await conn.fetchrow(
        """
        insert into subtopics (project_id, title, information_objective, sort_order)
        values ($1, 'Test subtopic', 'Objective', 0)
        returning id
        """,
        project_id,
    )
    return str(row["id"])


async def _enqueue_job(
    conn: asyncpg.Connection,
    project_id: str,
    job_type: str = "echo",
    payload: dict | None = None,
    max_attempts: int = 3,
) -> str:
    row = await conn.fetchrow(
        """
        insert into jobs (project_id, type, payload, max_attempts)
        values ($1, $2, $3::jsonb, $4)
        returning id
        """,
        project_id,
        job_type,
        payload or {"message": "hello"},  # jsonb codec encodes the dict
        max_attempts,
    )
    return str(row["id"])
