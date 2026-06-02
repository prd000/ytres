"""
Core worker loop — claim, dispatch, heartbeat, watchdog, graceful shutdown.

Design:
  - An asyncio.Semaphore(WORKER_CONCURRENCY) bounds in-flight jobs.
  - The main loop tries to fill capacity: acquire a slot → claim_job → spawn Task.
  - If the queue is empty it releases the slot and sleeps POLL_INTERVAL.
  - Each job Task owns its heartbeat coroutine; a cancellation flip (heartbeat
    returns 'cancelled') sets a per-job Event that handlers check via is_cancelled().
  - A separate watchdog coroutine calls reclaim_stale_jobs every WATCHDOG_INTERVAL.
  - SIGTERM/SIGINT → cancel_event.set() → loop stops claiming → in-flight jobs
    drain within GRACE_SHUTDOWN_SECONDS before the process exits.
"""
from __future__ import annotations
import asyncio
import logging
import traceback
from typing import Any, Callable, Awaitable

from worker.config import (
    WORKER_CONCURRENCY,
    POLL_INTERVAL,
    HEARTBEAT_INTERVAL,
    WATCHDOG_INTERVAL,
    STALE_TIMEOUT_SECONDS,
    GRACE_SHUTDOWN_SECONDS,
    COORDINATOR_SWEEP_INTERVAL,
)
from worker.queue import (
    claim_job,
    heartbeat_job,
    complete_job,
    fail_job,
    reclaim_stale_jobs,
    enqueue_ready_coordinator_reviews,
)
from worker.handlers import HANDLERS

log = logging.getLogger(__name__)


class JobContext:
    """Passed to each handler — provides checkpoint() and is_cancelled()."""

    def __init__(
        self,
        job: dict[str, Any],
        checkpoint: Callable[[dict], Awaitable[None]],
        cancelled: asyncio.Event,
    ) -> None:
        self.job = job
        self._checkpoint = checkpoint
        self._cancelled = cancelled

    async def checkpoint(self, payload: dict) -> None:
        await self._checkpoint(payload)

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()


async def _heartbeat_loop(
    job_id: str,
    cancel_event: asyncio.Event,
    job_cancel_event: asyncio.Event,
) -> None:
    """Runs alongside a job handler; stops when job_cancel_event fires."""
    while not job_cancel_event.is_set() and not cancel_event.is_set():
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        if job_cancel_event.is_set():
            break
        try:
            status = await heartbeat_job(job_id)
            if status == "cancelled":
                log.info("job %s cancelled via heartbeat", job_id)
                job_cancel_event.set()
        except Exception:
            log.exception("heartbeat error for job %s", job_id)


async def _process_job(
    job: dict[str, Any],
    semaphore: asyncio.Semaphore,
    cancel_event: asyncio.Event,
) -> None:
    job_id = str(job["id"])
    job_type = str(job["type"])
    job_cancel_event = asyncio.Event()

    async def checkpoint(payload: dict) -> None:
        await heartbeat_job(job_id, payload)

    ctx = JobContext(job, checkpoint, job_cancel_event)

    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(job_id, cancel_event, job_cancel_event)
    )
    try:
        handler = HANDLERS.get(job_type)
        if handler is None:
            raise ValueError(f"Unknown job type: {job_type!r}")
        await handler(ctx)  # type: ignore[operator]
        await complete_job(job_id)
        log.info("job %s (%s) completed", job_id, job_type)
    except Exception as exc:
        error_detail = traceback.format_exc()
        log.error("job %s (%s) failed: %s", job_id, job_type, exc)
        await fail_job(job_id, error_detail[:2000])
    finally:
        job_cancel_event.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        semaphore.release()


async def _watchdog(cancel_event: asyncio.Event) -> None:
    while not cancel_event.is_set():
        await asyncio.sleep(WATCHDOG_INTERVAL)
        if cancel_event.is_set():
            break
        try:
            await reclaim_stale_jobs(STALE_TIMEOUT_SECONDS)
            log.debug("watchdog: reclaim sweep done")
        except Exception:
            log.exception("watchdog error")


async def _coordinator_sweep(cancel_event: asyncio.Event) -> None:
    while not cancel_event.is_set():
        await asyncio.sleep(COORDINATOR_SWEEP_INTERVAL)
        if cancel_event.is_set():
            break
        try:
            n = await enqueue_ready_coordinator_reviews()
            if n:
                log.info("coordinator sweep: enqueued %d review(s)", n)
        except Exception:
            log.exception("coordinator sweep error")


async def run(worker_id: str, cancel_event: asyncio.Event) -> None:
    """Main loop — runs until cancel_event is set, then drains in-flight jobs."""
    semaphore = asyncio.Semaphore(WORKER_CONCURRENCY)
    in_flight: set[asyncio.Task] = set()

    watchdog_task = asyncio.create_task(_watchdog(cancel_event))
    coordinator_sweep_task = asyncio.create_task(_coordinator_sweep(cancel_event))

    while not cancel_event.is_set():
        any_claimed = False

        # Fill up to concurrency cap
        while not cancel_event.is_set():
            # Non-blocking capacity check
            try:
                await asyncio.wait_for(semaphore.acquire(), timeout=0.05)
            except asyncio.TimeoutError:
                break  # At capacity

            job = await claim_job(worker_id)
            if job is None:
                semaphore.release()
                break  # Queue empty

            any_claimed = True
            task = asyncio.create_task(_process_job(job, semaphore, cancel_event))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)
            log.info("claimed job %s (%s)", job["id"], job["type"])

        if not any_claimed:
            # Nothing to do — wait before next poll
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass

    # Graceful shutdown: stop claiming, drain within the grace window
    log.info("shutting down — draining %d in-flight jobs", len(in_flight))
    watchdog_task.cancel()
    coordinator_sweep_task.cancel()
    if in_flight:
        done, pending = await asyncio.wait(in_flight, timeout=GRACE_SHUTDOWN_SECONDS)
        if pending:
            log.warning("%d jobs did not finish within grace window; reclaim will recover them", len(pending))
            for t in pending:
                t.cancel()
