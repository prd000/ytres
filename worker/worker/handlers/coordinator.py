"""
Coordinator handler — job type 'coordinator_review'.

After a research wave completes, this handler reviews coverage against the
project's research objectives. On wave 1 it may spawn a gap-fill round (up to 3
new subtopics + their research_subtopic jobs) then exit without completing the
project. On wave 2 (or wave 1 with no gaps) it calls complete_research().

The two-wave cap is enforced by the barrier RPC (enqueue_ready_coordinator_reviews):
at most one coordinator_review per project is ever enqueued with wave=2.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from worker.db import get_pool
from worker.llm.config import LLMConfig
from worker.llm.factory import build_chat_model, invoke_structured
from worker.llm.schemas import CoverageReview, PlannedSubtopic
from worker.queue import complete_research, enqueue_job

if TYPE_CHECKING:
    from worker.loop import JobContext

log = logging.getLogger(__name__)


async def _load_coverage(conn, project_id: str) -> list[dict]:
    """Load per-subtopic coverage data for the coordinator prompt.

    Returns rows with: id, title, information_objective, status, wave,
    why_nothing_report, sources_stored, takeaways (list of key_takeaway strings).
    """
    rows = await conn.fetch(
        """
        SELECT s.id, s.title, s.information_objective, s.status, s.wave,
               wa.why_nothing_report, wa.sources_stored,
               array_remove(array_agg(src.key_takeaway ORDER BY src.stored_at), NULL) AS takeaways
        FROM subtopics s
        LEFT JOIN worker_activity wa ON wa.subtopic_id = s.id
        LEFT JOIN source_subtopics ss ON ss.subtopic_id = s.id
        LEFT JOIN sources src ON src.id = ss.source_id
        WHERE s.project_id = $1::uuid
        GROUP BY s.id, wa.why_nothing_report, wa.sources_stored
        ORDER BY s.sort_order
        """,
        project_id,
    )
    return [dict(r) for r in rows]


def _build_messages(
    research_question: str,
    source_tier_settings: dict,
    coverage_rows: list[dict],
    wave: int,
) -> list:
    """Build coordinator prompt messages for the coverage review."""
    enabled_tiers = [
        tier
        for tier in ["academic", "government", "news", "industry", "social_media"]
        if source_tier_settings.get(tier) or source_tier_settings.get(
            "socialMedia" if tier == "social_media" else tier, False
        )
    ]
    tiers_str = ", ".join(enabled_tiers) if enabled_tiers else "any source type"

    subtopic_lines = []
    for row in coverage_rows:
        wave_tag = f" [wave={row['wave']}]" if row.get("wave", 0) > 0 else ""
        status = row.get("status") or "unknown"
        takeaways = row.get("takeaways") or []
        why_nothing = row.get("why_nothing_report") or ""
        stored = row.get("sources_stored") or 0

        lines = [f"Subtopic: {row['title']}{wave_tag} (status={status}, sources={stored})"]
        lines.append(f"  Objective: {row['information_objective']}")
        if takeaways:
            for t in takeaways:
                lines.append(f"  - {t}")
        elif why_nothing:
            lines.append(f"  [No sources found: {why_nothing}]")
        else:
            lines.append("  [No sources stored yet]")
        subtopic_lines.append("\n".join(lines))

    coverage_text = "\n\n".join(subtopic_lines)

    if wave == 1:
        gap_instruction = (
            "If coverage is incomplete, propose up to 3 gap subtopics in gap_subtopics "
            "(using the same enabled source tiers). Set is_complete=false. "
            "If coverage is sufficient, set is_complete=true and leave gap_subtopics empty."
        )
    else:
        gap_instruction = (
            "This is the final review (wave 2). Set is_complete=true. "
            "Do not propose gap subtopics — they will be ignored."
        )

    system = (
        "You are a research coordinator reviewing whether a research project has "
        "achieved sufficient coverage of its objectives.\n\n"
        f"Enabled source tiers: {tiers_str}\n\n"
        "For each subtopic you will see its status, the number of sources stored, "
        "and key takeaways from stored sources (or a why-nothing report if none were found).\n\n"
        f"{gap_instruction}\n\n"
        "Write a concise summary (2–4 sentences) of overall coverage quality.\n\n"
        "Respond with a JSON object matching the CoverageReview schema: "
        '{"is_complete": <bool>, "summary": "<str>", "gap_subtopics": [...]}'
    )

    user = (
        f"Research question: {research_question}\n\n"
        f"Coverage per subtopic:\n\n{coverage_text}"
    )

    return [("system", system), ("human", user)]


async def handle(ctx: "JobContext") -> dict:
    payload: dict = dict(ctx.job["payload"])
    project_id: str = payload["project_id"]
    wave: int = int(payload["wave"])

    if ctx.is_cancelled():
        log.info("coordinator_review job %s cancelled before start", ctx.job["id"])
        return payload

    pool = await get_pool()
    async with pool.acquire() as conn:
        project_row = await conn.fetchrow(
            "SELECT research_question, source_tier_settings, status FROM projects WHERE id = $1::uuid",
            project_id,
        )

    if not project_row:
        raise ValueError(f"Project {project_id!r} not found — cannot run coordinator review")

    if project_row["status"] != "researching":
        log.info(
            "coordinator_review job %s: project %s status=%s — skipping",
            ctx.job["id"], project_id, project_row["status"],
        )
        return payload

    research_question: str = project_row["research_question"]
    source_tier_settings: dict = dict(project_row["source_tier_settings"] or {})

    payload["progress"] = "loading_coverage"
    await ctx.checkpoint(payload)

    async with pool.acquire() as conn:
        coverage_rows = await _load_coverage(conn, project_id)

    messages = _build_messages(research_question, source_tier_settings, coverage_rows, wave)

    cfg = LLMConfig.from_env()
    llm = build_chat_model(
        cfg, "coordinator",
        tags=["coordinator", f"project:{project_id}", f"wave:{wave}"],
    )

    payload["progress"] = "reviewing"
    await ctx.checkpoint(payload)

    log.info(
        "coordinator_review job %s: invoking coordinator for project %s (wave=%d, subtopics=%d)",
        ctx.job["id"], project_id, wave, len(coverage_rows),
    )
    review: CoverageReview = await invoke_structured(
        llm, CoverageReview, messages, "coordinator_review"
    )

    if ctx.is_cancelled():
        log.info("coordinator_review job %s cancelled after LLM call", ctx.job["id"])
        return payload

    spawn = (wave == 1) and (not review.is_complete) and bool(review.gap_subtopics)

    if spawn:
        log.info(
            "coordinator_review job %s: spawning %d gap subtopics for project %s",
            ctx.job["id"], len(review.gap_subtopics), project_id,
        )
        async with pool.acquire() as conn:
            async with conn.transaction():
                max_order_row = await conn.fetchrow(
                    "SELECT coalesce(max(sort_order), -1) AS max_order FROM subtopics WHERE project_id = $1::uuid",
                    project_id,
                )
                next_order: int = int(max_order_row["max_order"]) + 1

                for i, sub in enumerate(review.gap_subtopics):
                    sub_row = await conn.fetchrow(
                        """
                        INSERT INTO subtopics
                            (project_id, title, information_objective,
                             source_tier_preferences, sort_order, status, wave)
                        VALUES ($1::uuid, $2, $3, $4::text[]::source_tier[], $5, 'queued', 1)
                        RETURNING id
                        """,
                        project_id,
                        sub.title,
                        sub.information_objective,
                        list(sub.source_tier_preferences),
                        next_order + i,
                    )
                    subtopic_id = str(sub_row["id"])
                    await enqueue_job(
                        conn,
                        project_id,
                        "research_subtopic",
                        {"project_id": project_id, "subtopic_id": subtopic_id},
                    )
    else:
        log.info(
            "coordinator_review job %s: completing project %s (wave=%d, is_complete=%s)",
            ctx.job["id"], project_id, wave, review.is_complete,
        )
        await complete_research(project_id)

    payload["progress"] = "done"
    payload["summary"] = review.summary
    await ctx.checkpoint(payload)
    return payload
