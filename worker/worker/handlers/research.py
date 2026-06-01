"""
Research handler — job type 'research_subtopic'.

For each approved subtopic runs the full research pipeline:
  query generation → multi-tier search → pass-1 batch filter → extraction
  → pass-2 per-source evaluation → store quality findings with embeddings
  → report live progress via worker_activity

Supports:
  - Checkpointing / idempotent resume (processed_urls + query_index)
  - 100K-token context-window handoff (enqueues a continuation job and exits)
  - Source cap (12 stored max) and min-target (3) with one auto-retry wave
  - Why-nothing report when 0 sources stored after both waves
  - Cancellation checks before every LLM/search/DB call
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from worker.config import CONTEXT_CEILING_TOKENS
from worker.db import get_pool
from worker.llm.config import LLMConfig
from worker.llm.factory import build_chat_model, invoke_structured
from worker.llm.schemas import (
    Pass1Batch,
    SearchQuerySet,
    SourceEvaluation,
)
from worker.queue import enqueue_job
from worker.search import SearchConfig, build_router
from worker.search.errors import ExtractionFailed
from worker.search.extraction.chain import ExtractionChain
from worker.storage.activity import set_subtopic_status, upsert_activity
from worker.storage.chunking import chunk_text, count_tokens
from worker.storage.embeddings import Embedder
from worker.storage.store import store_chunks, store_source

if TYPE_CHECKING:
    from worker.loop import JobContext

log = logging.getLogger(__name__)

_SOURCE_CAP = 12
_SOURCE_MIN = 3


# ── Prompt builders ───────────────────────────────────────────────────────────

def _query_gen_messages(
    title: str,
    objective: str,
    tier_prefs: list[str],
    extra_instruction: str | None = None,
) -> list:
    tiers_str = ", ".join(tier_prefs) if tier_prefs else "any source type"
    system = (
        "You are a research specialist. Generate 3 to 5 diverse, specific search queries "
        "that will find high-quality information about the given research subtopic.\n\n"
        "Requirements:\n"
        "- Queries must be non-overlapping — each should target a different angle\n"
        "- Use the source type preferences to shape query style (e.g. academic queries "
        "  should include technical terms; news queries should be more current-events focused)\n"
        f"- Preferred source types: {tiers_str}\n"
        "- Respond with a JSON object matching the SearchQuerySet schema"
    )
    user_parts = [f"Subtopic: {title}\nObjective: {objective}"]
    if extra_instruction:
        user_parts.append(f"\nNote: {extra_instruction}")
    return [("system", system), ("human", "\n".join(user_parts))]


def _pass1_messages(candidates: list, title: str, objective: str) -> list:
    snippets = "\n\n".join(
        f"[{i}] URL: {r.url}\nTitle: {r.title or '(no title)'}\n"
        f"Snippet: {(r.snippet or '')[:300]}"
        for i, r in enumerate(candidates)
    )
    system = (
        "You are a relevance classifier. For each numbered source snippet, decide:\n"
        "  relevant: true if the source likely contains useful information for the research objective\n"
        "  accessible: true if the source appears to be freely accessible (not paywalled)\n\n"
        "Be strict about relevance but lenient about accessibility when unclear. "
        "Respond with a JSON object matching the Pass1Batch schema."
    )
    user = (
        f"Research subtopic: {title}\nObjective: {objective}\n\n"
        f"Candidate sources:\n{snippets}"
    )
    return [("system", system), ("human", user)]


def _pass2_messages(
    result,
    source_text: str,
    title: str,
    objective: str,
    stored_takeaways: list[str],
) -> list:
    existing = (
        "\n".join(f"- {t}" for t in stored_takeaways)
        if stored_takeaways
        else "(none yet)"
    )
    text_preview = source_text[:3000]
    system = (
        "You are a research quality evaluator. Score the provided source on four dimensions "
        "(each 1–5, where 1=very poor and 5=excellent):\n\n"
        "  score_relevance:     How directly relevant to the research objective?\n"
        "  score_credibility:   How trustworthy/authoritative is the source?\n"
        "  score_uniqueness:    How different is this from already-stored key takeaways?\n"
        "  score_actionability: How actionable/insightful is the information?\n\n"
        "Also provide a one-sentence key_takeaway summarising the most important finding.\n"
        "Respond with a JSON object matching the SourceEvaluation schema."
    )
    user = (
        f"Research subtopic: {title}\nObjective: {objective}\n\n"
        f"Already-stored key takeaways (for uniqueness comparison):\n{existing}\n\n"
        f"Source URL: {result.url}\nSource title: {result.title or '(no title)'}\n\n"
        f"Source content (first 3000 chars):\n{text_preview}"
    )
    return [("system", system), ("human", user)]


def _why_nothing_messages(
    title: str,
    objective: str,
    queries: list[str],
) -> list:
    queries_str = "\n".join(f"- {q}" for q in queries)
    system = (
        "You are a research assistant. Explain in 2–3 sentences why a web search "
        "for the given subtopic may have returned no usable sources, and suggest "
        "what alternative approaches or search terms might work better."
    )
    user = (
        f"Subtopic: {title}\nObjective: {objective}\n\n"
        f"Search queries attempted:\n{queries_str}"
    )
    return [("system", system), ("human", user)]


# ── Pipeline helpers ──────────────────────────────────────────────────────────

def _passes_store_rule(eval_result: SourceEvaluation) -> bool:
    """avg >= 3.0 AND no dimension == 1."""
    scores = [
        eval_result.score_relevance,
        eval_result.score_credibility,
        eval_result.score_uniqueness,
        eval_result.score_actionability,
    ]
    return sum(scores) / len(scores) >= 3.0 and min(scores) > 1


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


# ── Handler ───────────────────────────────────────────────────────────────────

async def handle(ctx: "JobContext") -> dict:
    payload: dict = dict(ctx.job["payload"])
    project_id: str = payload["project_id"]
    subtopic_id: str = payload["subtopic_id"]
    checkpoint: dict | None = payload.get("checkpoint")

    if ctx.is_cancelled():
        log.info("research_subtopic job %s cancelled before start", ctx.job["id"])
        return payload

    pool = await get_pool()

    # 1. Load subtopic + project data
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT s.title, s.information_objective, s.source_tier_preferences,
                   p.source_tier_settings
            FROM subtopics s
            JOIN projects p ON p.id = s.project_id
            WHERE s.id = $1::uuid AND s.project_id = $2::uuid
            """,
            subtopic_id,
            project_id,
        )

    if not row:
        raise ValueError(
            f"Subtopic {subtopic_id!r} not found for project {project_id!r}"
        )

    title: str = row["title"]
    objective: str = row["information_objective"]
    tier_prefs: list[str] = list(row["source_tier_preferences"] or [])

    # Resume state
    if checkpoint:
        processed_urls: set[str] = set(checkpoint.get("processed_urls", []))
        stored_count: int = int(checkpoint.get("stored_count", 0))
        saved_queries: list[str] | None = checkpoint.get("queries")
        stored_takeaways: list[str] = list(checkpoint.get("stored_takeaways", []))
        is_retry_wave: bool = bool(checkpoint.get("is_retry_wave", False))
    else:
        processed_urls = set()
        stored_count = 0
        saved_queries = None
        stored_takeaways = []
        is_retry_wave = False

    cumulative_tokens: int = 0

    # Build clients
    cfg = LLMConfig.from_env()
    llm_worker = build_chat_model(
        cfg, "worker",
        tags=["research", f"project:{project_id}", f"subtopic:{subtopic_id}"],
    )
    llm_classifier = build_chat_model(
        cfg, "classifier",
        tags=["research", f"project:{project_id}", f"subtopic:{subtopic_id}"],
    )
    search_cfg = SearchConfig.from_env()
    router = build_router(search_cfg)
    extraction_chain = ExtractionChain(search_cfg)
    embedder = Embedder(cfg)

    async def _write_activity(
        activity: str,
        status: str = "running",
        why_nothing_report: str | None = None,
    ) -> None:
        async with pool.acquire() as _conn:
            await upsert_activity(
                _conn,
                subtopic_id=subtopic_id,
                project_id=project_id,
                latest_activity=activity,
                sources_stored=stored_count,
                status=status,
                why_nothing_report=why_nothing_report,
            )

    # Set running on first run (not on resume)
    if not checkpoint:
        async with pool.acquire() as conn:
            await set_subtopic_status(conn, subtopic_id, "running")
        await _write_activity("Generating search queries")

    # ── Wave 1 ──
    stored_count, stored_takeaways, processed_urls, cumulative_tokens, handoff = (
        await _run_wave(
            ctx=ctx,
            pool=pool,
            project_id=project_id,
            subtopic_id=subtopic_id,
            title=title,
            objective=objective,
            tier_prefs=tier_prefs,
            saved_queries=saved_queries,
            extra_instruction=None,
            router=router,
            extraction_chain=extraction_chain,
            llm_worker=llm_worker,
            llm_classifier=llm_classifier,
            embedder=embedder,
            processed_urls=processed_urls,
            stored_count=stored_count,
            stored_takeaways=stored_takeaways,
            cumulative_tokens=cumulative_tokens,
            write_activity=_write_activity,
            cfg=cfg,
            job_id=ctx.job["id"],
            checkpoint=checkpoint,
            is_retry_wave=is_retry_wave,
        )
    )

    if handoff or ctx.is_cancelled():
        await router.aclose()
        await extraction_chain.aclose()
        return payload

    # 9. Auto-retry wave if below minimum target
    if stored_count < _SOURCE_MIN and not is_retry_wave:
        log.info(
            "research_subtopic job %s: %d sources (min %d) — retrying with different angle",
            ctx.job["id"], stored_count, _SOURCE_MIN,
        )
        await _write_activity("Retrying with a different search angle")
        if ctx.is_cancelled():
            await router.aclose()
            await extraction_chain.aclose()
            return payload

        extra = (
            f"The previous search found only {stored_count} useful source(s). "
            "Try completely different keywords, angles, and source types to find more information."
        )
        stored_count, stored_takeaways, processed_urls, cumulative_tokens, handoff = (
            await _run_wave(
                ctx=ctx,
                pool=pool,
                project_id=project_id,
                subtopic_id=subtopic_id,
                title=title,
                objective=objective,
                tier_prefs=tier_prefs,
                saved_queries=None,  # regenerate queries for retry wave
                extra_instruction=extra,
                router=router,
                extraction_chain=extraction_chain,
                llm_worker=llm_worker,
                llm_classifier=llm_classifier,
                embedder=embedder,
                processed_urls=processed_urls,
                stored_count=stored_count,
                stored_takeaways=stored_takeaways,
                cumulative_tokens=cumulative_tokens,
                write_activity=_write_activity,
                cfg=cfg,
                job_id=ctx.job["id"],
                checkpoint=None,
                is_retry_wave=True,
            )
        )

        if handoff or ctx.is_cancelled():
            await router.aclose()
            await extraction_chain.aclose()
            return payload

    await router.aclose()
    await extraction_chain.aclose()

    # 10. Why-nothing report
    why_nothing_report: str | None = None
    if stored_count == 0:
        log.info(
            "research_subtopic job %s: 0 sources after both waves — generating why-nothing report",
            ctx.job["id"],
        )
        try:
            all_queries = list(processed_urls)[:5]  # best-effort: log tried queries
            why_msgs = _why_nothing_messages(title, objective, all_queries)
            why_nothing_report = await llm_worker.ainvoke(why_msgs)
            # ainvoke returns an AIMessage; extract its content string
            if hasattr(why_nothing_report, "content"):
                why_nothing_report = str(why_nothing_report.content)
            else:
                why_nothing_report = str(why_nothing_report)
        except Exception:
            log.exception("research_subtopic job %s: why-nothing report failed", ctx.job["id"])
            why_nothing_report = "Search returned no usable sources after two attempts."

    # 13. Final: set complete
    async with pool.acquire() as conn:
        await set_subtopic_status(conn, subtopic_id, "complete")
    await _write_activity("complete", status="complete", why_nothing_report=why_nothing_report)

    payload["progress"] = "done"
    payload["sources_stored"] = stored_count
    await ctx.checkpoint(payload)
    return payload


# ── Wave runner ───────────────────────────────────────────────────────────────

async def _run_wave(
    *,
    ctx,
    pool,
    project_id: str,
    subtopic_id: str,
    title: str,
    objective: str,
    tier_prefs: list[str],
    saved_queries: list[str] | None,
    extra_instruction: str | None,
    router,
    extraction_chain,
    llm_worker,
    llm_classifier,
    embedder,
    processed_urls: set[str],
    stored_count: int,
    stored_takeaways: list[str],
    cumulative_tokens: int,
    write_activity,
    cfg: LLMConfig,
    job_id: str,
    checkpoint: dict | None,
    is_retry_wave: bool,
) -> tuple[int, list[str], set[str], int, bool]:
    """Run one search wave. Returns (stored_count, takeaways, processed_urls, tokens, handoff)."""

    # 2. Query generation
    if saved_queries:
        queries = saved_queries
    else:
        if ctx.is_cancelled():
            return stored_count, stored_takeaways, processed_urls, cumulative_tokens, False
        msgs = _query_gen_messages(title, objective, tier_prefs, extra_instruction)
        query_set: SearchQuerySet = await invoke_structured(
            llm_worker, SearchQuerySet, msgs, "query_generation"
        )
        queries = query_set.queries
        log.info("research_subtopic job %s: generated %d queries", job_id, len(queries))

    # 3. Search — run all queries, collect ≤25 candidates, dedup by URL
    candidates = []
    seen_urls: set[str] = processed_urls.copy()

    start_query_idx = (checkpoint or {}).get("query_index", 0) if saved_queries else 0

    await write_activity("Searching…")
    for qi in range(start_query_idx, len(queries)):
        if ctx.is_cancelled():
            return stored_count, stored_takeaways, processed_urls, cumulative_tokens, False
        if len(candidates) >= 25:
            break
        query = queries[qi]
        try:
            resp = await router.search(query, tier_prefs or ["news"], count=10)
            for result in resp.results:
                if result.url not in seen_urls and len(candidates) < 25:
                    candidates.append(result)
                    seen_urls.add(result.url)
        except Exception:
            log.exception("research_subtopic job %s: search failed for query %r", job_id, query)

    if not candidates:
        log.info("research_subtopic job %s: no search candidates found", job_id)
        return stored_count, stored_takeaways, processed_urls, cumulative_tokens, False

    # 4. Pass 1 — one batched classifier call
    if ctx.is_cancelled():
        return stored_count, stored_takeaways, processed_urls, cumulative_tokens, False

    try:
        p1_msgs = _pass1_messages(candidates, title, objective)
        p1_result: Pass1Batch = await invoke_structured(
            llm_classifier, Pass1Batch, p1_msgs, "pass1_filter"
        )
        surviving_indices = {
            item.index
            for item in p1_result.items
            if item.relevant and item.accessible
        }
        survivors = [
            candidates[item.index]
            for item in p1_result.items
            if item.index < len(candidates) and item.relevant and item.accessible
        ]
    except Exception:
        log.exception("research_subtopic job %s: pass-1 filter failed — using all candidates", job_id)
        survivors = candidates

    await write_activity(f"Filtered {len(survivors)} candidates")
    log.info(
        "research_subtopic job %s: %d/%d candidates passed pass-1",
        job_id, len(survivors), len(candidates),
    )

    # 5–7. Extract + Pass 2 + store
    for result in survivors:
        if ctx.is_cancelled():
            return stored_count, stored_takeaways, processed_urls, cumulative_tokens, False
        if stored_count >= _SOURCE_CAP:
            break
        if result.url in processed_urls:
            continue

        # 5. Extract full text
        await write_activity(f"Reading {_domain(result.url)}")
        try:
            extracted = await extraction_chain.extract(result)
            source_text = extracted.text
        except ExtractionFailed:
            log.debug("research_subtopic job %s: extraction failed for %r", job_id, result.url)
            processed_urls.add(result.url)
            continue

        # 11. Context-window ceiling check
        token_estimate = count_tokens(source_text[:4000])
        if cumulative_tokens + token_estimate > CONTEXT_CEILING_TOKENS:
            ckpt = {
                "processed_urls": list(processed_urls),
                "stored_count": stored_count,
                "queries": queries,
                "query_index": len(queries),
                "stored_takeaways": stored_takeaways,
                "is_retry_wave": is_retry_wave,
            }
            async with pool.acquire() as conn:
                new_job_id = await enqueue_job(
                    conn, project_id, "research_subtopic",
                    {"project_id": project_id, "subtopic_id": subtopic_id, "checkpoint": ckpt},
                )
            log.info(
                "research_subtopic job %s: context ceiling reached (%d tokens) — "
                "enqueued continuation job %s",
                job_id, cumulative_tokens, new_job_id,
            )
            return stored_count, stored_takeaways, processed_urls, cumulative_tokens, True

        cumulative_tokens += token_estimate

        # 6. Pass 2 evaluation
        if ctx.is_cancelled():
            return stored_count, stored_takeaways, processed_urls, cumulative_tokens, False

        try:
            p2_msgs = _pass2_messages(result, source_text, title, objective, stored_takeaways)
            eval_result: SourceEvaluation = await invoke_structured(
                llm_worker, SourceEvaluation, p2_msgs, "pass2_eval"
            )
        except Exception:
            log.exception(
                "research_subtopic job %s: pass-2 eval failed for %r", job_id, result.url
            )
            processed_urls.add(result.url)
            continue

        # Store rule: avg >= 3.0 and no dimension == 1
        if _passes_store_rule(eval_result):
            if ctx.is_cancelled():
                return stored_count, stored_takeaways, processed_urls, cumulative_tokens, False

            # 7. Chunk + embed + store in one transaction
            chunks = chunk_text(source_text)
            embeddings = await embedder.embed_texts([c.text for c in chunks])

            tier = result.tier if result.tier else (tier_prefs[0] if tier_prefs else "news")

            async with pool.acquire() as conn:
                async with conn.transaction():
                    source_id, _ = await store_source(
                        conn,
                        project_id=project_id,
                        subtopic_id=subtopic_id,
                        url=result.url,
                        title=result.title or result.url,
                        full_text=source_text,
                        tier=tier,
                        key_takeaway=eval_result.key_takeaway,
                        score_relevance=float(eval_result.score_relevance),
                        score_credibility=float(eval_result.score_credibility),
                        score_uniqueness=float(eval_result.score_uniqueness),
                        score_actionability=float(eval_result.score_actionability),
                    )
                    await store_chunks(conn, source_id, project_id, chunks, embeddings)

            stored_count += 1
            stored_takeaways.append(eval_result.key_takeaway)
            source_title = (result.title or result.url)[:60]
            await write_activity(f"Stored: {source_title} ({stored_count} sources)")
            log.info(
                "research_subtopic job %s: stored source %d/%d — %r",
                job_id, stored_count, _SOURCE_CAP, result.url,
            )
        else:
            log.debug(
                "research_subtopic job %s: source %r did not pass store rule "
                "(scores: %d/%d/%d/%d)",
                job_id, result.url,
                eval_result.score_relevance, eval_result.score_credibility,
                eval_result.score_uniqueness, eval_result.score_actionability,
            )

        processed_urls.add(result.url)

    return stored_count, stored_takeaways, processed_urls, cumulative_tokens, False
