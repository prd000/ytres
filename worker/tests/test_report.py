"""
Tests for the report handler — LLM and DB are fully mocked.

Covers:
- curated mode caps at 25 server-side even when more IDs are passed
- auto-draft selects from all takeaways and respects the server-side cap
- generated markdown is returned from the LLM; source_ids_used validated
- hallucinated source IDs (not in provided set) are silently dropped
- source_refs recorded correctly in the INSERT call
- project-isolation: sources query always includes project_id = $2
- pre-LLM cancellation (before selection) exits cleanly
- post-LLM cancellation (after synthesis) exits cleanly
"""
from __future__ import annotations
import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.loop import JobContext
from worker.llm.schemas import AutoDraftSelection, ReportDraft
import worker.handlers.report as report_module


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ctx(
    project_id: str,
    mode: str = "curated",
    source_ids: list[str] | None = None,
    instructions: str | None = None,
    cancelled: bool = False,
) -> tuple[JobContext, list[dict]]:
    job = {
        "id": str(uuid.uuid4()),
        "type": "generate_report",
        "payload": {
            "project_id": project_id,
            "mode": mode,
            "source_ids": source_ids or [],
            "instructions": instructions,
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


def _make_pool(
    project_row: dict | None = None,
    all_source_rows: list[dict] | None = None,
    full_source_rows: list[dict] | None = None,
    report_id: str | None = None,
):
    """Return a fake asyncpg pool whose conn returns configurable rows."""
    conn = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    _project_row = project_row if project_row is not None else {"research_question": "Test question"}
    _report_id = report_id or str(uuid.uuid4())

    fetch_side: list[list[dict]] = []
    if all_source_rows is not None:
        fetch_side.append(all_source_rows)

    fetch_results = iter(fetch_side) if fetch_side else iter([])

    # fetchrow is called for: project, then report INSERT RETURNING
    _fetchrow_calls: list = []

    async def _fetchrow(sql: str, *args: Any) -> dict | None:
        _fetchrow_calls.append((sql, args))
        if "SELECT research_question" in sql:
            return _project_row
        if "INSERT INTO reports" in sql:
            return {"id": _report_id}
        return None

    async def _fetch(sql: str, *args: Any) -> list[dict]:
        if "SELECT id, title, key_takeaway" in sql:
            return all_source_rows or []
        if "SELECT id, title, url, key_takeaway, full_text" in sql:
            return full_source_rows or []
        return []

    conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    conn.fetch = AsyncMock(side_effect=_fetch)

    pool = AsyncMock()
    pool.acquire = MagicMock(return_value=_AsyncCtxMgr(conn))
    return pool, conn


def _make_source_row(sid: str, project_id: str) -> dict:
    return {
        "id": sid,
        "title": f"Source {sid[:8]}",
        "url": f"https://example.com/{sid[:8]}",
        "key_takeaway": "A key finding.",
        "full_text": "Full text " * 100,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def pid() -> str:
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_curated_server_side_cap(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Curated mode caps at REPORT_SOURCE_CAP even when > 25 IDs are passed."""
    many_ids = [str(uuid.uuid4()) for _ in range(30)]
    # full source rows returned for the first 25 (server caps the list)
    full_rows = [_make_source_row(sid, pid) for sid in many_ids[:25]]

    pool, conn = _make_pool(full_source_rows=full_rows)
    monkeypatch.setattr(report_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CAP", 25)
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CHARS", 200)

    used_ids = [r["id"] for r in full_rows[:3]]
    draft = ReportDraft(markdown="# Report\n[Source](https://example.com) text.", source_ids_used=used_ids)
    monkeypatch.setattr(report_module, "invoke_structured", AsyncMock(return_value=draft))
    monkeypatch.setattr(report_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    ctx, _ = _make_ctx(pid, mode="curated", source_ids=many_ids)
    await report_module.handle(ctx)

    # The fetch call that loads full source rows must have received only 25 IDs
    fetch_call = conn.fetch.call_args_list[-1]
    chosen_ids_arg = fetch_call.args[1]  # second positional arg = the uuid[] list
    assert len(chosen_ids_arg) == 25


@pytest.mark.asyncio
async def test_auto_draft_cap_respected(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-draft: if LLM returns > 25 IDs, server caps at REPORT_SOURCE_CAP."""
    all_sources = [{"id": str(uuid.uuid4()), "title": f"S{i}", "key_takeaway": "kt"} for i in range(30)]
    full_rows = [_make_source_row(s["id"], pid) for s in all_sources[:25]]

    pool, _ = _make_pool(all_source_rows=all_sources, full_source_rows=full_rows)
    monkeypatch.setattr(report_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CAP", 25)
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CHARS", 200)

    # LLM returns more than the cap
    over_cap_ids = [s["id"] for s in all_sources]  # 30 IDs
    selection = AutoDraftSelection(selected_source_ids=over_cap_ids)
    used_ids = over_cap_ids[:3]
    draft = ReportDraft(markdown="# Report", source_ids_used=used_ids)

    call_count = 0

    async def _fake_invoke(llm: Any, schema: type, messages: list, tag: str) -> Any:
        nonlocal call_count
        call_count += 1
        if schema is AutoDraftSelection:
            return selection
        return draft

    monkeypatch.setattr(report_module, "invoke_structured", _fake_invoke)
    monkeypatch.setattr(report_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    ctx, _ = _make_ctx(pid, mode="auto")
    await report_module.handle(ctx)

    # invoke_structured called twice: auto-selection + synthesis
    assert call_count == 2


@pytest.mark.asyncio
async def test_hallucinated_ids_dropped(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """source_ids_used items not in the provided set are dropped before INSERT."""
    real_sid = str(uuid.uuid4())
    hallucinated_sid = str(uuid.uuid4())
    full_rows = [_make_source_row(real_sid, pid)]

    pool, conn = _make_pool(full_source_rows=full_rows)
    monkeypatch.setattr(report_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CAP", 25)
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CHARS", 200)

    draft = ReportDraft(
        markdown="# Report",
        source_ids_used=[real_sid, hallucinated_sid],  # hallucinated_sid not in provided set
    )
    monkeypatch.setattr(report_module, "invoke_structured", AsyncMock(return_value=draft))
    monkeypatch.setattr(report_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    ctx, _ = _make_ctx(pid, mode="curated", source_ids=[real_sid])
    await report_module.handle(ctx)

    # The INSERT fetchrow call should have received only [real_sid]
    insert_call = None
    for call in conn.fetchrow.call_args_list:
        if "INSERT INTO reports" in call.args[0]:
            insert_call = call
            break
    assert insert_call is not None
    source_refs_arg = insert_call.args[3]  # fourth positional arg = source_refs uuid[]
    assert source_refs_arg == [real_sid]


@pytest.mark.asyncio
async def test_source_refs_recorded(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """source_refs in the INSERT matches the validated source_ids_used."""
    sid1, sid2 = str(uuid.uuid4()), str(uuid.uuid4())
    full_rows = [_make_source_row(sid1, pid), _make_source_row(sid2, pid)]

    pool, conn = _make_pool(full_source_rows=full_rows)
    monkeypatch.setattr(report_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CAP", 25)
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CHARS", 200)

    draft = ReportDraft(markdown="# Report [S1](https://a.com) [S2](https://b.com)", source_ids_used=[sid1, sid2])
    monkeypatch.setattr(report_module, "invoke_structured", AsyncMock(return_value=draft))
    monkeypatch.setattr(report_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    ctx, _ = _make_ctx(pid, mode="curated", source_ids=[sid1, sid2])
    await report_module.handle(ctx)

    insert_call = None
    for call in conn.fetchrow.call_args_list:
        if "INSERT INTO reports" in call.args[0]:
            insert_call = call
            break
    assert insert_call is not None
    source_refs_arg = insert_call.args[3]
    assert set(source_refs_arg) == {sid1, sid2}


@pytest.mark.asyncio
async def test_project_isolation(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Full-source fetch always includes project_id = $2 (isolation guard)."""
    sid = str(uuid.uuid4())
    full_rows = [_make_source_row(sid, pid)]

    pool, conn = _make_pool(full_source_rows=full_rows)
    monkeypatch.setattr(report_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CAP", 25)
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CHARS", 200)

    draft = ReportDraft(markdown="# Report", source_ids_used=[sid])
    monkeypatch.setattr(report_module, "invoke_structured", AsyncMock(return_value=draft))
    monkeypatch.setattr(report_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    ctx, _ = _make_ctx(pid, mode="curated", source_ids=[sid])
    await report_module.handle(ctx)

    # Find the full-source SELECT call and verify project_id is passed as $2
    full_source_call = None
    for call in conn.fetch.call_args_list:
        if "project_id = $2" in call.args[0]:
            full_source_call = call
            break
    assert full_source_call is not None
    assert full_source_call.args[2] == pid  # third positional arg = project_id


@pytest.mark.asyncio
async def test_pre_llm_cancellation(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Handler returns early without calling LLM when cancelled before selection."""
    pool, _ = _make_pool()
    monkeypatch.setattr(report_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CAP", 25)
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CHARS", 200)

    invoke_mock = AsyncMock()
    monkeypatch.setattr(report_module, "invoke_structured", invoke_mock)
    monkeypatch.setattr(report_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    ctx, _ = _make_ctx(pid, mode="curated", source_ids=[], cancelled=True)
    await report_module.handle(ctx)

    invoke_mock.assert_not_called()


@pytest.mark.asyncio
async def test_post_synthesis_cancellation(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Handler returns after synthesis LLM call when cancelled, without inserting."""
    sid = str(uuid.uuid4())
    full_rows = [_make_source_row(sid, pid)]

    pool, conn = _make_pool(full_source_rows=full_rows)
    monkeypatch.setattr(report_module, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CAP", 25)
    monkeypatch.setattr(report_module, "REPORT_SOURCE_CHARS", 200)

    cancel_event = asyncio.Event()
    call_count = 0

    async def _cancelling_invoke(llm: Any, schema: type, messages: list, tag: str) -> Any:
        nonlocal call_count
        call_count += 1
        # Set cancelled after the synthesis call
        cancel_event.set()
        return ReportDraft(markdown="# Report", source_ids_used=[sid])

    job = {
        "id": str(uuid.uuid4()),
        "type": "generate_report",
        "payload": {"project_id": pid, "mode": "curated", "source_ids": [sid], "instructions": None},
    }
    checkpoints: list = []

    async def _cp(payload: dict) -> None:
        checkpoints.append(dict(payload))

    ctx = JobContext(job, _cp, cancel_event)

    monkeypatch.setattr(report_module, "invoke_structured", _cancelling_invoke)
    monkeypatch.setattr(report_module, "build_chat_model", MagicMock(return_value=AsyncMock()))

    await report_module.handle(ctx)

    # LLM was called once; INSERT was NOT called (cancelled after synthesis)
    assert call_count == 1
    for call in conn.fetchrow.call_args_list:
        assert "INSERT INTO reports" not in call.args[0], "INSERT should not happen after post-LLM cancel"
