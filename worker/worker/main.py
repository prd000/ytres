"""
Entry point: python -m worker.main

Sets up logging, initialises the DB pool, installs signal handlers, and runs
the claim/heartbeat/watchdog loop until SIGTERM or SIGINT.
"""
from __future__ import annotations
import asyncio
import logging
import signal
import socket
import uuid

from worker.log_config import setup_logging
from worker.db import get_pool, close_pool
from worker.loop import run


def _make_worker_id() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


async def _main() -> None:
    setup_logging()
    log = logging.getLogger(__name__)

    worker_id = _make_worker_id()
    log.info("worker starting: %s", worker_id)

    await get_pool()

    cancel_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _shutdown() -> None:
        log.info("shutdown signal received")
        cancel_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown)

    try:
        await run(worker_id, cancel_event)
    finally:
        await close_pool()
        log.info("worker stopped: %s", worker_id)


if __name__ == "__main__":
    asyncio.run(_main())
