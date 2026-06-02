"""
Chat handler — job type 'chat_respond'.

Steps:
1. Embed the user's question via Embedder.
2. Hybrid-search the project corpus via match_chunks().
3. If zero chunks found: write a low-confidence "corpus is empty" reply (no LLM call).
4. Load parent source rows (title, url) for the distinct source_ids in the matches.
5. Build synthesis prompt with numbered source blocks; invoke ChatAnswer via structured output.
6. Validate cited_source_ids ⊆ provided set (drop hallucinated IDs).
7. Build camelCase citations list [{sourceId, sourceTitle, url}] — matches TS Citation type.
8. INSERT assistant chat_messages row (role=assistant, content, citations jsonb, confidence).
   Realtime delivers the row to the open Chat tab.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from worker.config import CHAT_MATCH_COUNT, CHAT_CHUNK_CHARS
from worker.db import get_pool
from worker.llm.config import LLMConfig
from worker.llm.factory import build_chat_model, invoke_structured
from worker.llm.schemas import ChatAnswer
from worker.storage.embeddings import Embedder
from worker.storage.search import match_chunks

if TYPE_CHECKING:
    from worker.loop import JobContext

log = logging.getLogger(__name__)

_EMPTY_CORPUS_ANSWER = (
    "I couldn't find any relevant information in this project's research corpus. "
    "Try asking something covered by the stored sources, or use the **Research this** "
    "button below to kick off new research on this topic."
)


def _build_synthesis_messages(
    question: str,
    sources: list[dict],
) -> list:
    source_blocks = []
    for s in sources:
        truncated = (s["content"] or "")[:CHAT_CHUNK_CHARS]
        source_blocks.append(
            f"[ID:{s['source_id']}] {s['title']} / {s['url']}\n{truncated}"
        )
    sources_text = "\n\n---\n\n".join(source_blocks)

    system = (
        "You are a research assistant. Answer the user's question ONLY using the provided "
        "source excerpts. Cite inline using markdown links [Title](URL). "
        "Set confidence to 'high' if the sources directly and fully answer the question, "
        "'medium' if partially, or 'low' if the sources are tangentially related or insufficient.\n\n"
        "Respond with a JSON object matching the ChatAnswer schema: "
        '{"answer_markdown": "<answer>", "cited_source_ids": ["<id>", ...], '
        '"confidence": "high"|"medium"|"low"}'
    )
    user = f"Question: {question}\n\nSources:\n\n{sources_text}"
    return [("system", system), ("human", user)]


async def handle(ctx: "JobContext") -> dict:
    payload: dict = dict(ctx.job["payload"])
    project_id: str = payload["project_id"]
    question: str = payload["question"]

    if ctx.is_cancelled():
        log.info("chat_respond job %s cancelled before start", ctx.job["id"])
        return payload

    cfg = LLMConfig.from_env()
    embedder = Embedder(cfg)

    # ── Step 1: embed the question ────────────────────────────────────────────

    payload["progress"] = "embedding"
    await ctx.checkpoint(payload)

    embeddings = await embedder.embed_texts([question])
    query_embedding = embeddings[0]

    # ── Step 2: hybrid search ─────────────────────────────────────────────────

    payload["progress"] = "searching"
    await ctx.checkpoint(payload)

    pool = await get_pool()
    async with pool.acquire() as conn:
        chunks = await match_chunks(
            conn,
            project_id=project_id,
            query_embedding=query_embedding,
            query_text=question,
            match_count=CHAT_MATCH_COUNT,
        )

    # ── Step 3: empty corpus path ─────────────────────────────────────────────

    if not chunks:
        log.info(
            "chat_respond job %s: no chunks found for project %s — writing low-confidence reply",
            ctx.job["id"], project_id,
        )
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chat_messages (project_id, role, content, citations, confidence)
                VALUES ($1::uuid, 'assistant', $2, $3, 'low')
                """,
                project_id,
                _EMPTY_CORPUS_ANSWER,
                [],
            )
        payload["progress"] = "done"
        await ctx.checkpoint(payload)
        return payload

    # ── Step 4: load parent source rows ───────────────────────────────────────

    distinct_source_ids = list({c.source_id for c in chunks})
    async with pool.acquire() as conn:
        source_rows = await conn.fetch(
            """
            SELECT id, title, url
            FROM sources
            WHERE id = ANY($1::uuid[]) AND project_id = $2::uuid
            """,
            distinct_source_ids,
            project_id,
        )
    source_map = {str(r["id"]): {"title": r["title"], "url": r["url"]} for r in source_rows}

    # Build per-chunk context dicts for the prompt (include chunk content + source metadata)
    context_chunks = [
        {
            "source_id": c.source_id,
            "title": source_map.get(c.source_id, {}).get("title", ""),
            "url": source_map.get(c.source_id, {}).get("url", ""),
            "content": c.content,
        }
        for c in chunks
        if c.source_id in source_map  # project isolation: only sources in our map
    ]
    provided_source_ids = {c["source_id"] for c in context_chunks}

    # ── Step 5: synthesize the answer ─────────────────────────────────────────

    payload["progress"] = "synthesizing"
    await ctx.checkpoint(payload)

    if ctx.is_cancelled():
        log.info("chat_respond job %s cancelled before LLM call", ctx.job["id"])
        return payload

    llm = build_chat_model(
        cfg, "coordinator",
        tags=["chat", f"project:{project_id}"],
    )
    messages = _build_synthesis_messages(question, context_chunks)
    answer: ChatAnswer = await invoke_structured(llm, ChatAnswer, messages, "chat_answer")

    if ctx.is_cancelled():
        log.info("chat_respond job %s cancelled after LLM call", ctx.job["id"])
        return payload

    # ── Step 6: validate cited_source_ids ⊆ provided set ─────────────────────

    validated_ids = [sid for sid in answer.cited_source_ids if sid in provided_source_ids]
    if len(validated_ids) != len(answer.cited_source_ids):
        dropped = set(answer.cited_source_ids) - provided_source_ids
        log.warning(
            "chat_respond job %s: dropped %d hallucinated source IDs: %s",
            ctx.job["id"], len(dropped), dropped,
        )

    # ── Step 7: build camelCase citations list ────────────────────────────────
    # Keys must match the TS Citation type (sourceId / sourceTitle / url) because
    # mapChatMessage in client.ts passes row.citations verbatim into the domain type.

    citations = [
        {
            "sourceId": sid,
            "sourceTitle": source_map[sid]["title"],
            "url": source_map[sid]["url"],
        }
        for sid in validated_ids
        if sid in source_map
    ]

    # ── Step 8: insert assistant chat_messages row ────────────────────────────

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chat_messages (project_id, role, content, citations, confidence)
            VALUES ($1::uuid, 'assistant', $2, $3, $4)
            """,
            project_id,
            answer.answer_markdown,
            citations,
            answer.confidence,
        )

    log.info(
        "chat_respond job %s: answered for project %s (confidence=%s, citations=%d)",
        ctx.job["id"], project_id, answer.confidence, len(citations),
    )

    payload["progress"] = "done"
    await ctx.checkpoint(payload)
    return payload
