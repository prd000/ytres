# File Map

A map of the project codebase — one line per file with its purpose. Update when files are added, renamed, or deleted.

---

## `context/` — Project documentation

| File | Purpose |
|---|---|
| `PRD.md` | Product requirements document — the full v2 spec including architecture decisions, tech stack, data model, and module development order |
| `DESIGN.md` | Design system spec — colors, typography, components, spacing, and brand guidelines. Source of truth for all UI tokens. |
| `decisions.md` | Architectural decisions log — any deviations from PRD or major direction choices |
| `deferredwork.md` | Items to implement later — required API keys, mocked surfaces pending real data, known gaps |
| `log.md` | Build log — running record of everything built/changed, newest first |
| `map.md` | This file — project file map |

## `agent/` — Active planning artifacts

_(no active plans — all phases through 8 complete)_

## `agent-complete/` — Completed planning artifacts

| File | Purpose |
|---|---|
| `phase-0-plan.md` | Phase 0 implementation plan — detailed spec for the navigable frontend shell (complete) |
| `phase-1-plan.md` | Phase 1 implementation plan (Supabase-native, FastAPI-free) — schema/RLS, job queue + RPCs, worker scaffold, Supabase auth wiring (complete) |
| `phase-3-plan.md` | Phase 3 implementation plan — search infrastructure: web providers, Semantic Scholar, extraction chain, router (complete) |
| `phase-4-5-plan.md` | Phase 4+5 implementation plan — storage/embeddings + planner + Realtime + social_media tier (complete) |
| `phase-6-plan.md` | Phase 6 implementation plan — worker research pipeline, LangSmith fix, live Research tab (complete) |
| `phase-8-plan.md` | Phase 8 implementation plan — coordinator review, gap-fill, complete_research RPC, barrier sweep (complete) |

---

## `supabase/` — Supabase project (migrations + config)

| File | Purpose |
|---|---|
| `config.toml` | Supabase CLI project config — ports, auth settings, analytics. Run `supabase start` to launch local stack. |
| `migrations/0001_extensions.sql` | Enable pgvector (1536-dim embeddings) + pgcrypto |
| `migrations/0002_core_tables.sql` | Enums (project_status, source_tier, subtopic_status, chat_role) + tables: projects, subtopics, sources, source_subtopics, source_chunks, chat_messages, reports. Realtime publication declared. |
| `migrations/0003_jobs_and_activity.sql` | job_status enum + jobs table (SKIP LOCKED queue, partial indexes) + worker_activity table. Realtime publication extended. |
| `migrations/0004_sharing.sql` | project_role enum + project_members table (Phase 11 groundwork) |
| `migrations/0005_rls_policies.sql` | RLS enabled on all tables; can_access_project() + can_write_project() SECURITY DEFINER helpers; all SELECT/INSERT/UPDATE/DELETE policies |
| `migrations/0006_rpc.sql` | Queue RPCs: claim_job(), heartbeat_job(), reclaim_stale_jobs(), complete_job(), fail_job(), cancel_project_jobs() |
| `migrations/0007_vector_indexes.sql` | ivfflat cosine + GIN FTS + btree project_id indexes on source_chunks |
| `migrations/0008_match_chunks.sql` | `match_chunks()` SQL function — hybrid vector+keyword search via Reciprocal Rank Fusion |
| `migrations/0009_social_media_tier.sql` | `ALTER TYPE source_tier ADD VALUE 'social_media'` |
| `migrations/0010_fix_projects_select_returning.sql` | Bug #1 fix — `projects_select` checks `owner_id = auth.uid()` directly (plus `can_access_project(id)` for members) so `INSERT … RETURNING` (create-project) passes the SELECT policy |
| `migrations/0011_coordinator_review.sql` | Phase 8 — `subtopics.wave` column; `enqueue_ready_coordinator_reviews()` barrier RPC (advisory lock + NOT EXISTS idempotency); `jobs_review_wave_uniq` partial unique index; `complete_research()` status-transition RPC |

---

## `worker/` — Python async worker (job queue + agent orchestrator)

### `worker/worker/` — Python package

| File | Purpose |
|---|---|
| `__init__.py` | Package marker |
| `config.py` | All tunable constants from env vars (SUPABASE_DB_URL, WORKER_CONCURRENCY, POLL_INTERVAL, HEARTBEAT_INTERVAL, WATCHDOG_INTERVAL, STALE_TIMEOUT_SECONDS, GRACE_SHUTDOWN_SECONDS) |
| `log_config.py` | `setup_logging()` — stdout JSON-ish logging setup |
| `db.py` | asyncpg connection pool — `get_pool()` / `close_pool()`. Direct connection bypasses RLS by design. `register_json_codecs()` (pool `init` callback) makes json/jsonb columns decode to dict/list and encode back automatically. |
| `queue.py` | Thin async wrappers around Postgres queue RPCs (claim_job, heartbeat_job, complete_job, fail_job, reclaim_stale_jobs, cancel_project_jobs) |
| `loop.py` | Core loop: semaphore-bounded claim/dispatch, per-job heartbeat coroutine (detects cancellation), watchdog coroutine (reclaim stale), graceful SIGTERM/SIGINT drain. `JobContext` class passed to handlers. |
| `main.py` | Entry point (`python -m worker.main`): setup_logging, pool init, signal handlers, runs loop.run() |
| `handlers/__init__.py` | `HANDLERS` registry mapping job type strings to handler coroutines |
| `handlers/echo.py` | Phase 1 proof-of-concept handler: checkpoints through steps, echoes payload.message, completes |
| `handlers/planner.py` | Phase 5 planner handler (job type `generate_plan`): reads project, calls DeepSeek coordinator, writes subtopics in transaction |
| `handlers/research.py` | Phase 6 research handler (job type `research_subtopic`): full pipeline — query gen → search → pass-1 filter → extraction → pass-2 eval → store with embeddings. Supports checkpointing, context-window handoff, source cap (12), auto-retry, why-nothing report, cancellation. |
| `handlers/coordinator.py` | Phase 8 coordinator handler (job type `coordinator_review`): loads coverage data, invokes LLM for CoverageReview, either spawns gap-fill subtopics+jobs (wave 1 w/gaps) or calls complete_research() |

### `worker/worker/llm/` — Phase 5 LLM layer

| File | Purpose |
|---|---|
| `__init__.py` | Package marker |
| `config.py` | Frozen `LLMConfig` dataclass + `from_env()` reading `config.toml [llm]` + env (no DB dep) |
| `factory.py` | `build_chat_model(cfg, role)` — returns `ChatOpenAI` pointed at DeepSeek base_url; provider swap = config edit |
| `schemas.py` | Structured-output Pydantic models: `SourceTier`, `PlannedSubtopic`, `ResearchPlan` (3–8 subtopics guardrail), `CoverageReview` (Phase 8 coordinator output) |

### `worker/worker/storage/` — Phase 4 storage & embeddings

| File | Purpose |
|---|---|
| `__init__.py` | Package marker |
| `chunking.py` | `count_tokens()` + `chunk_text()` — pure, no I/O; tiktoken cl100k_base sliding window |
| `embeddings.py` | `Embedder` class wrapping `AsyncOpenAI`; batched ≤128, order-preserving, dimension-asserted |
| `store.py` | `store_source()` (upsert + subtopic link) + `store_chunks()` (executemany `$N::vector` string cast) |
| `activity.py` | `upsert_activity()` (ON CONFLICT update worker_activity) + `set_subtopic_status()` (update subtopics.status enum) — Phase 6 progress writes |
| `search.py` | `match_chunks()` — calls the SQL function, returns `ChunkMatch` list |

### `worker/worker/search/` — Phase 3 search infrastructure

| File | Purpose |
|---|---|
| `__init__.py` | Public surface: `build_router(cfg)`, `SearchRouter`, all models/errors re-exported |
| `models.py` | Pydantic models: `SearchResult`, `ExtractedContent`, `SearchFailure`, `SearchResponse`, `Tier` literal |
| `errors.py` | Exception hierarchy: `SearchError`, `ProviderUnavailable`, `ExtractionFailed`, `ConfigError` |
| `config.py` | Frozen `SearchConfig` dataclass; `from_env()` reads `config.toml [search]` + env (no DB dep) |
| `retry.py` | `with_retry()` tenacity exponential-backoff policy; `make_client()` shared httpx factory |
| `base.py` | ABCs: `WebSearchProvider`, `ContentExtractor` |
| `web/__init__.py` | Package marker |
| `web/brave.py` | `BraveProvider` — snippets only, tier-tagged |
| `web/tavily.py` | `TavilyProvider` — sets `raw_content` from `include_raw_content=true` |
| `web/factory.py` | `build_web_provider(name, cfg)` — config-driven provider select; raises `ConfigError` on unknown/missing-key |
| `academic/__init__.py` | Package marker |
| `academic/semantic_scholar.py` | `SemanticScholarClient` — keyless Graph API; metadata + abstract + open-access PDF URL |
| `extraction/__init__.py` | Package marker |
| `extraction/trafilatura_extractor.py` | `TrafilaturaExtractor` — sync trafilatura wrapped via `asyncio.to_thread` |
| `extraction/jina_extractor.py` | `JinaExtractor` — async Jina Reader fallback (`https://r.jina.ai/{url}`) |
| `extraction/chain.py` | `ExtractionChain` — raw_content short-circuit → trafilatura → Jina; raises `ExtractionFailed` |
| `router.py` | `SearchRouter` — tier fan-out with `asyncio.gather`; partial-failure collection; all-down → `SearchError` |

### `worker/tests/` — pytest tests

| File | Purpose |
|---|---|
| `conftest.py` | asyncpg pool fixture + seed helpers (_seed_user, _seed_project, _seed_subtopic, _enqueue_job) |
| `test_queue.py` | Integration tests: SKIP LOCKED correctness, claim/heartbeat/reclaim/cancel/idempotent-resume scenarios against real Postgres |
| `test_contract.py` | Pydantic contract tests for EchoPayload and WorkerActivityRow schemas |
| `test_search_models.py` | Phase 3 contract/validation tests for search models |
| `test_retry.py` | Retry policy: 500×2→200, 429 retry, 401 fast-fail, all-503 → ProviderUnavailable (respx mocked) |
| `test_web_providers.py` | Brave/Tavily parsing, factory, missing-key errors (respx mocked) |
| `test_academic.py` | Semantic Scholar parsing, PDF URL, fallback URL (respx mocked) |
| `test_extraction.py` | raw_content short-circuit, trafilatura (monkeypatched), Jina (respx), fallback chain |
| `test_search_router.py` | Tier routing, de-duplication, single web call (v1), provider tagging |
| `test_degradation.py` | Partial failures (one backend down), all-down → SearchError |
| `test_chunking.py` | Pure unit tests: empty, short, long overlap, token limits, index sequence |
| `test_embeddings.py` | Fake AsyncOpenAI: dimensions, order, empty→no-call, 300-text batching |
| `test_storage.py` | Integration: store_source insert/dedup/idempotent link; store_chunks vector rows |
| `test_hybrid_search.py` | Integration: vector-near ranks high, keyword surfaces, project scoping, match_count limit, scores descending |
| `test_planner.py` | Mocked LLM: subtopic count/order/enum-array, regenerate, idempotent, cancel pre/post-LLM, status unchanged |
| `test_research.py` | Mocked LLM + router + embedder + extraction + DB: store rule pass/fail, source cap (12), min-target triggers second wave, why-nothing, pre/post-LLM cancel, handoff enqueues continuation, resume skips processed URLs, activity upsert sequence |
| `test_coordinator.py` | Mocked LLM + real DB: wave1-gaps inserts subtopics+jobs, wave1-nogaps calls complete_research, wave2 always completes, pre/post-LLM cancel, non-researching skip, _load_coverage assembly |
| `test_barrier.py` | Real Postgres via `db` fixture (migration 0011 required): barrier enqueues wave1, idempotent, waits while in-flight, fires on all-failed, skips cancelled, wave2 after gap-fill, no wave3, complete_research transitions/noop |

| Root file | Purpose |
|---|---|
| `pyproject.toml` | Package config: asyncpg/pydantic/python-dotenv/httpx/trafilatura/tenacity deps; respx test dep |

---

## `shared/` — Shared contracts between worker and web

| File | Purpose |
|---|---|
| `schemas/__init__.py` | Package marker |
| `schemas/job_payloads.py` | Pydantic models: EchoPayload, GeneratePlanPayload, ResearchSubtopicPayload, CoordinatorReviewPayload, WorkerActivityRow, JOB_PAYLOAD_MODELS registry |

---

## Root files

| File | Purpose |
|---|---|
| `.env.example` | All environment variables documented with usage notes |
| `render.yaml` | Render deployment: ytres-web (Next.js Web Service) + ytres-worker (Background Worker) |

---

## `web/` — Next.js frontend (Phase 0+)

### Root config

| File | Purpose |
|---|---|
| `package.json` | Dependencies and npm scripts (includes @supabase/ssr, @supabase/supabase-js, server-only added in Phase 1) |
| `tsconfig.json` | TypeScript strict config with `@/` path alias |
| `next.config.ts` | Next.js configuration |
| `postcss.config.mjs` | PostCSS config (`@tailwindcss/postcss`) |
| `proxy.ts` | Next.js 16 Proxy (replaces middleware.ts) — session refresh + auth redirects for (app) routes |
| `public/brand/spike-mark.svg` | Anthropic radial spike-mark brand glyph (SVG asset) |

### `src/app/` — App Router routes

| File | Purpose |
|---|---|
| `layout.tsx` | Root layout — loads Cormorant Garamond/Inter/JetBrains Mono via `next/font`, sets `<html>` font CSS vars (+ `suppressHydrationWarning`), wraps children in `ThemeProvider`, imports `globals.css` |
| `globals.css` | Tailwind `@import` + `@custom-variant dark` + `@theme` design token block (all DESIGN.md colors, radius, spacing, fonts) + `.dark{}` warm-dark role-token remap + typography composite utility classes |
| `page.tsx` | Root route — redirects to `/dashboard` |
| `(auth)/layout.tsx` | Auth route group layout (minimal, no chrome) |
| `(auth)/login/page.tsx` | Login page — renders `AuthShell` + `LoginForm` |
| `(auth)/signup/page.tsx` | Signup page — renders `AuthShell` + `SignupForm` |
| `(auth)/actions.ts` | `"use server"` auth Server Actions: `login`, `signup`, `signOut` — call Supabase auth, return `{error}` or `redirect()` |
| `(app)/layout.tsx` | App route group layout — async; calls `getCurrentUser()`, passes user + `signOut` to `TopNav`; renders TopNav + main + Footer |
| `(app)/dashboard/page.tsx` | Dashboard — fetches projects via `client.ts`, renders `DashboardView` |
| `(app)/project/[id]/layout.tsx` | **Project shell layout** — fetches project, renders `ProjectShellHeader` + `ProjectTabNav` + `{children}`. STAYS MOUNTED across tab switches. Phase 7 Realtime seam. |
| `(app)/project/[id]/page.tsx` | Redirects `/project/[id]` → `/project/[id]/plan` |
| `(app)/project/[id]/plan/page.tsx` | Plan tab — fetches project + subtopics |
| `(app)/project/[id]/research/page.tsx` | Research tab — fetches project + subtopics + worker activity |
| `(app)/project/[id]/sources/page.tsx` | Sources tab — fetches project + subtopics + sources |
| `(app)/project/[id]/chat/page.tsx` | Chat tab — fetches project + chat messages |
| `(app)/project/[id]/report/page.tsx` | Report tab — fetches project + sources + existing report |
| `(app)/project/actions.ts` | `"use server"` Server Actions: `createProject` (insert + enqueue generate_plan), `regeneratePlan` (re-enqueue + set planning), `approvePlan` (set researching), `deleteProject` (cancel_project_jobs RPC + cascade delete + redirect to dashboard) |
| `(app)/project/new/page.tsx` | New project page — server component rendering `NewProjectForm` |

### `src/lib/` — Utilities and data layer

| File | Purpose |
|---|---|
| `utils.ts` | `cn()` (clsx + tailwind-merge), `formatRelativeDate()` |
| `design/tokens.ts` | TS-side design maps: `STATUS_META` (ProjectStatus → label/toneClass/dotClass), `scoreClass()`, `scoreBarClass()` |
| `data/types.ts` | Domain types: `ProjectStatus`, `SourceTier`, `SubtopicStatus`, `Project`, `Subtopic`, `Source`, `WorkerActivity`, `ChatMessage`, `Report`. Verbatim-reusable by real Supabase client. |
| `data/client.ts` | Real Supabase data-access layer — 7 async fns with row→domain mappers; `"server-only"` guard. `fixtures.ts` deleted. |
| `data/dal.ts` | `getCurrentUser()` — server-only, React cache()-memoized, reads Supabase auth session |
| `supabase/client.ts` | `createClient()` — `createBrowserClient` for Client Components |
| `supabase/server.ts` | `createClient()` — `createServerClient` with async cookies() adapter (`server-only`) |
| `supabase/admin.ts` | `createAdminClient()` — service-role client for privileged Server Actions (`server-only`) |
| `supabase/proxy-session.ts` | `updateSession()` — session refresh helper for proxy.ts; returns `{response, user}` |

### `src/components/ui/` — Design system primitives

| File | Purpose |
|---|---|
| `Button.tsx` | Button variants (primary/secondary/secondaryOnDark/text/icon/destructive) via cva |
| `TextLink.tsx` | Coral text link — internal (next/link) or external |
| `Card.tsx` | `Card` + `Surface` — surface prop: canvas/canvas-bordered/card/dark/dark-elevated/coral |
| `Input.tsx` | `Input` (text input) + `Textarea` — coral focus ring, hairline border |
| `Badge.tsx` | `Badge` — variants: pill (cream-card), coral (uppercase), outline |
| `StatusPill.tsx` | `StatusPill` — maps `ProjectStatus` to semantic color via `STATUS_META` |
| `ScorePill.tsx` | `ScorePill` (score/5 with color) + `ScoreBar` (horizontal bar) |
| `Callout.tsx` | `Callout` — variants: coral, info (teal), warning |
| `SpikeMark.tsx` | Anthropic radial spike-mark as inline SVG React component |

### `src/components/theme/` — Dark mode

| File | Purpose |
|---|---|
| `ThemeProvider.tsx` | `"use client"` next-themes wrapper (class strategy, system default) — mounted in root layout |
| `ThemeToggle.tsx` | `"use client"` circular sun/moon toggle button (DESIGN.md `button-icon-circular`); `mounted` guard, calls `useTheme()`. Mounted in TopNav desktop + mobile |

### `src/components/layout/` — Layout components

| File | Purpose |
|---|---|
| `PageContainer.tsx` | Max-1200px centered container with responsive horizontal padding |
| `TopNav.tsx` | `"use client"` 64px cream sticky nav — accepts `user` + `signOut` props; signed-in cluster (email + sign-out form action) vs signed-out cluster (sign-in/get-started links); mobile hamburger → Radix Dialog sheet |
| `Footer.tsx` | Dark navy footer — wordmark, nav links, copyright |
| `AuthShell.tsx` | Centered cream card layout for login/signup screens |
| `ProjectShellHeader.tsx` | Project title (serif), StatusPill, optional Cancel button, `DeleteProjectButton` |
| `DeleteProjectButton.tsx` | `"use client"` — error-toned Delete trigger + Radix Dialog confirmation; `useActionState(deleteProject)` → cascade DB delete + redirect to dashboard |
| `ProjectTabNav.tsx` | `"use client"` — tab links using `usePathname()` for active state; category-tab token styling |

### `src/components/features/` — Feature composites

| File | Purpose |
|---|---|
| `auth/LoginForm.tsx` | `"use client"` email/password form — `useActionState(login)` + `<form action={action}>`; shows server error, pending state |
| `auth/SignupForm.tsx` | `"use client"` name/email/password form — `useActionState(signup)` + `<form action={action}>`; shows server error, pending state |
| `dashboard/DashboardView.tsx` | Projects grid + New project button |
| `dashboard/ProjectCard.tsx` | Project card — research question, StatusPill, relative date |
| `dashboard/EmptyState.tsx` | Empty dashboard state with CTA |
| `plan/PlanTab.tsx` | `"use client"` — source tier display, subtopic list; real Approve/Regenerate Server Actions via useActionState; loading dots when planning with no subtopics |
| `realtime/ProjectRealtime.tsx` | `"use client"` — Supabase Realtime subscription for subtopics+projects; calls router.refresh() on changes; mounted in project layout |
| `project/NewProjectForm.tsx` | `"use client"` — create-project form: research question, tier checkboxes, recency months, `useActionState(createProject)` |
| `research/ResearchTab.tsx` | Subtopic progress cards with animated running dots, latest activity, sources-stored count |
| `sources/SourcesTab.tsx` | Sources grouped by subtopic |
| `sources/SourceCard.tsx` | Source card — title (external TextLink), key takeaway, 4 ScorePills, tier Badge |
| `chat/ChatTab.tsx` | `"use client"` — scrollable message thread; composer disabled (Phase 9 RAG pending) |
| `chat/ChatMessage.tsx` | Chat bubble (user=coral, assistant=card) with citation chips |
| `report/ReportTab.tsx` | `"use client"` — source selector + disabled Generate button (Phase 10 pending) + .md download + preview |
| `report/SourceSelector.tsx` | Checkbox list with 25-source cap enforcement |
| `report/ReportPreview.tsx` | `"use client"` — react-markdown with design-token styled components |
