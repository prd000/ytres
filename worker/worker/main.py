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

# load_dotenv must run before any worker.* import so that LANGCHAIN_API_KEY
# and other env vars are present when worker.config is first imported.
from dotenv import load_dotenv
load_dotenv()

from worker.log_config import setup_logging
from worker.db import get_pool, close_pool
from worker.loop import run
from worker.observability import check_langsmith, flush_traces


def _make_worker_id() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


async def _main() -> None:
    setup_logging()
    log = logging.getLogger(__name__)

    # LangSmith auth probe — must be after setup_logging. Turns a silent 403 into
    # one loud, explained ERROR line instead of per-job WARNING noise.
    check_langsmith()

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
        await loop.run_in_executor(None, flush_traces)
        log.info("worker stopped: %s", worker_id)


if __name__ == "__main__":
    asyncio.run(_main())
