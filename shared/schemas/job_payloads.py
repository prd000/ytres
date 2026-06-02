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


class GeneratePlanPayload(BaseModel):
    """Payload for the 'generate_plan' job type (Phase 5 planner)."""
    project_id: str
    feedback: str | None = None
    progress: str | None = None


class ResearchSubtopicPayload(BaseModel):
    """Payload for the 'research_subtopic' job type (Phase 6 research pipeline)."""
    project_id: str
    subtopic_id: str
    progress: str | None = None
    checkpoint: dict | None = None  # resume state: processed_urls, stored_count, queries, etc.


class CoordinatorReviewPayload(BaseModel):
    """Payload for the 'coordinator_review' job type (Phase 8 coordinator)."""
    project_id: str
    wave: int
    progress: str | None = None


class GenerateReportPayload(BaseModel):
    """Payload for the 'generate_report' job type (Phase 10 reports)."""
    project_id: str
    mode: Literal["curated", "auto"]
    source_ids: list[str] = []          # curated: user selection; auto: ignored
    instructions: str | None = None     # optional tone/audience/focus
    progress: str | None = None


# Registry mapping job type names to their payload model.
JOB_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "echo": EchoPayload,
    "generate_plan": GeneratePlanPayload,
    "research_subtopic": ResearchSubtopicPayload,
    "coordinator_review": CoordinatorReviewPayload,
    "generate_report": GenerateReportPayload,
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
