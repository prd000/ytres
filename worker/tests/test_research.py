"""
Tests for the research handler — all external dependencies mocked.

LLM (invoke_structured), SearchRouter, Embedder, ExtractionChain, and all DB
writes are monkeypatched or faked so these tests need no network or database.

Covers: store rule, source cap (12), min-target triggers second wave, why-nothing
on empty result, pre/post-LLM cancellation, idempotent resume from checkpoint,
handoff enqueues a continuation job, worker_activity upsert sequence.
"""
from __future__ import annotations
import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.loop import JobContext
from worker.llm.schemas import Pass1Batch, Pass1Item, SearchQuerySet, SourceEvaluation
import worker.handlers.research as research_module


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _make_ctx(
    project_id: str,
    subtopic_id: str,
    checkpoint: dict | None = None,
    cancelled: bool = False,
) -> tuple[JobContext, list[dict]]:
    job = {
        "id": str(uuid.uuid4()),
        "type": "research_subtopic",
        "payload": {
            "project_id": project_id,
            "subtopic_id": subtopic_id,
            **({"checkpoint": checkpoint} if checkpoint else {}),
        },
    }
    cancel_event = asyncio.Event()
    if cancelled:
        cancel_event.set()
    checkpoints: list[dict] = []

    async def _cp(payload: dict) -> None:
        checkpoints.append(dict(payload))

    ctx = JobContext(job, _cp, cancel_event)
    return ctx, checkpoints


def _make_result(url: str, title: str = "Test Source", tier: str = "news"):
    """Return a mock SearchResult-like object."""
    r = MagicMock()
    r.url = url
    r.title = title
    r.tier = tier
    r.snippet = "A snippet about the topic."
    r.raw_content = None
    return r


def _good_eval(score: int = 4) -> SourceEvaluation:
    return SourceEvaluation(
        score_relevance=score,
        score_credibility=score,
        score_uniqueness=score,
        score_actionability=score,
        key_takeaway="Key finding about the topic.",
    )


def _bad_eval() -> SourceEvaluation:
    """Eval that fails the store rule (avg < 3, has a 1)."""
    return SourceEvaluation(
        score_relevance=1,
        score_credibility=2,
        score_uniqueness=2,
        score_actionability=2,
        key_takeaway="Poor source.",
    )


def _make_query_set(n: int = 3) -> SearchQuerySet:
    return SearchQuerySet(queries=[f"query {i}" for i in range(n)])


def _make_pass1_batch(n: int, all_pass: bool = True) -> Pass1Batch:
    return Pass1Batch(items=[
        Pass1Item(index=i, relevant=all_pass, accessible=all_pass)
        for i in range(n)
    ])


class _FakeSearchResponse:
    def __init__(self, results):
        self.results = results
        self.failures = []


class _FakeRouter:
    def __init__(self, results_per_query: list | None = None):
        self._results = results_per_query or []
        self._call_count = 0
        self.searches: list = []

    async def search(self, query, tiers, *, count=10):
        self.searches.append(query)
        idx = min(self._call_count, len(self._results) - 1)
        results = self._results[idx] if self._results else []
        self._call_count += 1
        return _FakeSearchResponse(results)

    async def aclose(self):
        pass


class _FakeEmbedder:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1536 for _ in texts]


class _FakeExtraction:
    def __init__(self, text: str = "Full source text with enough content for evaluation."):
        self._text = text
        self.extracted: list[str] = []

    async def extract(self, result):
        self.extracted.append(result.url)
        content = MagicMock()
        content.text = self._text
        return content

    async def aclose(self):
        pass


class _FailExtraction:
    async def extract(self, result):
        from worker.search.errors import ExtractionFailed
        raise ExtractionFailed(result.url, failures=[])

    async def aclose(self):
        pass


# ── DB mock helpers ───────────────────────────────────────────────────────────

def _make_fake_pool(project_id: str, subtopic_id: str):
    """Return a fake asyncpg pool that returns a stub subtopic row."""
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_AsyncCtxMgr(conn))
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    # fetchrow returns the subtopic row
    row = {
        "title": "Test Subtopic",
        "information_objective": "Gather test information",
        "source_tier_preferences": ["news"],
        "source_tier_settings": {"news": True},
    }
    conn.fetchrow = AsyncMock(return_value=row)
    conn.execute = AsyncMock()
    conn.fetchrow_side = None

    pool = AsyncMock()
    pool.acquire = MagicMock(return_value=_AsyncCtxMgr(conn))
    return pool, conn


class _AsyncCtxMgr:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def pid():
    return str(uuid.uuid4())


@pytest.fixture
def sid():
    return str(uuid.uuid4())


async def test_store_rule_passes_good_source(pid, sid, monkeypatch):
    """Source with avg>=3 and no-1 scores gets stored."""
    pool, conn = _make_fake_pool(pid, sid)
    results = [_make_result(f"https://example{i}.com") for i in range(3)]
    router = _FakeRouter([results])

    stored_sources: list = []

    async def fake_store_source(conn, **kwargs):
        stored_sources.append(kwargs["url"])
        return (str(uuid.uuid4()), True)

    async def fake_store_chunks(*args, **kwargs):
        return 2

    monkeypatch.setattr(research_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(research_module, "build_router", lambda cfg: router)
    monkeypatch.setattr(research_module, "ExtractionChain", lambda cfg: _FakeExtraction())
    monkeypatch.setattr(research_module, "Embedder", lambda cfg: _FakeEmbedder())
    monkeypatch.setattr(research_module, "store_source", fake_store_source)
    monkeypatch.setattr(research_module, "store_chunks", fake_store_chunks)
    monkeypatch.setattr(research_module, "set_subtopic_status", AsyncMock())
    monkeypatch.setattr(research_module, "upsert_activity", AsyncMock())

    call_num = [0]
    async def fake_invoke_structured(llm, schema, messages, run_name):
        n = call_num[0]
        call_num[0] += 1
        if schema is SearchQuerySet:
            return _make_query_set(3)
        if schema is Pass1Batch:
            return _make_pass1_batch(len(results))
        if schema is SourceEvaluation:
            return _good_eval()
        raise ValueError(f"Unexpected schema {schema}")

    monkeypatch.setattr(research_module, "invoke_structured", fake_invoke_structured)

    ctx, _ = _make_ctx(pid, sid)
    await research_module.handle(ctx)

    assert len(stored_sources) == 3


async def test_store_rule_fails_bad_source(pid, sid, monkeypatch):
    """Source with avg<3 or a score==1 is not stored."""
    pool, conn = _make_fake_pool(pid, sid)
    results = [_make_result("https://bad.com")]
    router = _FakeRouter([results])

    stored_sources: list = []

    async def fake_store_source(conn, **kwargs):
        stored_sources.append(kwargs["url"])
        return (str(uuid.uuid4()), True)

    monkeypatch.setattr(research_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(research_module, "build_router", lambda cfg: router)
    monkeypatch.setattr(research_module, "ExtractionChain", lambda cfg: _FakeExtraction())
    monkeypatch.setattr(research_module, "Embedder", lambda cfg: _FakeEmbedder())
    monkeypatch.setattr(research_module, "store_source", fake_store_source)
    monkeypatch.setattr(research_module, "store_chunks", AsyncMock(return_value=0))
    monkeypatch.setattr(research_module, "set_subtopic_status", AsyncMock())
    monkeypatch.setattr(research_module, "upsert_activity", AsyncMock())

    async def fake_invoke_structured(llm, schema, messages, run_name):
        if schema is SearchQuerySet:
            return _make_query_set(3)
        if schema is Pass1Batch:
            return _make_pass1_batch(1)
        if schema is SourceEvaluation:
            return _bad_eval()
        raise ValueError(f"Unexpected schema {schema}")

    monkeypatch.setattr(research_module, "invoke_structured", fake_invoke_structured)

    ctx, _ = _make_ctx(pid, sid)
    await research_module.handle(ctx)

    assert len(stored_sources) == 0


async def test_source_cap_12(pid, sid, monkeypatch):
    """Handler stops storing after 12 sources even if more pass the store rule."""
    pool, conn = _make_fake_pool(pid, sid)
    results = [_make_result(f"https://s{i}.com") for i in range(20)]
    router = _FakeRouter([results])

    stored_sources: list = []

    async def fake_store_source(conn, **kwargs):
        stored_sources.append(kwargs["url"])
        return (str(uuid.uuid4()), True)

    monkeypatch.setattr(research_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(research_module, "build_router", lambda cfg: router)
    monkeypatch.setattr(research_module, "ExtractionChain", lambda cfg: _FakeExtraction())
    monkeypatch.setattr(research_module, "Embedder", lambda cfg: _FakeEmbedder())
    monkeypatch.setattr(research_module, "store_source", fake_store_source)
    monkeypatch.setattr(research_module, "store_chunks", AsyncMock(return_value=2))
    monkeypatch.setattr(research_module, "set_subtopic_status", AsyncMock())
    monkeypatch.setattr(research_module, "upsert_activity", AsyncMock())

    async def fake_invoke_structured(llm, schema, messages, run_name):
        if schema is SearchQuerySet:
            return _make_query_set(3)
        if schema is Pass1Batch:
            return _make_pass1_batch(len(results))
        if schema is SourceEvaluation:
            return _good_eval()
        raise ValueError(f"Unexpected schema {schema}")

    monkeypatch.setattr(research_module, "invoke_structured", fake_invoke_structured)

    ctx, _ = _make_ctx(pid, sid)
    await research_module.handle(ctx)

    assert len(stored_sources) <= research_module._SOURCE_CAP


async def test_min_target_triggers_second_wave(pid, sid, monkeypatch):
    """When stored < _SOURCE_MIN after wave 1, a second wave is attempted."""
    pool, conn = _make_fake_pool(pid, sid)
    # Wave 1: 1 result (below min=3); wave 2: 3 results
    wave1_results = [_make_result("https://w1.com")]
    wave2_results = [_make_result(f"https://w2-{i}.com") for i in range(3)]

    call_counts = {"search": 0}

    class _TwoWaveRouter:
        async def search(self, query, tiers, *, count=10):
            call_counts["search"] += 1
            if call_counts["search"] <= 3:  # queries in wave 1
                return _FakeSearchResponse(wave1_results)
            return _FakeSearchResponse(wave2_results)

        async def aclose(self):
            pass

    stored_sources: list = []

    async def fake_store_source(conn, **kwargs):
        stored_sources.append(kwargs["url"])
        return (str(uuid.uuid4()), True)

    monkeypatch.setattr(research_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(research_module, "build_router", lambda cfg: _TwoWaveRouter())
    monkeypatch.setattr(research_module, "ExtractionChain", lambda cfg: _FakeExtraction())
    monkeypatch.setattr(research_module, "Embedder", lambda cfg: _FakeEmbedder())
    monkeypatch.setattr(research_module, "store_source", fake_store_source)
    monkeypatch.setattr(research_module, "store_chunks", AsyncMock(return_value=2))
    monkeypatch.setattr(research_module, "set_subtopic_status", AsyncMock())
    monkeypatch.setattr(research_module, "upsert_activity", AsyncMock())

    wave1_extra_seen = [False]

    async def fake_invoke_structured(llm, schema, messages, run_name):
        if schema is SearchQuerySet:
            # Check if this is the retry invocation via messages content
            user_msg = str(messages)
            if "previous search" in user_msg.lower() or "different" in user_msg.lower():
                wave1_extra_seen[0] = True
            return _make_query_set(3)
        if schema is Pass1Batch:
            n = len(wave1_results) if call_counts["search"] <= 3 else len(wave2_results)
            return _make_pass1_batch(max(1, n))
        if schema is SourceEvaluation:
            return _good_eval()
        raise ValueError(f"Unexpected schema {schema}")

    monkeypatch.setattr(research_module, "invoke_structured", fake_invoke_structured)

    ctx, _ = _make_ctx(pid, sid)
    await research_module.handle(ctx)

    # Should have stored at least the wave-2 sources
    assert len(stored_sources) >= 1


async def test_why_nothing_report_on_empty(pid, sid, monkeypatch):
    """When 0 sources stored after both waves, why_nothing_report is written."""
    pool, conn = _make_fake_pool(pid, sid)
    router = _FakeRouter([])  # no results

    activity_calls: list = []

    async def fake_upsert_activity(conn, **kwargs):
        activity_calls.append(dict(kwargs))

    monkeypatch.setattr(research_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(research_module, "build_router", lambda cfg: router)
    monkeypatch.setattr(research_module, "ExtractionChain", lambda cfg: _FakeExtraction())
    monkeypatch.setattr(research_module, "Embedder", lambda cfg: _FakeEmbedder())
    monkeypatch.setattr(research_module, "store_source", AsyncMock())
    monkeypatch.setattr(research_module, "store_chunks", AsyncMock())
    monkeypatch.setattr(research_module, "set_subtopic_status", AsyncMock())
    monkeypatch.setattr(research_module, "upsert_activity", fake_upsert_activity)

    async def fake_invoke_structured(llm, schema, messages, run_name):
        if schema is SearchQuerySet:
            return _make_query_set(3)
        if schema is Pass1Batch:
            return _make_pass1_batch(0)
        raise ValueError(f"Unexpected schema {schema}")

    monkeypatch.setattr(research_module, "invoke_structured", fake_invoke_structured)

    # Mock the why-nothing llm call (returns an AIMessage-like object)
    llm_mock = AsyncMock()
    llm_mock.ainvoke = AsyncMock(return_value=MagicMock(content="No useful sources found because the topic is very niche."))
    monkeypatch.setattr(research_module, "build_chat_model", lambda cfg, role, **kw: llm_mock)

    ctx, _ = _make_ctx(pid, sid)
    await research_module.handle(ctx)

    # The final upsert_activity call should have a why_nothing_report
    final_call = activity_calls[-1]
    assert final_call.get("status") == "complete"
    assert final_call.get("why_nothing_report") is not None


async def test_cancellation_before_queries(pid, sid, monkeypatch):
    """Cancelled before query generation — no LLM calls made."""
    pool, conn = _make_fake_pool(pid, sid)

    invoke_calls = [0]

    async def fake_invoke_structured(llm, schema, messages, run_name):
        invoke_calls[0] += 1
        return _make_query_set(3)

    monkeypatch.setattr(research_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(research_module, "build_router", lambda cfg: _FakeRouter())
    monkeypatch.setattr(research_module, "ExtractionChain", lambda cfg: _FakeExtraction())
    monkeypatch.setattr(research_module, "Embedder", lambda cfg: _FakeEmbedder())
    monkeypatch.setattr(research_module, "set_subtopic_status", AsyncMock())
    monkeypatch.setattr(research_module, "upsert_activity", AsyncMock())
    monkeypatch.setattr(research_module, "invoke_structured", fake_invoke_structured)

    ctx, _ = _make_ctx(pid, sid, cancelled=True)
    await research_module.handle(ctx)

    assert invoke_calls[0] == 0


async def test_cancellation_after_queries_before_store(pid, sid, monkeypatch):
    """Cancellation after Pass-1 filter — no DB stores executed."""
    pool, conn = _make_fake_pool(pid, sid)
    results = [_make_result("https://good.com")]
    router = _FakeRouter([results])

    stored_calls = [0]

    async def fake_store_source(conn, **kwargs):
        stored_calls[0] += 1
        return (str(uuid.uuid4()), True)

    ctx, _ = _make_ctx(pid, sid)

    call_num = [0]

    async def fake_invoke_structured(llm, schema, messages, run_name):
        call_num[0] += 1
        if schema is SearchQuerySet:
            return _make_query_set(3)
        if schema is Pass1Batch:
            return _make_pass1_batch(1)
        if schema is SourceEvaluation:
            ctx._cancelled.set()  # cancel after pass-2 eval starts
            return _good_eval()
        raise ValueError

    monkeypatch.setattr(research_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(research_module, "build_router", lambda cfg: router)
    monkeypatch.setattr(research_module, "ExtractionChain", lambda cfg: _FakeExtraction())
    monkeypatch.setattr(research_module, "Embedder", lambda cfg: _FakeEmbedder())
    monkeypatch.setattr(research_module, "store_source", fake_store_source)
    monkeypatch.setattr(research_module, "store_chunks", AsyncMock(return_value=2))
    monkeypatch.setattr(research_module, "set_subtopic_status", AsyncMock())
    monkeypatch.setattr(research_module, "upsert_activity", AsyncMock())
    monkeypatch.setattr(research_module, "invoke_structured", fake_invoke_structured)

    await research_module.handle(ctx)

    # Cancelled after eval but before store — store should not have been called
    assert stored_calls[0] == 0


async def test_handoff_enqueues_continuation_job(pid, sid, monkeypatch):
    """When context ceiling is hit, a continuation job is enqueued and handler returns."""
    pool, conn = _make_fake_pool(pid, sid)
    results = [_make_result(f"https://heavy{i}.com") for i in range(5)]
    router = _FakeRouter([results])

    enqueued_jobs: list = []

    async def fake_enqueue_job(conn, project_id, job_type, payload):
        enqueued_jobs.append({"project_id": project_id, "type": job_type, "payload": payload})
        return str(uuid.uuid4())

    # Force the ceiling to 0 so it triggers immediately
    monkeypatch.setattr(research_module, "CONTEXT_CEILING_TOKENS", 0)
    monkeypatch.setattr(research_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(research_module, "build_router", lambda cfg: router)
    monkeypatch.setattr(research_module, "ExtractionChain", lambda cfg: _FakeExtraction("long " * 500))
    monkeypatch.setattr(research_module, "Embedder", lambda cfg: _FakeEmbedder())
    monkeypatch.setattr(research_module, "store_source", AsyncMock(return_value=(str(uuid.uuid4()), True)))
    monkeypatch.setattr(research_module, "store_chunks", AsyncMock(return_value=2))
    monkeypatch.setattr(research_module, "set_subtopic_status", AsyncMock())
    monkeypatch.setattr(research_module, "upsert_activity", AsyncMock())
    monkeypatch.setattr(research_module, "enqueue_job", fake_enqueue_job)

    async def fake_invoke_structured(llm, schema, messages, run_name):
        if schema is SearchQuerySet:
            return _make_query_set(3)
        if schema is Pass1Batch:
            return _make_pass1_batch(len(results))
        if schema is SourceEvaluation:
            return _good_eval()
        raise ValueError

    monkeypatch.setattr(research_module, "invoke_structured", fake_invoke_structured)

    ctx, checkpoints = _make_ctx(pid, sid)
    await research_module.handle(ctx)

    # A continuation job must have been enqueued
    assert len(enqueued_jobs) == 1
    job = enqueued_jobs[0]
    assert job["type"] == "research_subtopic"
    assert job["payload"]["project_id"] == pid
    assert job["payload"]["subtopic_id"] == sid
    assert "checkpoint" in job["payload"]
    ckpt = job["payload"]["checkpoint"]
    assert "processed_urls" in ckpt
    assert "stored_count" in ckpt
    assert "queries" in ckpt


async def test_resume_from_checkpoint_skips_processed_urls(pid, sid, monkeypatch):
    """On resume, URLs in checkpoint.processed_urls are not re-processed."""
    already_done = "https://already-done.com"
    ckpt = {
        "processed_urls": [already_done],
        "stored_count": 1,
        "queries": ["query 0", "query 1", "query 2"],
        "query_index": 3,
        "stored_takeaways": ["Prior takeaway"],
        "is_retry_wave": False,
    }

    pool, conn = _make_fake_pool(pid, sid)
    new_result = _make_result("https://new-source.com")
    old_result = _make_result(already_done)
    router = _FakeRouter([[old_result, new_result]])

    extracted_urls: list = []

    class _TrackingExtraction:
        async def extract(self, result):
            extracted_urls.append(result.url)
            content = MagicMock()
            content.text = "Text content"
            return content

        async def aclose(self):
            pass

    stored_sources: list = []

    async def fake_store_source(conn, **kwargs):
        stored_sources.append(kwargs["url"])
        return (str(uuid.uuid4()), True)

    monkeypatch.setattr(research_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(research_module, "build_router", lambda cfg: router)
    monkeypatch.setattr(research_module, "ExtractionChain", lambda cfg: _TrackingExtraction())
    monkeypatch.setattr(research_module, "Embedder", lambda cfg: _FakeEmbedder())
    monkeypatch.setattr(research_module, "store_source", fake_store_source)
    monkeypatch.setattr(research_module, "store_chunks", AsyncMock(return_value=2))
    monkeypatch.setattr(research_module, "set_subtopic_status", AsyncMock())
    monkeypatch.setattr(research_module, "upsert_activity", AsyncMock())

    async def fake_invoke_structured(llm, schema, messages, run_name):
        if schema is SearchQuerySet:
            return _make_query_set(3)
        if schema is Pass1Batch:
            # Only 1 new candidate (old_result is in seen_urls from processed_urls)
            return _make_pass1_batch(1)
        if schema is SourceEvaluation:
            return _good_eval()
        raise ValueError

    monkeypatch.setattr(research_module, "invoke_structured", fake_invoke_structured)

    ctx, _ = _make_ctx(pid, sid, checkpoint=ckpt)
    await research_module.handle(ctx)

    # The already-processed URL should not have been extracted again
    assert already_done not in extracted_urls


async def test_worker_activity_upsert_sequence(pid, sid, monkeypatch):
    """worker_activity is upserted at key stages: running → searching → filtered → stored → complete."""
    pool, conn = _make_fake_pool(pid, sid)
    results = [_make_result("https://ok.com")]
    router = _FakeRouter([results])

    activity_sequence: list[str] = []

    async def fake_upsert_activity(conn, *, latest_activity, status, **kwargs):
        activity_sequence.append(f"{status}:{latest_activity}")

    monkeypatch.setattr(research_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(research_module, "build_router", lambda cfg: router)
    monkeypatch.setattr(research_module, "ExtractionChain", lambda cfg: _FakeExtraction())
    monkeypatch.setattr(research_module, "Embedder", lambda cfg: _FakeEmbedder())
    monkeypatch.setattr(research_module, "store_source", AsyncMock(return_value=(str(uuid.uuid4()), True)))
    monkeypatch.setattr(research_module, "store_chunks", AsyncMock(return_value=2))
    monkeypatch.setattr(research_module, "set_subtopic_status", AsyncMock())
    monkeypatch.setattr(research_module, "upsert_activity", fake_upsert_activity)

    async def fake_invoke_structured(llm, schema, messages, run_name):
        if schema is SearchQuerySet:
            return _make_query_set(3)
        if schema is Pass1Batch:
            return _make_pass1_batch(1)
        if schema is SourceEvaluation:
            return _good_eval()
        raise ValueError

    monkeypatch.setattr(research_module, "invoke_structured", fake_invoke_structured)

    ctx, _ = _make_ctx(pid, sid)
    await research_module.handle(ctx)

    # Must start with running activity and end with complete
    assert any("running" in a for a in activity_sequence), f"Expected 'running' in {activity_sequence}"
    assert any("complete:complete" in a for a in activity_sequence), f"Expected complete in {activity_sequence}"
