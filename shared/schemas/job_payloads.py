"""
Pydantic schemas for job payloads and worker_activity row shapes.

Consumed by the worker (on claim, re-validates defensively) and mirrored/validated
on the TS enqueue path. Add one model per job type as new handlers are built.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


# ── Job payloads ──────────────────────────────────────────────────────────────

class EchoPayload(BaseModel):
    """Payload for the 'echo' job type (Phase 1 proof-of-concept)."""
    message: str
    progress: str | None = None
    echo: str | None = None


# Registry mapping job type names to their payload model.
JOB_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "echo": EchoPayload,
}


# ── worker_activity row shape ──────────────────────────────────────────────────

SubtopicStatus = Literal["queued", "running", "complete", "failed", "cancelled"]


class WorkerActivityRow(BaseModel):
    """Shape of a worker_activity row (contract test target)."""
    subtopic_id: str
    project_id: str
    latest_activity: str
    sources_stored: int
    status: SubtopicStatus
    why_nothing_report: str | None = None
