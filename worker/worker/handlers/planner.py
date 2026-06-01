"""
Planner handler — job type 'generate_plan'.

Reads the project's research question, calls the DeepSeek coordinator LLM
to produce a structured research plan (3–8 subtopics), then writes the
subtopics to the database in a single transaction (delete-then-insert makes
this idempotent for both first-plan and regenerate paths).

The web sets project.status = 'planning' on enqueue. This handler never
mutates project.status — subtopic presence signals readiness to the UI.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

import asyncpg

from worker.db import get_pool
from worker.llm.config import LLMConfig
from worker.llm.factory import build_chat_model, invoke_structured
from worker.llm.schemas import ResearchPlan

if TYPE_CHECKING:
    from worker.loop import JobContext

log = logging.getLogger(__name__)


def _build_messages(
    research_question: str,
    source_tier_settings: dict,
    feedback: str | None,
) -> list:
    """Construct coordinator messages for the plan-generation prompt."""
    enabled_tiers = [
        tier
        for tier in ["academic", "government", "news", "industry", "social_media"]
        if source_tier_settings.get(tier) or source_tier_settings.get(
            # Handle both snake_case and camelCase keys stored in JSONB
            "socialMedia" if tier == "social_media" else tier, False
        )
    ]
    tiers_str = ", ".join(enabled_tiers) if enabled_tiers else "any source type"

    system = (
        "You are a research coordinator. Decompose the given research question into "
        "3 to 8 non-overlapping subtopics that together comprehensively cover it.\n\n"
        "For each subtopic provide:\n"
        "- title: a concise descriptive title\n"
        "- information_objective: a concrete statement of what specific information "
        "  to gather (1–2 sentences)\n"
        "- source_tier_preferences: 1–3 source tiers from the enabled tiers below\n\n"
        f"Enabled source tiers: {tiers_str}\n\n"
        "Subtopics must be distinct and non-overlapping. Respond with a valid JSON "
        "object matching the ResearchPlan schema."
    )

    user_lines = [f"Research question: {research_question}"]
    if feedback:
        user_lines.append(
            f"\nThe user has reviewed the prior plan and provided this feedback. "
            f"Revise the plan accordingly:\n{feedback}"
        )

    return [
        ("system", system),
        ("human", "\n".join(user_lines)),
    ]


async def handle(ctx: "JobContext") -> dict:
    payload: dict = dict(ctx.job["payload"])
    project_id: str = payload["project_id"]
    feedback: str | None = payload.get("feedback")

    # 1. Early cancellation check
    if ctx.is_cancelled():
        log.info("generate_plan job %s cancelled before start", ctx.job["id"])
        return payload

    # 2. Read project row
    pool = await get_pool()
    async with pool.acquire() as conn:
        project_row = await conn.fetchrow(
            "SELECT research_question, source_tier_settings FROM projects WHERE id = $1::uuid",
            project_id,
        )

    if not project_row:
        raise ValueError(f"Project {project_id!r} not found — cannot generate plan")

    research_question: str = project_row["research_question"]
    source_tier_settings: dict = dict(project_row["source_tier_settings"] or {})

    # 3. Checkpoint
    payload["progress"] = "planning"
    await ctx.checkpoint(payload)

    # 4. Build and invoke LLM
    cfg = LLMConfig.from_env()
    llm = build_chat_model(cfg, "coordinator", tags=["planner", f"project:{project_id}"])
    messages = _build_messages(research_question, source_tier_settings, feedback)

    log.info(
        "generate_plan job %s: invoking coordinator for project %s (feedback=%s)",
        ctx.job["id"],
        project_id,
        bool(feedback),
    )
    plan: ResearchPlan = await invoke_structured(llm, ResearchPlan, messages, "generate_plan")

    # 5. Post-LLM cancellation check — don't write if cancelled after the LLM call
    if ctx.is_cancelled():
        log.info("generate_plan job %s cancelled after LLM call — discarding plan", ctx.job["id"])
        return payload

    # 6. Persist subtopics in a single transaction (delete-then-insert = idempotent)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM subtopics WHERE project_id = $1::uuid",
                project_id,
            )
            for i, sub in enumerate(plan.subtopics):
                # Use text[]::source_tier[] so asyncpg encodes as text[] (known type)
                # and PostgreSQL handles the enum cast.
                await conn.execute(
                    """
                    INSERT INTO subtopics
                        (project_id, title, information_objective,
                         source_tier_preferences, sort_order, status)
                    VALUES ($1::uuid, $2, $3, $4::text[]::source_tier[], $5, 'queued')
                    """,
                    project_id,
                    sub.title,
                    sub.information_objective,
                    list(sub.source_tier_preferences),
                    i,
                )

    log.info(
        "generate_plan job %s: wrote %d subtopics for project %s",
        ctx.job["id"],
        len(plan.subtopics),
        project_id,
    )

    # 7. Final checkpoint
    payload["progress"] = "done"
    payload["subtopic_count"] = len(plan.subtopics)
    await ctx.checkpoint(payload)
    return payload
