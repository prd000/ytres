# Build Log

A running record of everything built/changed. Newest first.

---

## 2026-05-31 — Phase 4 + 5 (Storage, Embeddings, Planner) + Realtime + social_media tier

### Part A — Worker LLM layer (`worker/worker/llm/`)
- `llm/config.py` — frozen `LLMConfig` dataclass + `from_env()` reading `config.toml [llm]` + env vars.
- `llm/factory.py` — `build_chat_model(cfg, role)` returning `ChatOpenAI` pointed at DeepSeek's OpenAI-compatible endpoint (`base_url` in config); provider swap = config edit.
- `llm/schemas.py` — `SourceTier` literal, `PlannedSubtopic`, `ResearchPlan` (3–8 subtopics guardrail) for structured output.
- `config.toml` — added `[llm]` block with model IDs, temperature, timeout, embedding model/dims.
- `worker/worker/config.py` — added `DEEPSEEK_API_KEY` and `OPENAI_API_KEY` from env.
- `worker/pyproject.toml` — added `langchain-core>=0.3`, `langchain-openai>=0.2`, `openai>=1.40`, `tiktoken>=0.7`.

### Part B — Storage & Embeddings (`worker/worker/storage/`)
- `storage/chunking.py` — `count_tokens()` + `chunk_text()` using tiktoken cl100k_base; sliding window with configurable chunk/overlap tokens.
- `storage/embeddings.py` — `Embedder` wrapping `AsyncOpenAI`; batched ≤128, order-preserving, dimension-asserted.
- `storage/store.py` — `store_source()` (upsert with `xmax=0` created flag + subtopic link) and `store_chunks()` (executemany with `$N::vector` string-cast); no pgvector codec required.
- `storage/search.py` — `match_chunks()` wrapper calling the `match_chunks` SQL function, returns `ChunkMatch` list.

### Part C — Planner handler (`worker/worker/handlers/planner.py`, job type `generate_plan`)
- `handlers/planner.py` — reads project row, builds coordinator messages, invokes DeepSeek with `function_calling`→`json_mode` fallback, delete-then-inserts subtopics in a transaction (idempotent on resume/regenerate).
- `shared/schemas/job_payloads.py` — added `GeneratePlanPayload`; registered `generate_plan` in `JOB_PAYLOAD_MODELS`.
- `handlers/__init__.py` — registered `"generate_plan": planner_handle`.

### Part D — SQL migrations
- `0007_vector_indexes.sql` — ivfflat cosine index + GIN FTS index + btree project_id index on `source_chunks`.
- `0008_match_chunks.sql` — `match_chunks()` SQL function; vector CTE + keyword CTE full-outer-joined via Reciprocal Rank Fusion.
- `0009_social_media_tier.sql` — `ALTER TYPE source_tier ADD VALUE IF NOT EXISTS 'social_media'`.

### Part E — Web Server Actions + Plan tab rewrite
- `web/src/app/(app)/project/actions.ts` — `createProject` now sets `status: "planning"` and enqueues `generate_plan` job on submit. Added `regeneratePlan` (insert job + set planning + revalidate) and `approvePlan` (set researching + revalidate) Server Actions.
- `web/src/components/features/plan/PlanTab.tsx` — rewrote action area: loading dots when planning with no subtopics; real Approve/Regenerate forms via `useActionState` + `.bind()`; two separate forms sharing a textarea via HTML `form` attribute (no nesting).

### Part F — Realtime (pulled forward)
- `web/src/components/features/realtime/ProjectRealtime.tsx` — `"use client"` component subscribing to `postgres_changes` on `subtopics` + `projects` filtered by project ID; calls `router.refresh()` on any event.
- `web/src/app/(app)/project/[id]/layout.tsx` — mounts `<ProjectRealtime projectId={id} />` so subscription stays live across tab switches.

### Part G — `social_media` source tier (cross-cutting)
- `web/src/lib/data/types.ts` — `SourceTier` union + `socialMedia: boolean` to `SourceTierSettings`.
- `web/src/components/features/project/NewProjectForm.tsx` — added `{ key: "social_media", label: "Social media" }` tier checkbox.
- `web/src/app/(app)/project/actions.ts` (createProject) — reads `social_media` checkbox → `socialMedia` in `SourceTierSettings`.
- `web/src/components/features/plan/PlanTab.tsx` — added `social_media: "Social media"` to `TIER_LABELS`; renders in source-preferences block and subtopic tier badges.

### Tests
- `worker/tests/test_chunking.py` — pure unit tests (empty, short, long, overlap error, token limits).
- `worker/tests/test_embeddings.py` — fake AsyncOpenAI client; dimension check, order preservation, empty→no call, 300-text batching.
- `worker/tests/test_storage.py` — integration vs real PG: store_source insert/dedup/idempotent link; store_chunks vector rows.
- `worker/tests/test_hybrid_search.py` — integration: vector-near ranks high, keyword surfaces, project scoping, match_count limit, scores descending.
- `worker/tests/test_planner.py` — mocked LLM; subtopic count/order/enum-array; regenerate replaces; idempotent resume; pre/post-LLM cancellation; status unchanged; missing project raises; checkpoint sequence.
- `worker/tests/test_contract.py` — extended with `GeneratePlanPayload` valid/invalid/missing-id and registry assertions.

---

## 2026-05-31 — Fix "Not authenticated" on project creation + auth page spacing (bug #1)

### Root cause
`web/proxy.ts` was at the Next.js project root, but the app lives under `web/src/app/`. Next.js 16 only picks up `proxy.ts` when it sits alongside `app/` — i.e. at `web/src/proxy.ts`. With the proxy silently ignored, unauthenticated users reached protected routes without being redirected to `/login`, and only hit the wall when `createProject`'s `supabase.auth.getUser()` returned null.

### Changes
- **`web/proxy.ts` → `web/src/proxy.ts`** (content unchanged): proxy now runs on every request, refreshing the Supabase session and redirecting unauthenticated visitors away from `(app)` routes. "Not authenticated" error on project creation is resolved.
- **`web/src/components/layout/AuthShell.tsx`**: card widened `max-w-sm` → `max-w-md` (448px); header bottom margin `mb-6` → `mb-8`; subtitle top margin `mt-1` → `mt-2` — matches DESIGN.md generous-whitespace intent.
- **`web/src/components/features/auth/LoginForm.tsx`** and **`SignupForm.tsx`**: field gap `gap-4` → `gap-5`; label↔input gap `gap-1.5` → `gap-2`; submit button top margin `mt-2` → `mt-4` for editorial breathing room.

---

## 2026-05-31 — Remove dummy data; wire real Supabase reads; add create-project flow

### What changed

**Data layer — `web/src/lib/data/client.ts` (rewritten):**
- All seven data-access functions now query live Supabase tables via `createClient()` from `@/lib/supabase/server` (RLS-enforced, returns only the signed-in user's rows).
- Private mapper helpers (`mapProject`, `mapSubtopic`, `mapSource`, `mapWorkerActivity`, `mapChatMessage`, `mapReport`) translate snake_case DB columns → camelCase domain types and wrap `timestamptz` strings as `Date`.
- `getSources` uses `select("*, source_subtopics(subtopic_id)")` to resolve the many-to-many subtopic join into `subtopicIds[]`.
- On Supabase error, functions throw (page error boundary handles it); empty results return `[]`/`null` so existing empty-states render.
- Added `"server-only"` import guard.

**`web/src/lib/data/fixtures.ts` — deleted.** Confirmed no remaining imports.

**New create-project flow:**
- `web/src/app/(app)/project/actions.ts` — `"use server"` `createProject(formData)` Server Action: gets user via `supabase.auth.getUser()`, inserts into `projects` with `owner_id`, `research_question`, `source_tier_settings`, `status: "draft"`, then `redirect(/project/${id}/plan)`. Error shape mirrors `@/app/(auth)/actions.ts`.
- `web/src/app/(app)/project/new/page.tsx` — server component that renders `NewProjectForm` inside a centered `PageContainer` layout.
- `web/src/components/features/project/NewProjectForm.tsx` — `"use client"` form using `useActionState(createProject)`. Fields: research-question textarea (required), four tier checkboxes (academic/government default-checked), optional recency-months input, submit button with pending state.

**Chat — `web/src/components/features/chat/ChatTab.tsx`:**
- Removed mock assistant-message generation (`handleSend` / `setMessages` / `useState` for input).
- Composer input and Send button are now permanently disabled with `cursor-not-allowed` styling.
- Callout added: "AI-powered chat … becomes available once the RAG backend is connected (Phase 9)."
- Real `initialMessages` from Supabase still render if present.

**Report — `web/src/components/features/report/ReportTab.tsx`:**
- Removed mock `handleGenerate` and `autoDraft` state.
- "Generate report" button is permanently disabled.
- Callout added: "Report generation arrives in Phase 10 when the coordinator agent is connected."
- Source-selection checkboxes and "Download .md" (for real `existingReport`) remain functional.

**TypeScript:** `npx tsc --noEmit` passes with zero errors.

---

## 2026-06-01 — Diagnostics: DB connection address-family logging (IPv6 "Network is unreachable")

Render deploy crashed with `OSError: [Errno 101] Network is unreachable` at the TCP `sock.connect()` stage — a *different* failure from the earlier `_encode_db_url` parsing bugs (the URL now parses fine; the socket connect itself fails). Root cause is the Supabase IPv6 issue: the **direct** connection host `db.<ref>.supabase.co` resolves to **IPv6 only**, and Render has no IPv6 egress. Fix is to use the **Supabase Session pooler** URL (`aws-N-<region>.pooler.supabase.com`, user `postgres.<ref>`, port 5432), which is IPv4-proxied for free.

Verified against the real Render DSN that `_encode_db_url()` correctly percent-encodes the password `,b6?%hT@C6,&wEs` → `%2Cb6%3F%25hT%40C6%2C%26wEs` and round-trips to the exact original. The pooler host + encoded password produce a valid DSN, so the live env var is correct; the failure log seen during debugging was a stale crash (identical nanosecond timestamp). Action: redeploy with **Clear build cache** so a fresh run picks up the pooler URL.

Added startup diagnostics to `worker/worker/db.py`:
- `_describe_target()` parses **host/port from the DSN without ever touching the password** (`urllib.parse.urlsplit`).
- `_log_dns()` resolves the host and logs which address families it offers (`IPv4`, `IPv6`, or both); if **IPv6 only**, logs an explicit error naming the pooler fix.
- `get_pool()` now logs `DB host <host>:<port> resolves to: …` before connecting and `DB pool ready (host:port)` after.
- Defensive: port `6543` (transaction-mode pooler) → `statement_cache_size=0` (asyncpg prepared statements are incompatible with transaction pooling). Session mode (5432) / direct unaffected.

---

## 2026-05-31 — Phase 3: Search Infrastructure

Built the full Phase 3 search package (`worker/worker/search/`) — deterministic plumbing consumed by the Phase 6 worker pipeline. No LLM calls, no DB dependency; all tests are mocked (respx) and run without real network or API keys.

### What was built

**Package structure (`worker/worker/search/`):**
- `models.py` — Pydantic models: `SearchResult`, `ExtractedContent`, `SearchFailure`, `SearchResponse`, `Tier` literal
- `errors.py` — Exception hierarchy: `SearchError`, `ProviderUnavailable`, `ExtractionFailed`, `ConfigError`
- `config.py` — Frozen `SearchConfig` dataclass; `from_env()` reads `config.toml [search]` + env vars
- `retry.py` — `with_retry()` (tenacity exponential backoff); `make_client()` shared httpx factory
- `base.py` — ABCs: `WebSearchProvider`, `ContentExtractor`
- `web/brave.py` — `BraveProvider`: snippets only, tagged per tier
- `web/tavily.py` — `TavilyProvider`: sets `raw_content` from `include_raw_content=true`
- `web/factory.py` — `build_web_provider(name, cfg)` — config-driven provider selection
- `academic/semantic_scholar.py` — `SemanticScholarClient`: keyless Graph API, metadata + abstract + open-access PDF
- `extraction/trafilatura_extractor.py` — sync trafilatura wrapped via `asyncio.to_thread`
- `extraction/jina_extractor.py` — async Jina Reader fallback (free tier, optional key)
- `extraction/chain.py` — `ExtractionChain`: raw_content short-circuit → trafilatura → Jina
- `router.py` — `SearchRouter`: tier fan-out with `asyncio.gather`, partial-failure collection
- `__init__.py` — public API: `build_router(cfg)`, all models/errors re-exported

**Config wiring:**
- `config.toml` — new `[search]` table (web_provider, results_per_query, timeout, retry tuning, extraction settings)
- `worker/worker/config.py` — added optional `BRAVE_SEARCH_API_KEY`, `TAVILY_API_KEY`, `JINA_API_KEY`
- `worker/pyproject.toml` — added runtime deps (`httpx>=0.27`, `trafilatura>=1.8`, `tenacity>=8.2`) + test dep (`respx>=0.21`)

**Tests (57 total, all green, no real network):**
- `tests/test_search_models.py` — contract/validation
- `tests/test_retry.py` — 500×2→200, 429 retry, 401 fast-fail, all-503 → `ProviderUnavailable`
- `tests/test_web_providers.py` — Brave/Tavily response parsing, factory, missing-key errors
- `tests/test_academic.py` — Semantic Scholar parsing, PDF URL, fallback URL
- `tests/test_extraction.py` — raw_content short-circuit, trafilatura, Jina fallback, both-fail
- `tests/test_search_router.py` — tier routing, de-duplication, single web call (v1)
- `tests/test_degradation.py` — partial failures, all-down → `SearchError`

### Key decisions (see decisions.md)
- Brave + Tavily behind one `WebSearchProvider` interface; `config.toml` selects active provider (default Brave)
- Provider-aware extraction: raw_content present and long enough → skip trafilatura/Jina entirely
- Tenacity retry + trafilatura→Jina fallback; no auto Brave↔Tavily failover in v1

---

## 2026-06-01 — Fix: `_encode_db_url` sliced passwords containing `?`

The first version of `_encode_db_url()` still crashed Render with `ValueError: bad query field: '%hT@C6,'`. Root cause: it ran `rest.partition("?")` to strip the query string *before* locating the password. Because the Supabase password itself contains a `?`, that split cut the password in half — the trailing half (`…%hT@C6,…@host`) landed in the "query string" bucket, then `rfind("@")` on the truncated front half found no separator and the function bailed out returning the **raw, unencoded** URL. asyncpg then parsed everything after the password's `?` as URL query params and rejected it.

Fix (`worker/worker/config.py`): find the userinfo/host boundary (the **last** `@`) first, then percent-encode the entire password — including any `?` it contains. A genuine `?sslmode=require` query string lives in the host part (after the last `@`) and is left untouched. Verified with three cases: password containing `?%@,`; a plain password; and a password with `?`/`@` alongside a real host query string. No change to Render env vars.

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
