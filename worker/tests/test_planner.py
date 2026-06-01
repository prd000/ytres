"""
Tests for the planner handler — LLM and asyncpg writes are mocked/real accordingly.

LLM is mocked (no real DeepSeek calls). DB writes use the real local PG stack
so we verify the SQL insert path end-to-end.
"""
from __future__ import annotations
import asyncio
import uuid
import pytest
import asyncpg

from worker.loop import JobContext
from worker.llm.schemas import ResearchPlan, PlannedSubtopic
import worker.handlers.planner as planner_module

from tests.conftest import _seed_user, _seed_project


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_plan(n: int = 4) -> ResearchPlan:
    return ResearchPlan(subtopics=[
        PlannedSubtopic(
            title=f"Subtopic {i}",
            information_objective=f"Gather information about aspect {i}",
            source_tier_preferences=["academic"],
        )
        for i in range(n)
    ])


def _make_ctx(
    project_id: str,
    feedback: str | None = None,
    cancelled: bool = False,
) -> tuple[JobContext, list[dict]]:
    job = {
        "id": str(uuid.uuid4()),
        "type": "generate_plan",
        "payload": {"project_id": project_id, "feedback": feedback},
    }
    cancel_event = asyncio.Event()
    if cancelled:
        cancel_event.set()
    checkpoints: list[dict] = []

    async def _checkpoint(payload: dict) -> None:
        checkpoints.append(dict(payload))

    ctx = JobContext(job, _checkpoint, cancel_event)
    return ctx, checkpoints


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_planner_writes_subtopics(db: asyncpg.Connection, monkeypatch):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)

    plan = _make_plan(4)
    monkeypatch.setattr(planner_module, "_invoke_structured", _mock_invoke(plan))

    ctx, checkpoints = _make_ctx(pid)
    await planner_module.handle(ctx)

    rows = await db.fetch(
        "SELECT title, sort_order, status FROM subtopics WHERE project_id = $1 ORDER BY sort_order",
        pid,
    )
    assert len(rows) == 4
    for i, row in enumerate(rows):
        assert row["sort_order"] == i
        assert row["status"] == "queued"


async def test_planner_sort_order_sequential(db: asyncpg.Connection, monkeypatch):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)

    monkeypatch.setattr(planner_module, "_invoke_structured", _mock_invoke(_make_plan(3)))
    ctx, _ = _make_ctx(pid)
    await planner_module.handle(ctx)

    rows = await db.fetch(
        "SELECT sort_order FROM subtopics WHERE project_id = $1 ORDER BY sort_order",
        pid,
    )
    assert [r["sort_order"] for r in rows] == [0, 1, 2]


async def test_planner_enum_array_persisted(db: asyncpg.Connection, monkeypatch):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)

    plan = ResearchPlan(subtopics=[
        PlannedSubtopic(
            title="Social media analysis",
            information_objective="Gather social media data",
            source_tier_preferences=["social_media", "news"],
        ),
        PlannedSubtopic(
            title="Academic review",
            information_objective="Review academic literature",
            source_tier_preferences=["academic"],
        ),
        PlannedSubtopic(
            title="Government data",
            information_objective="Check government sources",
            source_tier_preferences=["government"],
        ),
    ])
    monkeypatch.setattr(planner_module, "_invoke_structured", _mock_invoke(plan))

    ctx, _ = _make_ctx(pid)
    await planner_module.handle(ctx)

    row = await db.fetchrow(
        "SELECT source_tier_preferences FROM subtopics WHERE project_id = $1 ORDER BY sort_order LIMIT 1",
        pid,
    )
    tiers = list(row["source_tier_preferences"])
    assert "social_media" in tiers
    assert "news" in tiers


async def test_planner_regenerate_replaces_subtopics(db: asyncpg.Connection, monkeypatch):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)

    # First run — 2 subtopics
    monkeypatch.setattr(planner_module, "_invoke_structured", _mock_invoke(_make_plan(2)))
    ctx1, _ = _make_ctx(pid)
    await planner_module.handle(ctx1)

    # Regenerate — 3 subtopics
    monkeypatch.setattr(planner_module, "_invoke_structured", _mock_invoke(_make_plan(3)))
    ctx2, _ = _make_ctx(pid, feedback="Please add more depth")
    await planner_module.handle(ctx2)

    rows = await db.fetch(
        "SELECT id FROM subtopics WHERE project_id = $1",
        pid,
    )
    assert len(rows) == 3


async def test_planner_idempotent_on_resume(db: asyncpg.Connection, monkeypatch):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)

    monkeypatch.setattr(planner_module, "_invoke_structured", _mock_invoke(_make_plan(4)))

    # Run twice — should result in exactly 4 subtopics (not 8)
    ctx1, _ = _make_ctx(pid)
    await planner_module.handle(ctx1)
    ctx2, _ = _make_ctx(pid)
    await planner_module.handle(ctx2)

    rows = await db.fetch(
        "SELECT id FROM subtopics WHERE project_id = $1",
        pid,
    )
    assert len(rows) == 4


async def test_planner_cancellation_before_llm_no_writes(db: asyncpg.Connection, monkeypatch):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)

    invoke_called = False

    async def mock_invoke(llm, schema, messages, run_name):
        nonlocal invoke_called
        invoke_called = True
        return _make_plan(4)

    monkeypatch.setattr(planner_module, "_invoke_structured", mock_invoke)

    ctx, _ = _make_ctx(pid, cancelled=True)
    await planner_module.handle(ctx)

    assert not invoke_called
    rows = await db.fetch(
        "SELECT id FROM subtopics WHERE project_id = $1", pid
    )
    assert len(rows) == 0


async def test_planner_cancellation_after_llm_no_writes(db: asyncpg.Connection, monkeypatch):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)

    ctx, checkpoints = _make_ctx(pid)

    async def mock_invoke_and_cancel(llm, schema, messages, run_name):
        ctx._cancelled.set()  # Cancel after LLM call
        return _make_plan(4)

    monkeypatch.setattr(planner_module, "_invoke_structured", mock_invoke_and_cancel)

    await planner_module.handle(ctx)

    rows = await db.fetch(
        "SELECT id FROM subtopics WHERE project_id = $1", pid
    )
    assert len(rows) == 0


async def test_planner_does_not_mutate_project_status(db: asyncpg.Connection, monkeypatch):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)

    monkeypatch.setattr(planner_module, "_invoke_structured", _mock_invoke(_make_plan(3)))

    ctx, _ = _make_ctx(pid)
    await planner_module.handle(ctx)

    row = await db.fetchrow(
        "SELECT status FROM projects WHERE id = $1", pid
    )
    # Project status is seeded as 'draft' — handler must not change it
    assert row["status"] == "draft"


async def test_planner_missing_project_raises(db: asyncpg.Connection, monkeypatch):
    monkeypatch.setattr(planner_module, "_invoke_structured", _mock_invoke(_make_plan(3)))
    fake_pid = str(uuid.uuid4())

    ctx, _ = _make_ctx(fake_pid)
    with pytest.raises(ValueError, match="not found"):
        await planner_module.handle(ctx)


async def test_planner_checkpoints_planning_then_done(db: asyncpg.Connection, monkeypatch):
    uid = await _seed_user(db)
    pid = await _seed_project(db, uid)

    monkeypatch.setattr(planner_module, "_invoke_structured", _mock_invoke(_make_plan(3)))
    ctx, checkpoints = _make_ctx(pid)
    await planner_module.handle(ctx)

    progresses = [cp.get("progress") for cp in checkpoints]
    assert "planning" in progresses
    assert "done" in progresses

    done_cp = next(cp for cp in checkpoints if cp.get("progress") == "done")
    assert done_cp["subtopic_count"] == 3


# ── Internal helpers ──────────────────────────────────────────────────────────

def _mock_invoke(plan: ResearchPlan):
    async def _invoke(llm, schema, messages, run_name):
        return plan
    return _invoke
