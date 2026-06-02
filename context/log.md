# Build Log

Newest-first. One entry per milestone or significant bug fix.

---

## Phase 8 — Coordinator review + gap-fill (2026-06-01)
Closes the research loop. New `coordinator_review` job type: after all `research_subtopic` jobs for a project finish, an in-process coordinator sweep (`_coordinator_sweep` in `loop.py`, every 10 s) calls the `enqueue_ready_coordinator_reviews()` SECURITY DEFINER RPC (migration `0011`). The RPC uses a transaction-level advisory lock + `NOT EXISTS` idempotency guards to enqueue exactly one review per wave (two-wave cap). The coordinator handler (`handlers/coordinator.py`) loads per-subtopic coverage (key takeaways + why-nothing reports), invokes the DeepSeek coordinator LLM against `CoverageReview` schema, then either spawns gap-fill subtopics + jobs (wave 1 only) or calls `complete_research()` (new SECURITY DEFINER RPC — sanctioned exception to Decision 4). New `subtopics.wave` column (0 = initial plan, 1 = gap-fill); Research tab renders a "Gap-fill" outline Badge for wave > 0 subtopics. `CoordinatorReviewPayload` + `CoverageReview` schemas added. 20 contract tests pass; coordinator + barrier integration tests written (live run pending — no local Supabase).

## Bug: research_subtopic crash — dict-shaped search queries (2026-06-01)
`SearchQuerySet.queries` is typed `list[str]`, but the query-gen model (prompted with source-tier preferences) intermittently returned each query as an object (`{"query": ..., "source_type": ...}`), failing Pydantic validation and killing the job — explaining why ~2/5 subtopic jobs failed while the rest succeeded. Fix: `field_validator(mode="before")` on `SearchQuerySet.queries` normalises either shape (string or `query`/`q`/`text`/`search_query` object, with first-string fallback) down to a plain query string. 2 regression tests added (`test_search_query_set_coerces_dict_queries`, `..._plain_strings_unchanged`).

## Phase 6 — Research pipeline (2026-06-01)
Full `research_subtopic` worker handler: query gen → Brave/Tavily search → Pass-1 batch filter → extraction → Pass-2 per-source eval → store (≤12 sources, min-3 target, auto-retry wave, context-ceiling handoff). LangSmith tracing fixed (`load_dotenv` before worker imports; `LANGSMITH_ACTIVE` flag). `invoke_structured` lifted from planner into `factory.py` (shared). New `storage/activity.py` (upsert + status helper). `approvePlan` action bulk-enqueues one `research_subtopic` job per subtopic. Realtime subscriptions added for `worker_activity` + `sources`. 9 new tests; `ResearchSubtopicPayload` added to contract.

## Feature: delete project (2026-06-01)
`deleteProject` Server Action (cancel jobs RPC → cascade `DELETE FROM projects` → redirect). New `DeleteProjectButton` client component (Radix Dialog confirm, error display). Rendered in `ProjectShellHeader` beside Cancel.

## Bug: generate_plan crash — asyncpg jsonb codec (2026-06-01)
`ctx.job["payload"]` arrived as a raw JSON string; `dict(str)` iterated chars → ValueError. Fix: `register_json_codecs()` in `db.py` added as pool `init=` so all jsonb columns decode to dict on read. `queue.py` heartbeat updated to pass dict directly (was double-encoding). Regression test added.

## Bug: RLS blocked INSERT…RETURNING (2026-06-01)
`createProject` used `.select("id")` → `INSERT … RETURNING`, which requires the SELECT policy to pass on the new row. `can_access_project()` (SECURITY DEFINER) re-queries `projects` — new row not yet visible in that snapshot → 42501. Fix: migration `0010` adds `owner_id = auth.uid()` short-circuit to the SELECT policy.

## Feature: email confirmation route (2026-06-01)
New `web/src/app/auth/confirm/route.ts` — reads `token_hash`+`type`, calls `verifyOtp` via SSR client (writes session cookie). `signup` action sets `emailRedirectTo` to `/auth/confirm`. Login page made async to read `searchParams`; `LoginForm` shows redirect error until user submits.

## Bug: Tailwind token collision shrank max-w utilities (2026-06-01)
`--spacing-sm/md` custom tokens shadow Tailwind v4's container scale → `.max-w-md` compiled to 16px. Fix: added semantic `--container-card/panel/content` tokens; swapped all `max-w-{sm,md}` usages to new utilities. Previously hotfixed with arbitrary `max-w-[28rem]` values.

## Bug: proxy.ts wrong location (2026-05-31)
`web/proxy.ts` → `web/src/proxy.ts` so Next.js 16 picks it up alongside `app/`. Unauthenticated users now redirected to `/login`; "Not authenticated" on project creation resolved.

## Phase 4+5 — LLM, storage, planner, Realtime (2026-05-31)
LLM layer (`llm/config.py`, `factory.py`, `schemas.py`) using DeepSeek via OpenAI-compatible endpoint. Storage: tiktoken chunker, batched embedder, `store_source`/`store_chunks` (pgvector `$N::vector` cast), hybrid search via RRF SQL function. Planner handler (`generate_plan` job): coordinator → structured output → delete+insert subtopics (idempotent). Migrations: ivfflat + GIN indexes, `match_chunks()` RRF function, `social_media` tier enum. Web: `createProject` enqueues plan job; `PlanTab` rewired with Approve/Regenerate actions; `ProjectRealtime` component subscribes to subtopics+projects changes.

## Phase 3 — Search infrastructure (2026-05-31)
Full `worker/worker/search/` package: Brave + Tavily web providers, Semantic Scholar academic, trafilatura→Jina extraction chain, tier-based `SearchRouter`. Tenacity retry, provider interface ABCs, config-driven provider selection. 57 mocked tests, no real network required.

## Fix: DB URL encoding + IPv6 diagnostics (2026-06-01)
Two-step fix for Render deploy crashes: (1) `_encode_db_url()` in `config.py` percent-encodes password component (handles `?%@,`); (2) startup DNS logging identifies IPv6-only hosts and names the Session Pooler fix. Port 6543 (transaction pooler) sets `statement_cache_size=0`.

## Config refactor: secrets vs tuning (2026-05-31)
Created `config.toml` for worker tuning (concurrency, poll/heartbeat/watchdog intervals, observability). `worker/config.py` reads tuning via `tomllib`; `.env` contains secrets only.

## Phase 1 — Infrastructure & auth (2026-05-31)
Supabase migrations 0001–0006: pgvector, core tables, jobs+activity, sharing groundwork, RLS policies+helpers, queue RPCs (`claim_job`, `heartbeat_job`, `reclaim_stale_jobs`, `complete_job`, `fail_job`, `cancel_project_jobs`). Worker: asyncpg pool, queue wrappers, claim/dispatch loop with semaphore concurrency, per-job heartbeat, watchdog, graceful SIGTERM drain. Web: `@supabase/ssr` server/browser clients, `proxy.ts` session refresh + route guards, login/signup/signout Server Actions, `getCurrentUser` DAL. Shared Pydantic job payload schemas. `render.yaml` for two-service deploy.

## Feature: dark mode (2026-05-29)
CSS-variable remapping under `.dark` selector (warm-dark palette, no `dark:` utility sprinkling). `next-themes` class strategy. `ThemeProvider` + `ThemeToggle` components. Wired into root layout and TopNav.

## Phase 0 — Frontend shell (2026-05-29)
Next.js 16 / React 19 / Tailwind v4 in `web/`. Design tokens from DESIGN.md. All routes: `/dashboard`, `/project/[id]/{plan,research,sources,chat,report}`. UI component library (Button, Badge, StatusPill, ScorePill, etc.). Mock data layer with swap-ready `client.ts`. Persistent project shell layout (Phase 7 Realtime seam).

## PRD v2 + architecture decisions (2026-05-29)
Replaced Celery/Redis with DB-backed job queue. Two-plane (execution/projection) principle. Supabase Realtime as sole UI sync. Render hosting. Added Phase 0. Eliminated FastAPI (Supabase-native reads+Server Actions). All decisions captured in `decisions.md`.
