"""
Tests for the chat handler — LLM, Embedder, match_chunks, and DB are fully mocked.

Covers:
- cited_source_ids subset validation drops hallucinated IDs
- citations list uses camelCase keys (sourceId/sourceTitle/url) — TS contract
- project isolation: only sources from this project appear in context
- empty corpus path writes a low-confidence message without an LLM call
- pre-LLM cancellation exits cleanly without inserting
- post-LLM cancellation exits cleanly without inserting
"""
from __future__ import annotations
import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.loop import JobContext
from worker.llm.schemas import ChatAnswer
from worker.storage.search import ChunkMatch
import worker.handlers.chat as chat_module


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ctx(
    project_id: str,
    question: str = "What are the main findings?",
    cancelled: bool = False,
) -> tuple[JobContext, list[dict]]:
    job = {
        "id": str(uuid.uuid4()),
        "type": "chat_respond",
        "payload": {
            "project_id": project_id,
            "question": question,
        },
    }
    cancel_event = asyncio.Event()
    if cancelled:
        cancel_event.set()
    checkpoints: list[dict] = []

    async def _cp(payload: dict) -> None:
        checkpoints.append(dict(payload))

    return JobContext(job, _cp, cancel_event), checkpoints


class _AsyncCtxMgr:
    def __init__(self, value: Any):
        self._value = value

    async def __aenter__(self) -> Any:
        return self._value

    async def __aexit__(self, *args: Any) -> bool:
        return False


def _make_pool(source_rows: list[dict] | None = None):
    conn = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    async def _fetch(sql: str, *args: Any) -> list[dict]:
        if "SELECT id, title, url" in sql:
            return source_rows or []
        return []

    conn.fetch = AsyncMock(side_effect=_fetch)
    conn.execute = AsyncMock(return_value=None)

    pool = AsyncMock()
    pool.acquire = MagicMock(return_value=_AsyncCtxMgr(conn))
    return pool, conn


def _make_chunk(source_id: str, project_id: str, content: str = "chunk text") -> ChunkMatch:
    return ChunkMatch(
        chunk_id=str(uuid.uuid4()),
        source_id=source_id,
        project_id=project_id,
        chunk_index=0,
        content=content,
        token_count=10,
        score=0.9,
    )


def _make_embedder(vector: list[float] | None = None):
    embedder = AsyncMock()
    embedder.embed_texts = AsyncMock(return_value=[vector or [0.1] * 10])
    return embedder


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def pid() -> str:
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_citations_camelcase_keys(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Citations list must use camelCase keys matching the TS Citation type."""
    sid = str(uuid.uuid4())
    source_rows = [{"id": sid, "title": "Source A", "url": "https://example.com/a"}]
    chunks = [_make_chunk(sid, pid)]
    pool, conn = _make_pool(source_rows=source_rows)

    monkeypatch.setattr(chat_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(chat_module, "match_chunks", AsyncMock(return_value=chunks))
    monkeypatch.setattr(chat_module, "Embedder", MagicMock(return_value=_make_embedder()))
    monkeypatch.setattr(chat_module, "CHAT_MATCH_COUNT", 12)
    monkeypatch.setattr(chat_module, "CHAT_CHUNK_CHARS", 200)

    answer = ChatAnswer(answer_markdown="Answer", cited_source_ids=[sid], confidence="high")
    monkeypatch.setattr(chat_module, "invoke_structured", AsyncMock(return_value=answer))
    monkeypatch.setattr(chat_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    ctx, _ = _make_ctx(pid)
    await chat_module.handle(ctx)

    insert_call = conn.execute.call_args
    assert insert_call is not None
    citations_arg = insert_call.args[3]  # fourth positional = citations jsonb
    assert len(citations_arg) == 1
    cit = citations_arg[0]
    assert "sourceId" in cit
    assert "sourceTitle" in cit
    assert "url" in cit
    assert "source_id" not in cit  # must not use snake_case


@pytest.mark.asyncio
async def test_hallucinated_ids_dropped(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """cited_source_ids not in the provided set are silently dropped."""
    sid = str(uuid.uuid4())
    hallucinated = str(uuid.uuid4())
    source_rows = [{"id": sid, "title": "Real source", "url": "https://example.com/r"}]
    chunks = [_make_chunk(sid, pid)]
    pool, conn = _make_pool(source_rows=source_rows)

    monkeypatch.setattr(chat_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(chat_module, "match_chunks", AsyncMock(return_value=chunks))
    monkeypatch.setattr(chat_module, "Embedder", MagicMock(return_value=_make_embedder()))
    monkeypatch.setattr(chat_module, "CHAT_MATCH_COUNT", 12)
    monkeypatch.setattr(chat_module, "CHAT_CHUNK_CHARS", 200)

    answer = ChatAnswer(
        answer_markdown="Answer",
        cited_source_ids=[sid, hallucinated],  # hallucinated not in provided set
        confidence="medium",
    )
    monkeypatch.setattr(chat_module, "invoke_structured", AsyncMock(return_value=answer))
    monkeypatch.setattr(chat_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    ctx, _ = _make_ctx(pid)
    await chat_module.handle(ctx)

    insert_call = conn.execute.call_args
    citations_arg = insert_call.args[3]
    # only the real source_id survives
    assert len(citations_arg) == 1
    assert citations_arg[0]["sourceId"] == sid


@pytest.mark.asyncio
async def test_empty_corpus_no_llm_call(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no chunks are found, a low-confidence reply is inserted without an LLM call."""
    pool, conn = _make_pool()

    monkeypatch.setattr(chat_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(chat_module, "match_chunks", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_module, "Embedder", MagicMock(return_value=_make_embedder()))
    monkeypatch.setattr(chat_module, "CHAT_MATCH_COUNT", 12)
    monkeypatch.setattr(chat_module, "CHAT_CHUNK_CHARS", 200)

    invoke_mock = AsyncMock()
    monkeypatch.setattr(chat_module, "invoke_structured", invoke_mock)
    monkeypatch.setattr(chat_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    ctx, _ = _make_ctx(pid)
    await chat_module.handle(ctx)

    invoke_mock.assert_not_called()
    insert_call = conn.execute.call_args
    assert insert_call is not None
    # 'low' is embedded in the SQL string for the empty-corpus path
    assert "'low'" in insert_call.args[0]


@pytest.mark.asyncio
async def test_project_isolation(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Source fetch always includes project_id = $2 (isolation guard)."""
    sid = str(uuid.uuid4())
    source_rows = [{"id": sid, "title": "S", "url": "https://example.com/s"}]
    chunks = [_make_chunk(sid, pid)]
    pool, conn = _make_pool(source_rows=source_rows)

    monkeypatch.setattr(chat_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(chat_module, "match_chunks", AsyncMock(return_value=chunks))
    monkeypatch.setattr(chat_module, "Embedder", MagicMock(return_value=_make_embedder()))
    monkeypatch.setattr(chat_module, "CHAT_MATCH_COUNT", 12)
    monkeypatch.setattr(chat_module, "CHAT_CHUNK_CHARS", 200)

    answer = ChatAnswer(answer_markdown="A", cited_source_ids=[sid], confidence="high")
    monkeypatch.setattr(chat_module, "invoke_structured", AsyncMock(return_value=answer))
    monkeypatch.setattr(chat_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    ctx, _ = _make_ctx(pid)
    await chat_module.handle(ctx)

    # The source SELECT must include project_id scoping
    source_fetch_call = None
    for call in conn.fetch.call_args_list:
        if "project_id = $2" in call.args[0]:
            source_fetch_call = call
            break
    assert source_fetch_call is not None
    assert source_fetch_call.args[2] == pid  # third positional = project_id


@pytest.mark.asyncio
async def test_pre_llm_cancellation(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Handler returns early without calling LLM when cancelled at start."""
    pool, conn = _make_pool()

    monkeypatch.setattr(chat_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(chat_module, "match_chunks", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_module, "Embedder", MagicMock(return_value=_make_embedder()))
    monkeypatch.setattr(chat_module, "CHAT_MATCH_COUNT", 12)
    monkeypatch.setattr(chat_module, "CHAT_CHUNK_CHARS", 200)

    invoke_mock = AsyncMock()
    monkeypatch.setattr(chat_module, "invoke_structured", invoke_mock)
    monkeypatch.setattr(chat_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    ctx, _ = _make_ctx(pid, cancelled=True)
    await chat_module.handle(ctx)

    invoke_mock.assert_not_called()
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_post_llm_cancellation(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Handler returns after LLM call when cancelled, without inserting."""
    sid = str(uuid.uuid4())
    source_rows = [{"id": sid, "title": "S", "url": "https://example.com/s"}]
    chunks = [_make_chunk(sid, pid)]
    pool, conn = _make_pool(source_rows=source_rows)

    cancel_event = asyncio.Event()

    async def _cancelling_invoke(llm: Any, schema: type, messages: list, tag: str) -> Any:
        cancel_event.set()
        return ChatAnswer(answer_markdown="A", cited_source_ids=[sid], confidence="high")

    monkeypatch.setattr(chat_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(chat_module, "match_chunks", AsyncMock(return_value=chunks))
    monkeypatch.setattr(chat_module, "Embedder", MagicMock(return_value=_make_embedder()))
    monkeypatch.setattr(chat_module, "CHAT_MATCH_COUNT", 12)
    monkeypatch.setattr(chat_module, "CHAT_CHUNK_CHARS", 200)
    monkeypatch.setattr(chat_module, "invoke_structured", _cancelling_invoke)
    monkeypatch.setattr(chat_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    job = {
        "id": str(uuid.uuid4()),
        "type": "chat_respond",
        "payload": {"project_id": pid, "question": "Test?"},
    }
    checkpoints: list = []

    async def _cp(payload: dict) -> None:
        checkpoints.append(dict(payload))

    ctx = JobContext(job, _cp, cancel_event)
    await chat_module.handle(ctx)

    conn.execute.assert_not_called()
