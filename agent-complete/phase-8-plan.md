# Phase 8 — Coordinator Review

## Context

Phases 0–7 are complete. **Phase 7 (Real-Time Progress) was effectively finished inside Phase 6**: the research handler writes `worker_activity` at every stage (`research.py:251,293,419,462,478,560,362`), `ProjectRealtime.tsx` subscribes to `projects`/`subtopics`/`sources`/`worker_activity` and calls `router.refresh()`, the Research tab renders all states, and re-mount reconciliation happens via the server-component re-fetch on navigation. The only un-done PRD-7 items are cosmetic (no `jobs`/`source_subtopics` subscriptions — neither drives a user-facing surface). **So the real target is Phase 8.**

Today, when a project's `research_subtopic` jobs all finish, **nothing happens**: there is no fan-in barrier to detect "research is done", no coordinator that reviews coverage, no gap-filling, and nothing transitions a project `researching → complete`. The project sits in `researching` forever. Phase 8 closes the research loop: after the worker wave finishes, a DeepSeek-Pro coordinator reviews coverage against objectives, optionally spawns **one** gap-fill wave, then marks the project `complete`.

**Two confirmed choices (from clarifying questions):**
- **Barrier = in-process worker sweep** (not a DB trigger) — consistent with the existing `_watchdog` precedent (`loop.py:117`), keeps orchestration visible in Python.
- **Include the gap-fill badge** in the Research tab.

Interpretation of the PRD two-wave cap ("research ends after wave 2"): at most **one** gap-fill round. `coordinator_review` runs at most twice — review #1 after the initial subtopics (may spawn one gap-fill round, or complete if no gaps); review #2 after the gap-fill round (always completes, never spawns more).

Build order per CLAUDE.md: **backend first, then wire the frontend.**

---

## Step 1 — Migration `supabase/migrations/0011_coordinator_review.sql` (new)

Three parts (next number after `0010`):

**1a. `subtopics.wave` column** — initial-plan subtopics stay `wave=0`; gap-fill subtopics get `wave=1`. Drives the coordinator's analysis and the frontend badge.
```sql
alter table subtopics add column wave smallint not null default 0;
```

**1b. Set-based barrier RPC `enqueue_ready_coordinator_reviews()` (SECURITY DEFINER)** — the sweep calls this every interval; mirrors `reclaim_stale_jobs` (one set-based RPC, no per-row Python loop). A transaction-level advisory lock serializes concurrent sweeps across worker instances so the `NOT EXISTS` idempotency guards are reliable.
```sql
create or replace function enqueue_ready_coordinator_reviews()
returns integer language plpgsql security definer as $$
declare v_count integer;
begin
  perform pg_advisory_xact_lock(81273401);  -- serialize concurrent sweeps
  insert into jobs (project_id, type, payload)
  select p.id, 'coordinator_review',
         jsonb_build_object('project_id', p.id::text, 'wave', rev.next_wave)
  from projects p
  cross join lateral (
    select (select count(*) from jobs j
            where j.project_id = p.id and j.type = 'coordinator_review') + 1 as next_wave
  ) rev
  where p.status = 'researching'
    and rev.next_wave <= 2                                    -- two-wave cap
    and exists (select 1 from jobs j                          -- research actually ran
                where j.project_id = p.id and j.type = 'research_subtopic')
    and not exists (select 1 from jobs j                      -- nothing still in flight
                    where j.project_id = p.id and j.type = 'research_subtopic'
                      and j.status in ('queued','running'))
    and not exists (select 1 from jobs j                      -- idempotent per wave
                    where j.project_id = p.id and j.type = 'coordinator_review'
                      and (j.payload->>'wave')::int = rev.next_wave);
  get diagnostics v_count = row_count;
  return v_count;
end; $$;
```
Plus a hard backstop index (won't fire given the advisory lock, kept as defense-in-depth):
```sql
create unique index jobs_review_wave_uniq
  on jobs (project_id, ((payload->>'wave'))) where type = 'coordinator_review';
```

**1c. `complete_research(p_project_id)` RPC (SECURITY DEFINER)** — the single worker-owned status transition; guarded so it no-ops unless currently `researching`.
```sql
create or replace function complete_research(p_project_id uuid)
returns void language plpgsql security definer as $$
begin
  update projects set status='complete', updated_at=now()
  where id = p_project_id and status = 'researching';
end; $$;
```

**Edge cases handled:** handoff continuation (the new same-subtopic job is `queued` → "still in flight" → sweep waits); retry (`fail_job` re-queues to `queued`, not terminal → sweep waits, per `0006_rpc.sql:112`); all-subtopics-failed (jobs terminal, none open → review fires → coordinator completes, research still terminates); cancellation (project `cancelled`, status guard skips it); gap-fill in progress (coordinator enqueues gap jobs `queued` before its own job ends → sweep waits until they finish → review #2); two-wave cap (`next_wave > 2` → no further reviews).

## Step 2 — `shared/schemas/job_payloads.py`

Add after `ResearchSubtopicPayload` and register in `JOB_PAYLOAD_MODELS`:
```python
class CoordinatorReviewPayload(BaseModel):
    project_id: str
    wave: int
    progress: str | None = None
```

## Step 3 — `worker/worker/llm/schemas.py`

Add after `SourceEvaluation`, **reusing** `PlannedSubtopic` (its title / information_objective / `source_tier_preferences: list[SourceTier]` shape is exactly what the subtopic INSERT needs):
```python
class CoverageReview(BaseModel):
    is_complete: bool
    summary: str
    gap_subtopics: list[PlannedSubtopic] = Field(default_factory=list, max_length=3)
```

## Step 4 — `worker/worker/queue.py` — two thin wrappers

Alongside the existing pool-based wrappers (`queue.py:41-48` style):
```python
async def enqueue_ready_coordinator_reviews() -> int:
    pool = await get_pool()
    row = await pool.fetchrow("select enqueue_ready_coordinator_reviews()")
    return int(row[0]) if row else 0

async def complete_research(project_id: str) -> None:
    pool = await get_pool()
    await pool.execute("select complete_research($1::uuid)", project_id)
```
(`enqueue_job(conn, ...)` already exists at `queue.py:51` and is reused inside the coordinator's gap-fill transaction.)

## Step 5 — Sweep coroutine in `worker/worker/loop.py`

Mirror `_watchdog` (`loop.py:117-126`) exactly. Add `enqueue_ready_coordinator_reviews` to the `from worker.queue import (...)` block and `COORDINATOR_SWEEP_INTERVAL` to the `from worker.config import (...)` block.
```python
async def _coordinator_sweep(cancel_event: asyncio.Event) -> None:
    while not cancel_event.is_set():
        await asyncio.sleep(COORDINATOR_SWEEP_INTERVAL)
        if cancel_event.is_set():
            break
        try:
            n = await enqueue_ready_coordinator_reviews()
            if n:
                log.info("coordinator sweep: enqueued %d review(s)", n)
        except Exception:
            log.exception("coordinator sweep error")
```
In `run()` (`loop.py:134`), spawn it next to `watchdog_task` and cancel it in the shutdown block alongside `watchdog_task.cancel()` (`loop.py:167`).

**Config:** add `coordinator_sweep_interval` to `config.toml [worker]` (e.g. `10`) and read it in `worker/worker/config.py` next to `WATCHDOG_INTERVAL` (`config.py:58`): `COORDINATOR_SWEEP_INTERVAL: float = _w["coordinator_sweep_interval"]`.

## Step 6 — `worker/worker/handlers/coordinator.py` (new) — job type `coordinator_review`

Mirror `planner.py` structure (cancel check before+after the LLM call; transactional writes). Register in `handlers/__init__.py`: `"coordinator_review": coordinator_handle`.

Flow:
1. Early-out if `ctx.is_cancelled()`. Read `project_id`, `wave` from payload.
2. Load project (`research_question`, `source_tier_settings`, `status`); return early if `status != 'researching'`.
3. `_load_coverage(conn, project_id)` (factored module-level fn, directly testable) — per subtopic: `title`, `information_objective`, `status`, `wave`, `sources_stored` + `why_nothing_report` (from `worker_activity`), and the `key_takeaway`s of its stored sources via `source_subtopics`→`sources`:
   ```sql
   SELECT s.id, s.title, s.information_objective, s.status, s.wave,
          wa.why_nothing_report, wa.sources_stored,
          array_remove(array_agg(src.key_takeaway ORDER BY src.created_at), NULL) AS takeaways
   FROM subtopics s
   LEFT JOIN worker_activity wa ON wa.subtopic_id = s.id
   LEFT JOIN source_subtopics ss ON ss.subtopic_id = s.id
   LEFT JOIN sources src ON src.id = ss.source_id
   WHERE s.project_id = $1::uuid
   GROUP BY s.id, wa.why_nothing_report, wa.sources_stored
   ORDER BY s.sort_order;
   ```
   (Verify `sources` timestamp column name during implementation — use whatever `store_source` writes; fall back to ordering by `src.id` if none.)
4. `_build_messages(research_question, coverage_rows, wave)` — reuse planner's enabled-tier extraction (`planner.py:35-43`). Ask the coordinator to set `is_complete`, write a `summary`, and on **wave 1** propose up to 3 refined `gap_subtopics`; pass `wave` so on wave 2 it's told gaps will be ignored.
5. `llm = build_chat_model(cfg, "coordinator", tags=["coordinator", f"project:{project_id}"])`; `review = await invoke_structured(llm, CoverageReview, messages, "coordinator_review")`. **Import `invoke_structured` bare and patch `worker.handlers.coordinator.invoke_structured` in tests** (the working pattern from `test_research.py:257` — note `test_planner.py` patches a non-existent `_invoke_structured`, a separate pre-existing no-op bug, out of scope here).
6. Post-LLM cancel guard.
7. Branch: `spawn = (wave == 1) and (not review.is_complete) and bool(review.gap_subtopics)`.
   - **spawn** → in ONE transaction: insert gap subtopics (`wave=1`, `status='queued'`, `sort_order` after current max, `source_tier_preferences` cast `$N::text[]::source_tier[]` per `planner.py:132`) and `enqueue_job(conn, project_id, "research_subtopic", {"project_id":…, "subtopic_id":…})` for each. Do **not** complete the project. (Append, never delete-then-insert — preserves the original subtopics and their sources.)
   - **else** (wave 1 no gaps, OR wave 2, OR `is_complete`) → `await complete_research(project_id)`.
8. `await ctx.checkpoint(payload)`.

## Step 7 — Frontend: gap-fill badge (after backend)

- `web/src/lib/data/types.ts` — add `wave: number;` to `interface Subtopic`.
- `web/src/lib/data/client.ts` — add `wave` to the `subtopics` `.select(...)` column list (if not `*`) and `wave: row.wave` to `mapSubtopic` (~`client.ts:28-38`).
- `web/src/components/features/research/ResearchTab.tsx` — render a small `Badge` (outline variant, existing `ui/Badge.tsx`) labeled "Gap-fill" beside the subtopic title when `subtopic.wave > 0`. Purely additive; reference DESIGN.md for token usage. No other UI changes — new gap subtopics and the project→`complete` transition already surface via the existing Realtime subscriptions.

## Step 8 — Tests (mocked external APIs, per PRD)

- `worker/tests/test_coordinator.py` (new) — patch `worker.handlers.coordinator.invoke_structured`; real `db` fixture + conftest seeders; project status `researching`; monkeypatch `coordinator_module.complete_research` to an `AsyncMock` to assert call/no-call:
  - wave1-gaps: `is_complete=False` + 2 gaps → 2 new `wave=1` `queued` subtopics, 2 new `research_subtopic` jobs, project still `researching`, `complete_research` NOT called.
  - wave1-nogaps: `is_complete=True` → no new rows, `complete_research` called.
  - wave2-completes: payload `wave=2` even with gaps present → no gap inserts, `complete_research` called.
  - cancel before-LLM and after-LLM → no writes.
  - `_load_coverage` assembly: seed a subtopic with 2 linked sources + a barren subtopic with `why_nothing_report`; assert takeaways and why-nothing per subtopic.
- `worker/tests/test_contract.py` — add `CoordinatorReviewPayload` valid / missing-wave-invalid / `JOB_PAYLOAD_MODELS["coordinator_review"]` registry checks (mirror existing `ResearchSubtopicPayload` tests).
- `worker/tests/test_barrier.py` (new, real Postgres via `db` fixture; needs 0011 applied) — exercise `enqueue_ready_coordinator_reviews()` + `complete_research()`: last job done → exactly one review (wave 1); already-reviewed → no duplicate; all-failed → review still fires; project `cancelled` → none; gap-fill done with wave-1 review present → wave 2; wave-2 present → no wave 3. **No local Supabase on this machine → flag "verified statically; live run pending"** (consistent with prior phases).

## Step 9 — Docs (required by CLAUDE.md)

- `context/log.md` — Phase 8 entry (newest first).
- `context/map.md` — add `handlers/coordinator.py`, `migrations/0011_coordinator_review.sql`, `test_coordinator.py`, `test_barrier.py`, the new schemas, the two `queue.py` wrappers, the sweep, `subtopics.wave`. Move `phase-8-plan.md` to `agent-complete/` when the phase finishes.
- `context/decisions.md` — two new entries: (1) **Worker completes the project** — sanctioned exception to Decision 4, via `complete_research` SECURITY DEFINER RPC, the one worker-owned terminal transition. (2) **Fan-in barrier via in-process sweep + set-based RPC, not a DB trigger** — rationale (consistency with `_watchdog`, orchestration stays visible in Python, advisory-lock + `NOT EXISTS` idempotency for race safety, accepted sweep-interval latency).
- `context/deferredwork.md` — note: migration 0011 must be applied to live Supabase before Phase 8 runs; single gap-fill round enforced by the two-wave cap (a 3rd wave needs lifting the cap); barrier/RPC tests "verified statically; live run pending"; pre-existing `test_planner.py` `_invoke_structured` mis-patch logged as separate cleanup.

---

## Verification

**Static / mocked (runnable now, no DB/network):**
1. `python -m py_compile` on `coordinator.py`, `handlers/__init__.py`, `queue.py`, `loop.py`, `config.py`, `llm/schemas.py`, `shared/schemas/job_payloads.py`.
2. From `web/`: `npx tsc --noEmit` (covers the badge edits).
3. From `worker/`: `pytest tests/test_coordinator.py tests/test_contract.py` (mocked LLM + `complete_research`).

**Live stack (deferred — no local Supabase here; flag in log.md as "verified statically; live run pending"):**
4. Apply migrations through 0011; confirm `subtopics.wave`, both RPCs, and the unique index exist.
5. E2E: create → plan → approve (`researching`) → research finishes → within one sweep interval, exactly one `coordinator_review` wave 1 appears → if gaps, new `wave=1` subtopics + jobs (badge shows in Research tab), project still `researching` → after gap jobs finish, `coordinator_review` wave 2 → project `complete`, no third review.
6. Negative: cancel mid-research → no review fires, project stays `cancelled`.

## Risks / open items

- **Sweep latency** — completion lags by up to `coordinator_sweep_interval` (~10s). Acceptable at this scale; tunable.
- **Sweep won't fire if all workers are down** — same limitation as the existing watchdog (decisions.md 2026-05-31, accepted). Recovers on next worker start.
- **Concurrent sweeps across worker instances** — neutralized by the `pg_advisory_xact_lock` + unique partial index.
- **Coordinator returns gaps on wave 2** — structurally ignored (`wave == 1` gate); two-wave cap is the backstop, so no infinite loop even if every subtopic fails.
- **`sources` ORDER BY column** — confirm the actual timestamp column written by `store_source` during implementation (fall back to `src.id`).
