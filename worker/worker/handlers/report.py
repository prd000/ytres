"""
Report handler — job type 'generate_report'.

Steps:
1. Load project (research_question); guard not-found.
2. Select sources:
   - auto:    load every source's {id, title, key_takeaway} scoped to project_id
              → invoke AutoDraftSelection (LLM picks top ≤ REPORT_SOURCE_CAP)
   - curated: use payload.source_ids, server-side capped at REPORT_SOURCE_CAP
3. Load full rows for chosen ids (title, url, key_takeaway, full_text), truncating
   full_text to REPORT_SOURCE_CHARS per source. Scoped to project_id for isolation.
4. invoke_structured(ReportDraft) — markdown with inline citations + References.
5. Validate source_ids_used ⊆ provided set (drop any hallucinated ids).
6. INSERT into reports (markdown, source_refs). Realtime delivers it to the tab.

No project-status change: report generation is independent and repeatable.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from worker.config import REPORT_SOURCE_CAP, REPORT_SOURCE_CHARS
from worker.db import get_pool
from worker.llm.config import LLMConfig
from worker.llm.factory import build_chat_model, invoke_structured
from worker.llm.schemas import AutoDraftSelection, ReportDraft

if TYPE_CHECKING:
    from worker.loop import JobContext

log = logging.getLogger(__name__)


def _build_auto_select_messages(sources: list[dict], cap: int) -> list:
    source_lines = "\n".join(
        f"[{s['id']}] {s['title']}: {s['key_takeaway']}"
        for s in sources
    )
    system = (
        f"You are a research editor. Select up to {cap} sources that together provide "
        "the broadest, highest-quality coverage of the research question. "
        "Return their IDs in selected_source_ids."
    )
    user = f"Available sources:\n{source_lines}"
    return [("system", system), ("human", user)]


def _build_synthesis_messages(
    research_question: str,
    sources: list[dict],
    instructions: str | None,
) -> list:
    source_blocks = []
    for s in sources:
        truncated = (s["full_text"] or "")[:REPORT_SOURCE_CHARS]
        source_blocks.append(
            f"[ID:{s['id']}]\nTitle: {s['title']}\nURL: {s['url']}\n"
            f"Key takeaway: {s['key_takeaway']}\n\n{truncated}"
        )
    sources_text = "\n\n---\n\n".join(source_blocks)

    instruction_note = f"\n\nAdditional instructions: {instructions}" if instructions else ""

    system = (
        "You are a research writer. Synthesize the provided sources into a well-structured "
        "markdown report for the given research question.\n\n"
        "Requirements:\n"
        "- Use inline citations as markdown links: [Author/Title](URL)\n"
        "- Include a ## References section at the end listing all cited sources\n"
        "- Only cite sources from the provided list\n"
        "- Return the full markdown in the `markdown` field\n"
        "- Return the IDs of sources you actually cited in `source_ids_used`"
        f"{instruction_note}"
    )
    user = f"Research question: {research_question}\n\nSources:\n\n{sources_text}"
    return [("system", system), ("human", user)]


async def handle(ctx: "JobContext") -> dict:
    payload: dict = dict(ctx.job["payload"])
    project_id: str = payload["project_id"]
    mode: str = payload.get("mode", "curated")
    source_ids: list[str] = payload.get("source_ids", [])
    instructions: str | None = payload.get("instructions")

    if ctx.is_cancelled():
        log.info("generate_report job %s cancelled before start", ctx.job["id"])
        return payload

    pool = await get_pool()
    async with pool.acquire() as conn:
        project_row = await conn.fetchrow(
            "SELECT research_question FROM projects WHERE id = $1::uuid",
            project_id,
        )

    if not project_row:
        raise ValueError(f"Project {project_id!r} not found — cannot generate report")

    research_question: str = project_row["research_question"]
    cfg = LLMConfig.from_env()
    llm = build_chat_model(
        cfg, "coordinator",
        tags=["report", f"project:{project_id}", f"mode:{mode}"],
    )

    # ── Step 2: select sources ────────────────────────────────────────────────

    payload["progress"] = "selecting_sources"
    await ctx.checkpoint(payload)

    if mode == "auto":
        async with pool.acquire() as conn:
            all_rows = await conn.fetch(
                "SELECT id, title, key_takeaway FROM sources WHERE project_id = $1::uuid ORDER BY stored_at",
                project_id,
            )
        all_sources = [{"id": str(r["id"]), "title": r["title"], "key_takeaway": r["key_takeaway"]} for r in all_rows]

        if not all_sources:
            raise ValueError(f"Project {project_id!r} has no sources — cannot auto-draft report")

        if ctx.is_cancelled():
            log.info("generate_report job %s cancelled before auto-selection LLM call", ctx.job["id"])
            return payload

        messages = _build_auto_select_messages(all_sources, REPORT_SOURCE_CAP)
        selection: AutoDraftSelection = await invoke_structured(
            llm, AutoDraftSelection, messages, "auto_draft_selection"
        )
        chosen_ids = selection.selected_source_ids[:REPORT_SOURCE_CAP]
    else:
        # curated: trust the client selection but enforce the server-side cap
        chosen_ids = source_ids[:REPORT_SOURCE_CAP]

    if not chosen_ids:
        raise ValueError("No source IDs provided for report generation")

    # ── Step 3: load full source rows (scoped to project_id for isolation) ────

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, title, url, key_takeaway, full_text
            FROM sources
            WHERE id = ANY($1::uuid[]) AND project_id = $2::uuid
            """,
            chosen_ids,
            project_id,
        )
    full_sources = [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "url": r["url"],
            "key_takeaway": r["key_takeaway"],
            "full_text": (r["full_text"] or "")[:REPORT_SOURCE_CHARS],
        }
        for r in rows
    ]
    provided_ids = {s["id"] for s in full_sources}

    if not full_sources:
        raise ValueError("None of the chosen source IDs exist in this project")

    # ── Step 4: synthesize the report ─────────────────────────────────────────

    payload["progress"] = "synthesizing"
    await ctx.checkpoint(payload)

    if ctx.is_cancelled():
        log.info("generate_report job %s cancelled before synthesis LLM call", ctx.job["id"])
        return payload

    log.info(
        "generate_report job %s: synthesizing report for project %s (%d sources, mode=%s)",
        ctx.job["id"], project_id, len(full_sources), mode,
    )

    messages = _build_synthesis_messages(research_question, full_sources, instructions)
    draft: ReportDraft = await invoke_structured(llm, ReportDraft, messages, "report_draft")

    if ctx.is_cancelled():
        log.info("generate_report job %s cancelled after synthesis LLM call", ctx.job["id"])
        return payload

    # ── Step 5: validate source_ids_used ⊆ provided set ─────────────────────

    validated_ids = [sid for sid in draft.source_ids_used if sid in provided_ids]
    if len(validated_ids) != len(draft.source_ids_used):
        dropped = set(draft.source_ids_used) - provided_ids
        log.warning(
            "generate_report job %s: dropped %d hallucinated source IDs: %s",
            ctx.job["id"], len(dropped), dropped,
        )

    # ── Step 6: insert reports row ────────────────────────────────────────────

    async with pool.acquire() as conn:
        report_row = await conn.fetchrow(
            """
            INSERT INTO reports (project_id, markdown, source_refs)
            VALUES ($1::uuid, $2, $3::uuid[])
            RETURNING id
            """,
            project_id,
            draft.markdown,
            validated_ids,
        )

    log.info(
        "generate_report job %s: report %s inserted for project %s (%d sources cited)",
        ctx.job["id"], str(report_row["id"]), project_id, len(validated_ids),
    )

    payload["progress"] = "done"
    payload["report_id"] = str(report_row["id"])
    await ctx.checkpoint(payload)
    return payload
