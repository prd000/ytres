# Build Log

A running record of everything built/changed. Newest first.

---

## 2026-06-01 — Fix: URL-encode DB password in SUPABASE_DB_URL

Render deploy crashed with `ValueError: bad query field: '%hT@C6,'` because the Supabase database password contains URL-special characters (`%`, `@`, `,`) that asyncpg's DSN parser rejected.

Added `_encode_db_url()` helper in `worker/worker/config.py` that percent-encodes the password component of the DSN using `urllib.parse.quote` before the URL is used anywhere. No change required to Render env vars.

---

## 2026-05-31 — Config refactor: secrets vs tuning

Separated non-sensitive configuration from secrets.

- Created `config.toml` at repo root — worker tuning (`concurrency`, `poll_interval`, `heartbeat_interval`, `watchdog_interval`, `stale_timeout_seconds`, `grace_shutdown_seconds`) and observability settings (`langchain_tracing`, `langchain_project`) now live here. Safe to commit.
- Updated `worker/worker/config.py` to read tuning from `config.toml` via stdlib `tomllib`; only `SUPABASE_DB_URL` (and other API keys) remain in `.env`.
- Stripped tuning vars and `LANGCHAIN_TRACING_V2`/`LANGCHAIN_PROJECT` from `.env` and `.env.example`. `.env` now contains secrets only.

---

## 2026-05-31 — Phase 1: Infrastructure & Auth (Supabase-native)

Built the full Phase 1 foundation: Supabase schema/migrations, database-backed job queue worker, real Supabase auth wired into the Next.js 16 shell, shared Pydantic schemas, Render deployment config, and pytest integration test suite.

### Architecture note: FastAPI eliminated
Phase 1 eliminates FastAPI entirely (recorded in `decisions.md`). The web frontend reads via `@supabase/ssr` server client (RLS-enforced) and writes via Server Actions. The Python worker is the only backend service; job enqueue is a row INSERT or `SECURITY DEFINER` RPC. Two services deploy to Render: `ytres-web` (Next.js) and `ytres-worker` (Python).

### Supabase migrations (`supabase/migrations/`)
- `0001_extensions.sql` — `vector` (pgvector, 1536-dim) + `pgcrypto`.
- `0002_core_tables.sql` — enums (`project_status`, `source_tier`, `subtopic_status`, `chat_role`) exactly mirroring `types.ts`; tables: `projects`, `subtopics`, `sources` (unique `project_id,url`), `source_subtopics`, `source_chunks` (`embedding vector(1536)`; ivfflat index deferred to Phase 4), `chat_messages`, `reports`. Realtime publication for these tables declared.
- `0003_jobs_and_activity.sql` — `job_status` enum + `jobs` table (partial indexes on `status='queued'` and `status='running'`) + `worker_activity` (one row per subtopic, PK). Realtime publication extended.
- `0004_sharing.sql` — `project_role` enum + `project_members` table. Phase 11 groundwork; no invite UX yet.
- `0005_rls_policies.sql` — RLS enabled on all app tables; `can_access_project()` and `can_write_project()` SECURITY DEFINER helpers; SELECT/INSERT/UPDATE/DELETE policies for all tables.
- `0006_rpc.sql` — `claim_job()` (SKIP LOCKED), `heartbeat_job()` (bump + optional checkpoint, returns status), `reclaim_stale_jobs()`, `complete_job()`, `fail_job()` (retry if under max_attempts), `cancel_project_jobs()`.

### Worker scaffold (`worker/`)
- `worker/config.py` — all tunable constants (`SUPABASE_DB_URL`, concurrency, poll/heartbeat/watchdog intervals) read from env vars; no hard-coding.
- `worker/db.py` — asyncpg pool (direct connection, RLS bypassed by design).
- `worker/queue.py` — thin async wrappers around the Postgres queue RPCs.
- `worker/loop.py` — main claim/dispatch loop; `asyncio.Semaphore(CONCURRENCY)` bounds in-flight jobs; per-job heartbeat coroutine detects cancellation; separate watchdog coroutine reclaims stale jobs; graceful SIGTERM/SIGINT drain.
- `worker/main.py` — entry point (`python -m worker.main`); signal handlers; worker-id = hostname+uuid.
- `worker/handlers/echo.py` — Phase 1 proof-of-concept: reads `payload.message`, runs checkpoint steps with sleeps (heartbeats observable), echoes message, completes. No LLM calls.

### Web: real Supabase auth (`web/`)
- Installed: `@supabase/ssr`, `@supabase/supabase-js`, `server-only`.
- `web/src/lib/supabase/client.ts` — `createBrowserClient` for Client Components.
- `web/src/lib/supabase/server.ts` — `createServerClient` with async `cookies()` adapter (`server-only`).
- `web/src/lib/supabase/admin.ts` — service-role client (`server-only`, `SUPABASE_SERVICE_ROLE_KEY`).
- `web/src/lib/supabase/proxy-session.ts` — session refresh helper for proxy.ts context.
- `web/proxy.ts` — Next.js 16 `proxy()` export: refreshes session, redirects unauthenticated users away from `(app)` routes, redirects authenticated users away from auth routes.
- `web/src/app/(auth)/actions.ts` — `"use server"` `login` / `signup` / `signOut` Server Actions; return `{error}` for `useActionState`, `redirect()` on success.
- `web/src/lib/data/dal.ts` — `getCurrentUser()` (server client + React `cache()`).
- Modified `LoginForm.tsx` / `SignupForm.tsx` — replaced mocked `router.push` with `useActionState` + `<form action={action}>` + error display.
- Modified `TopNav.tsx` — accepts `user` and `signOut` props; signed-in cluster shows email + sign-out form action; signed-out cluster shows sign-in/get-started links.
- Modified `(app)/layout.tsx` — async; calls `getCurrentUser()` + passes user + `signOut` Server Action to TopNav.

### Shared contracts (`shared/`)
- `shared/schemas/job_payloads.py` — `EchoPayload`, `WorkerActivityRow` Pydantic models; `JOB_PAYLOAD_MODELS` registry.

### Deployment config
- `render.yaml` — two services: `ytres-web` (Next.js Web Service) and `ytres-worker` (Python Background Worker). No `api` service.
- `.env.example` — documents every variable with usage notes (`NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_DB_URL`, worker tuning constants, future phase vars).
- `worker/pyproject.toml` — hatchling build, asyncpg/pydantic/python-dotenv deps, pytest-asyncio test config.

### Tests (`worker/tests/`)
- `test_queue.py` — integration tests against real Postgres (SKIP LOCKED correctness, claim/heartbeat/reclaim/cancellation/idempotent-resume scenarios).
- `test_contract.py` — Pydantic schema contract tests for `EchoPayload` and `WorkerActivityRow`.

**`npm run build`** — clean, zero TypeScript errors.

---

## 2026-05-31 — Architecture: eliminate FastAPI (Supabase-native) + Phase 1 plan rewrite

Decided to **drop the FastAPI backend** before any of it was built. The web (Next.js) now talks to Supabase directly — reads via the `@supabase/ssr` server client (RLS), writes/CRUD/enqueue via Server Actions (RLS + `SECURITY DEFINER` RPCs) — and the **Python worker is the only backend service** (and the agent orchestrator). Rationale: FastAPI was a thin auth/CRUD/enqueue shim that never orchestrated agents; removing it loses no capability, aligns the read shape with the Phase 7 Realtime shape, and exercises RLS as a real control. RAG chat will run as a job; a sync endpoint is deferred to Phase 9.

- **`decisions.md`** — added the dated decision (eliminate FastAPI / Supabase-native), incl. state-machine-in-Postgres and reads-RLS / writes-Server-Actions.
- **`PRD.md`** — Tech Stack: replaced the "Backend API: FastAPI" bullet with the Supabase-native frontend/data bullet; worker is the only backend service; hosting drops the API Web Service; two-plane execution trigger is now a Server Action; Phase 1 module drops "FastAPI scaffold"; auth test module updated (`proxy.ts` + RLS).
- **`deferredwork.md`** — env vars: split public `NEXT_PUBLIC_*`, `SUPABASE_SERVICE_ROLE_KEY` now used by Next.js server-side, added `SUPABASE_DB_URL` (worker asyncpg); Render row drops the API service.
- **`agent/phase-1-plan.md`** — rewritten FastAPI-free (removed the `api/` scaffold, JWT verifier, `/me`, FastAPI auth tests, `SUPABASE_JWT_SECRET`/`CORS_ALLOW_ORIGINS`); kept schema, RLS, queue + RPCs, worker scaffold, and Supabase auth wiring; added a server-only service-role client for Next.js.

No application code changed yet — docs + Phase 1 plan only.

---

## 2026-05-29 — Major Feature #1: Dark Mode

Added a site-wide dark mode toggle. Implemented via **CSS-variable remapping**, not `dark:` utility sprinkling — because every component already uses semantic token utilities (`bg-canvas`, `text-ink`, `border-hairline`) that compile to `var(--color-*)`, overriding those variable values under a `.dark` selector flips the whole app with essentially zero component edits.

**Dependency:** `next-themes` (class strategy → toggles `.dark` on `<html>`; handles SSR no-flash + system-preference + localStorage persistence).

**`globals.css`:**
- Registered Tailwind v4 `@custom-variant dark (&:where(.dark, .dark *))` for any targeted `dark:` overrides.
- Added a `.dark { … }` block remapping the **role** tokens to a warm-dark palette (warm near-blacks, never cool slate — brand stays warm per DESIGN.md). Elevation hierarchy preserved: `canvas` (darkest floor) → `surface-soft` → `surface-card`. Text inverts dark→light. Coral `primary`/`primary-active` lifted slightly for legibility on dark.
- **Not** remapped (kept literal): semantic accents (success/warning/error/teal/amber), `on-primary`, and the always-dark surfaces (`surface-dark*`, `on-dark*`) used by the Footer, code blocks, and dark product cards.

**New components:**
- `src/components/theme/ThemeProvider.tsx` — `"use client"` next-themes wrapper (`attribute="class"`, `defaultTheme="system"`, `enableSystem`, `disableTransitionOnChange`).
- `src/components/theme/ThemeToggle.tsx` — `"use client"` circular sun/moon icon button styled per DESIGN.md `button-icon-circular` (36px, canvas bg, hairline border, ink icon). `mounted` guard prevents hydration mismatch; aria-label reflects target mode.

**Wiring:**
- `app/layout.tsx` — added `suppressHydrationWarning` on `<html>` (required by next-themes) and wrapped `{children}` in `<ThemeProvider>`.
- `TopNav.tsx` — `<ThemeToggle />` added to the desktop right cluster and the mobile menu header. Fixed the Radix Dialog overlay scrim (`bg-ink/40` → `bg-[#141413]/50`) so it stays a dark scrim in both modes (`ink` flips to light in dark mode).

**`npm run build`** — clean, zero TS errors.

---

## 2026-05-29 — Phase 0: Navigable Frontend Shell

Built the complete Phase 0 frontend shell into `ytres/web/` (Next.js 16 App Router, TypeScript strict, Tailwind v4, src/ dir).

**Tooling & setup:**
- Next.js 16.2.6 (Turbopack), React 19, TypeScript strict, Tailwind v4 CSS-first `@theme`
- Fonts: Cormorant Garamond (display serif), Inter (humanist sans), JetBrains Mono — wired via `next/font/google` CSS variables
- Deps: `@radix-ui/react-tabs`, `@radix-ui/react-dialog` (mobile nav), `class-variance-authority`, `tailwind-merge`, `clsx`, `react-markdown`
- `npm run build` — clean, zero TS errors. Zero inline hex in components (design-token guardrail).

**Design tokens (`globals.css` `@theme`):**
- All DESIGN.md colors, border-radius, spacing, and font families mapped to CSS custom properties
- Typography composite utility classes: `.text-display-xl/lg/md/sm`, `.text-title-lg/md/sm`, `.text-body-md/sm`, `.text-caption`, `.text-caption-uppercase`, `.text-button`, `.text-nav-link`

**Data layer (`src/lib/data/`):**
- `types.ts` — domain types mirroring the PRD data model (verbatim-reusable by real client)
- `fixtures.ts` — 5 projects (one of each status), subtopics, sources (incl. low-quality score set), worker activity, full chat thread with citations, complete markdown report
- `client.ts` — async data-access fns (getProjects, getProject, getSubtopics, getSources, getWorkerActivity, getChatMessages, getReport) — the swappable mock→real seam

**Components:**
- `src/components/ui/` — Button (5 variants, cva), TextLink, Card/Surface, Input/Textarea, Badge, StatusPill, ScorePill/ScoreBar, Callout, SpikeMark
- `src/components/layout/` — TopNav (64px, mobile hamburger via Radix Dialog), Footer (dark navy), AuthShell, ProjectShellHeader, ProjectTabNav (usePathname active state), PageContainer
- `src/components/features/` — auth (LoginForm, SignupForm), dashboard (DashboardView, ProjectCard, EmptyState), plan (PlanTab), research (ResearchTab), sources (SourcesTab, SourceCard), chat (ChatTab, ChatMessage), report (ReportTab, SourceSelector, ReportPreview)

**Routes (all verified in build):**
- `/` → redirect to `/dashboard`
- `/login`, `/signup` — auth shell forms
- `/dashboard` — ProjectList grid
- `/project/[id]` → redirect to `/plan`
- `/project/[id]/{plan,research,sources,chat,report}` — all tabs, mocked data

**Persistent shell confirmed:** `(app)/project/[id]/layout.tsx` renders ProjectShellHeader + ProjectTabNav + `{children}` — only `page.tsx` swaps on tab navigation. This is the Phase 7 Realtime seam.

---

## 2026-05-29 — Verified DeepSeek V4 models; corrected context-window framing

- Confirmed via web search that `deepseek-v4-pro` and `deepseek-v4-flash` are real, current model IDs (both 1M-token context, three reasoning-effort modes). Legacy `deepseek-chat`/`deepseek-reasoner` aliases deprecated 2026-07-24.
- Updated `PRD.md`: exact model IDs in Tech Stack + Further Notes; reframed the 100K-token ceiling as a **self-imposed cost/quality guardrail** (tunable constant), not a model limit.
- Resolved the DeepSeek open question in `deferredwork.md`.

## 2026-05-29 — PRD v2 rewrite + architecture decisions captured

- Rewrote `context/PRD.md` as v2 for the fresh attempt. Key changes:
  - Replaced Celery + Redis async model with a **database-backed job queue** (Postgres `FOR UPDATE SKIP LOCKED` + `asyncio` concurrency, worker heartbeats, self-healing watchdog).
  - Added the **two-plane (execution / projection)** core principle to fix v1 agent orphaning; added user story #31 (research survives tab close).
  - Made **Supabase Realtime** the sole UI sync mechanism; removed the SSE/Redis contradiction.
  - Committed hosting to **Render** (frontend + API as Web Services, worker as Background Worker) with managed Supabase.
  - Added a **Phase 0: Navigable Frontend Shell** to the module order for QA-from-day-one; renumbered subsequent phases and moved the worker/queue scaffold into Phase 1.
  - Added an explicit **LLM vs. non-LLM task split** table.
  - Added `jobs` and `worker_activity` tables to the data model; added a `queue` test module.
- Created `context/decisions.md` with five dated decisions (job queue, two-plane, Realtime, Render, Phase 0).
- Created `context/deferredwork.md` capturing required API keys / env vars (DeepSeek, OpenAI embeddings, Brave/Tavily, Jina, Supabase, LangSmith, Render).
- No application code yet — repo still contains only `context/` docs and `CLAUDE.md`.
