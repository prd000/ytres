"""
Integration tests for the queue RPCs.

Requires a running local Supabase stack with migrations applied.
Run: pytest worker/tests/ (from repo root, with SUPABASE_DB_URL set).

Key invariants verified:
  - SKIP LOCKED: concurrent claims yield distinct job ids, none double-claimed.
  - Claim marks running, increments attempts, sets claim fields.
  - Heartbeat advances heartbeat_at, persists checkpoint payload, returns status.
  - Stale reclaim → queued (or failed at max_attempts).
  - Idempotent resume: crash simulation → reclaim → re-claim picks up checkpointed payload.
  - Cancellation: cancel_project_jobs flips queued/running jobs; heartbeat returns 'cancelled'.
"""
from __future__ import annotations
import asyncio
import json
import uuid
import pytest
import asyncpg

from tests.conftest import _seed_user, _seed_project, _enqueue_job


# ── Claim correctness ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_claim_marks_running_and_increments_attempts(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            uid = await _seed_user(conn)
            pid = await _seed_project(conn, uid)
            jid = await _enqueue_job(conn, pid)

            row = await conn.fetchrow("select * from claim_job('worker-1')")
            assert row is not None
            assert str(row["id"]) == jid
            assert row["status"] == "running"
            assert row["attempts"] == 1
            assert row["claimed_by"] == "worker-1"
            assert row["claimed_at"] is not None
            assert row["heartbeat_at"] is not None

            raise Exception("rollback")  # keep test isolated


@pytest.mark.asyncio
async def test_claim_empty_queue_returns_none(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("select * from claim_job('worker-x')")
            assert row is None
            raise Exception("rollback")


@pytest.mark.asyncio
async def test_concurrent_claims_are_distinct(pool: asyncpg.Pool):
    """N concurrent claim_job calls on N jobs must yield N distinct job ids."""
    n = 5
    async with pool.acquire() as setup_conn:
        async with setup_conn.transaction():
            uid = await _seed_user(setup_conn)
            pid = await _seed_project(setup_conn, uid)
            job_ids = {await _enqueue_job(setup_conn, pid, payload={"message": f"job{i}"}) for i in range(n)}

            # Claim all jobs concurrently from separate connections
            async def claim_one(worker_id: str) -> str | None:
                async with pool.acquire() as c:
                    row = await c.fetchrow("select * from claim_job($1)", worker_id)
                    return str(row["id"]) if row else None

            claimed = await asyncio.gather(*[claim_one(f"w{i}") for i in range(n)])
            claimed_ids = [c for c in claimed if c is not None]

            assert len(claimed_ids) == n, "all jobs should be claimed"
            assert len(set(claimed_ids)) == n, "no double-claims"
            assert set(claimed_ids) == job_ids

            raise Exception("rollback")


# ── Heartbeat ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_heartbeat_advances_timestamp_and_checkpoints(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            uid = await _seed_user(conn)
            pid = await _seed_project(conn, uid)
            jid = await _enqueue_job(conn, pid, payload={"message": "hi"})

            await conn.execute("select * from claim_job('worker-hb')")

            checkpoint = {"message": "hi", "progress": "step_1"}
            row = await conn.fetchrow(
                "select * from heartbeat_job($1::uuid, $2::jsonb)",
                jid,
                json.dumps(checkpoint),
            )
            assert row["status"] == "running"

            job = await conn.fetchrow("select * from jobs where id = $1::uuid", jid)
            assert json.loads(job["payload"]) == checkpoint

            raise Exception("rollback")


@pytest.mark.asyncio
async def test_heartbeat_returns_cancelled_status(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            uid = await _seed_user(conn)
            pid = await _seed_project(conn, uid)
            jid = await _enqueue_job(conn, pid)

            await conn.execute("select * from claim_job('w-cancel')")

            # Cancel the job directly
            await conn.execute(
                "update jobs set status = 'cancelled' where id = $1::uuid", jid
            )

            row = await conn.fetchrow(
                "select * from heartbeat_job($1::uuid)", jid
            )
            assert row["status"] == "cancelled"

            raise Exception("rollback")


# ── Stale reclaim ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reclaim_stale_jobs_requeues_under_max_attempts(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            uid = await _seed_user(conn)
            pid = await _seed_project(conn, uid)
            jid = await _enqueue_job(conn, pid, max_attempts=3)

            # Simulate a claimed job with a stale heartbeat
            await conn.execute(
                """
                update jobs set
                  status = 'running',
                  attempts = 1,
                  claimed_by = 'dead-worker',
                  heartbeat_at = now() - interval '120 seconds'
                where id = $1::uuid
                """,
                jid,
            )

            await conn.execute("select reclaim_stale_jobs(90)")

            job = await conn.fetchrow("select * from jobs where id = $1::uuid", jid)
            assert job["status"] == "queued"
            assert job["claimed_by"] is None

            raise Exception("rollback")


@pytest.mark.asyncio
async def test_reclaim_stale_jobs_fails_at_max_attempts(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            uid = await _seed_user(conn)
            pid = await _seed_project(conn, uid)
            jid = await _enqueue_job(conn, pid, max_attempts=1)

            await conn.execute(
                """
                update jobs set
                  status = 'running',
                  attempts = 1,
                  heartbeat_at = now() - interval '120 seconds'
                where id = $1::uuid
                """,
                jid,
            )

            await conn.execute("select reclaim_stale_jobs(90)")

            job = await conn.fetchrow("select * from jobs where id = $1::uuid", jid)
            assert job["status"] == "failed"

            raise Exception("rollback")


# ── Idempotent resume ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_idempotent_resume_from_checkpoint(pool: asyncpg.Pool):
    """Claim → checkpoint → simulate crash → reclaim → re-claim picks up checkpointed payload."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            uid = await _seed_user(conn)
            pid = await _seed_project(conn, uid)
            jid = await _enqueue_job(conn, pid, payload={"message": "resume-test"})

            # Step 1: claim and checkpoint progress
            await conn.execute("select * from claim_job('worker-a')")
            checkpoint = {"message": "resume-test", "progress": "step_1"}
            await conn.execute(
                "select heartbeat_job($1::uuid, $2::jsonb)",
                jid,
                json.dumps(checkpoint),
            )

            # Step 2: simulate crash (stale heartbeat)
            await conn.execute(
                "update jobs set heartbeat_at = now() - interval '120 seconds' where id = $1::uuid",
                jid,
            )
            await conn.execute("select reclaim_stale_jobs(90)")

            # Step 3: re-claim — payload should still have the checkpoint
            row = await conn.fetchrow("select * from claim_job('worker-b')")
            assert row is not None
            assert str(row["id"]) == jid
            payload = json.loads(row["payload"])
            assert payload["progress"] == "step_1", "checkpoint payload must survive reclaim"

            raise Exception("rollback")


# ── Cancellation propagation ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_project_jobs_cancels_queued_and_running(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            uid = await _seed_user(conn)
            pid = await _seed_project(conn, uid)

            jid_q = await _enqueue_job(conn, pid)
            jid_r = await _enqueue_job(conn, pid)

            # Mark one as running
            await conn.execute(
                "update jobs set status = 'running', heartbeat_at = now() where id = $1::uuid",
                jid_r,
            )

            await conn.execute("select cancel_project_jobs($1::uuid)", pid)

            rows = await conn.fetch("select id, status from jobs where project_id = $1::uuid", pid)
            assert all(r["status"] == "cancelled" for r in rows)

            raise Exception("rollback")
