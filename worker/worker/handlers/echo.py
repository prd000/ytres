"""
Echo handler — Phase 1 proof-of-concept.

Reads payload.message, runs a few checkpoint steps with small sleeps
(so heartbeats fire and cancellation is observable mid-run), writes back
an echoed copy, and completes. No LLM or external calls.
"""
import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worker.loop import JobContext

log = logging.getLogger(__name__)

STEPS = ["reading", "processing", "finalising"]


async def handle(ctx: "JobContext") -> dict:
    payload: dict = dict(ctx.job["payload"])
    message: str = payload.get("message", "")

    for step in STEPS:
        if ctx.is_cancelled():
            log.info("echo job %s cancelled at step %s", ctx.job["id"], step)
            return payload

        payload["progress"] = step
        await ctx.checkpoint(payload)
        await asyncio.sleep(0.5)

    payload["echo"] = message
    payload["progress"] = "done"
    await ctx.checkpoint(payload)
    return payload
