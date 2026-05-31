# Phase 1 — Infrastructure & Auth (Supabase-native)

## Context

Phase 0 (the navigable Next.js 16 shell on mocked fixtures) is complete and verified. Phase 1 is
the durable foundation everything rests on: the Supabase schema (incl. the `jobs` queue and
`worker_activity`), RLS for project isolation, real Supabase auth wired into the shell, and the
**database-backed job-queue worker** (`FOR UPDATE SKIP LOCKED` + asyncio, heartbeats, self-healing
watchdog). The queue machinery is foundational — the whole two-plane durability guarantee depends
on it — so it is built and tested now even though real agent logic arrives in Phase 6.

**Architecture decision (this revision):** the project is **Supabase-native — no FastAPI.** Its
only roles would have been auth, CRUD, and job-enqueue (a thin Postgres shim); it never
orchestrated agents. The **Python worker** is the agent orchestrator and remains. So: the web
(Next.js) reads via the `@supabase/ssr` server client (RLS-enforced) and writes via **Server
Actions**; the **worker** is the only backend service; job enqueue is a row INSERT / `SECURITY
DEFINER` RPC. RLS is the single isolation layer. (Recorded in `decisions.md`.)

**Confirmed with the user:** full Phase 1 scope; build for Supabase via the Supabase CLI; document
every key/URL in `.env.example`; the user fills `.env`/`.env.local` and provisions Supabase in
parallel, so everything is *written* now and live auth e2e + cloud `db push` + Render deploy happen
once credentials are supplied.

**Hard constraint (Next.js 16, verified against `web/node_modules/next/dist/docs/`):**
- Middleware is **`proxy.ts`** (not `middleware.ts`), runs on the Node runtime, for *optimistic*
  session refresh/redirects only — not authorization.
- **`cookies()` is async** (`await cookies()`); `.set`/`.delete` only in Server Actions / Route
  Handlers.
- Auth via **Server Actions** + `useActionState` + `redirect()` from `next/navigation`.

---

## Build order (backend/DB first, then wire the frontend — per CLAUDE.md)

### 1. Supabase schema + migrations → `supabase/migrations/`

Use the Supabase CLI (`supabase init`, `supabase start`, ship via `supabase db push`).
Numeric-prefixed migrations:

- `0001_extensions.sql` — `vector` (pgvector) + `pgcrypto`.
- `0002_core_tables.sql` — enums mirroring `web/src/lib/data/types.ts` **exactly**
  (`project_status`, `source_tier`, `subtopic_status`, `chat_role`) + tables: `projects`,
  `subtopics`, `sources` (unique `(project_id, url)`), `source_subtopics`, `source_chunks`
  (`embedding vector(1536)`; defer the ivfflat/hnsw index to Phase 4), `chat_messages`, `reports`.
  Every child table carries `project_id` (backs RLS + the "every query filters by project_id"
  invariant). Column names map to the existing TS domain types so the data layer swaps cleanly.
- `0003_jobs_and_activity.sql` — the queue substrate:
  - `jobs`: `id, project_id, type, status job_status, payload jsonb (checkpoint), attempts,
    max_attempts, last_error, heartbeat_at, claimed_by, claimed_at, created_at, updated_at`.
    Partial indexes `(created_at) where status='queued'` and `(heartbeat_at) where status='running'`.
  - `worker_activity`: PK `subtopic_id → subtopics` (one row per subtopic, upsert), `project_id`,
    `latest_activity`, `sources_stored`, `status subtopic_status`, `why_nothing_report`,
    `updated_at`.
- `0004_sharing.sql` — `project_role('viewer'|'collaborator')` + `project_members`. Groundwork for
  Phase 11; no invite UX now.
- `0005_rls_policies.sql` — `enable row level security` on all app tables. A
  `can_access_project(p_project_id)` SECURITY DEFINER STABLE helper (owner OR `project_members`)
  drives SELECT policies; writes gate on owner/`collaborator` (viewers read-only).
- `0006_rpc.sql` — queue RPCs (SECURITY DEFINER): `claim_job(p_worker_id)` (the canonical
  SKIP-LOCKED claim, wrapped to mark `running`, `attempts+1`, set claim fields, return the row);
  `heartbeat_job(p_id, p_payload default null)` (bump `heartbeat_at`, optional checkpoint, **return
  current status** so a worker observes a flip to `cancelled`); `reclaim_stale_jobs(p_timeout_seconds)`
  (stale `running` → `queued`, or `failed` at `max_attempts`); `complete_job` / `fail_job` /
  `cancel_project_jobs(p_project_id)`.

Pre-declare a Realtime publication on `projects, subtopics, sources, source_subtopics, jobs,
worker_activity` (consumed in Phase 7).

**Security model:** the browser (anon/auth key) and Next.js server (user-session server client) are
RLS-enforced; the worker's direct asyncpg connection **bypasses RLS by design** (trusted server). A
server-only service-role client exists for the rare privileged Server Action, but `SECURITY DEFINER`
RPCs are preferred so the service-role key is seldom needed.

### 2. Worker scaffold → `worker/`

`worker/worker/{config,logging,db,queue,loop,main}.py`, `handlers/{__init__,echo}.py`, run via
`python -m worker.main`.

- `db.py` — `asyncpg` pool to the Supabase **direct connection string** (`SUPABASE_DB_URL`).
- Loop: `worker_id` = host+uuid; `asyncio.Semaphore(WORKER_CONCURRENCY)` bounds in-flight jobs.
  While capacity: `claim_job` → spawn an `asyncio.Task`, keep filling to cap; else
  `await asyncio.sleep(POLL_INTERVAL)`.
- `process_job`: dispatch via a `HANDLERS[type]` registry (Phase 1 registers only `echo`). A
  heartbeat task calls `heartbeat_job` every `HEARTBEAT_INTERVAL` (< stale timeout), setting a
  `cancel_event` when the returned status is `cancelled`. Handler gets a context with
  `checkpoint(payload)` + `is_cancelled()`. Success → `complete_job`; exception → `fail_job` (reset
  to `queued` if retriable and under `max_attempts`).
- Watchdog: a separate coroutine calling `reclaim_stale_jobs(STALE_TIMEOUT_SECONDS)` every
  `WATCHDOG_INTERVAL` (e.g. 10s heartbeat / 60s stale).
- Graceful shutdown: SIGTERM/SIGINT → stop claiming, drain in-flight within a grace window;
  overflow recovered by the next worker's watchdog reclaim.
- `handlers/echo.py` — trivial proof: reads `payload.message`, runs a few `ctx.checkpoint()` steps
  with small sleeps (so heartbeats fire and cancellation is observable mid-run), echoes the message
  into `payload`, completes. No LLM / external calls.

### 3. Wire real auth into the Next.js 16 shell → `web/`

Add deps: `@supabase/ssr` + `@supabase/supabase-js` (not yet in `web/package.json` — flag the
`npm install` as a state change).

**Create:**
- `web/src/lib/supabase/client.ts` — `createBrowserClient` (Client Components).
- `web/src/lib/supabase/server.ts` — `createServerClient` bound to async `cookies()` (getAll/setAll
  adapter), `"server-only"`.
- `web/src/lib/supabase/admin.ts` — server-only **service-role** client (`SUPABASE_SERVICE_ROLE_KEY`)
  for the rare privileged Server Action.
- `web/src/lib/supabase/proxy-session.ts` — request-bound client calling `auth.getUser()` and
  writing refreshed cookies onto the same `NextResponse` (must return *that* response).
- `web/proxy.ts` — `proxy(request)`: refresh session → if under the `(app)` group and no user →
  redirect `/login`; if logged-in on `/login`|`/signup` → redirect `/dashboard`. `config.matcher`
  excludes static assets.
- `web/src/app/(auth)/actions.ts` — `"use server"` `login` / `signup` / `signOut` calling
  `auth.signInWithPassword` / `signUp` / `signOut`; return `{error}` for `useActionState`,
  `redirect()` on success.
- `web/src/lib/data/dal.ts` — `getCurrentUser()` (server client + React `cache()`).

**Modify:**
- `LoginForm.tsx` / `SignupForm.tsx` — replace the mocked `router.push("/dashboard")` with
  `<form action={action}>` + `useActionState`, surfacing `state.error`. Keep existing
  `Input`/token styling per DESIGN.md.
- `TopNav.tsx` — make session-aware: a server wrapper reads `getCurrentUser()` and passes `user` +
  the `signOut` action into the existing client nav shell (signed-out CTA vs. signed-in cluster
  with email + Sign out).

**Unchanged in Phase 1:** `types.ts` (reused verbatim) and `client.ts` (stays mocked — its project
reads swap to real Supabase reads in **Phase 2**).

### 4. Shared contracts → `shared/schemas/job_payloads.py`

Pydantic models for job payloads, consumed by the **worker** (dequeue) and mirrored/validated on
the TS enqueue path; the worker re-validates defensively on claim. (Satisfies the PRD's "contract
tests for job `payload` schemas.")

### 5. Render deployment config → `render.yaml` + `.env.example`

**Two** services: `web` (Web Service, root `web/`, `npm ci && npm run build` / `npm run start`) and
`worker` (Background Worker, root `worker/`, `python -m worker.main`). **No `api` service.** Secrets
via Render env groups; deploy is the user's action. `.env.example` documents every var (below).

---

## Tests (pytest + pytest-asyncio) — Supabase CLI local stack (`supabase start`, migrations applied)

**Queue** (`worker/tests/`) — integration, real Postgres (SKIP LOCKED can't be mocked):
- Claim under contention: all ids distinct, none double-claimed, exactly `min(N,M)` succeed.
- Claim marks `running`, `attempts=1`, sets claim fields.
- Heartbeat advances `heartbeat_at`, persists checkpoint, returns status.
- Stale reclaim → `queued` (or `failed` at `max_attempts`).
- Idempotent resume: claim → checkpoint → simulated crash → reclaim → re-claim → echo resumes.
- Cancellation: run echo with checkpoints, concurrently `cancel_project_jobs` → handler observes via
  heartbeat status, exits cleanly, row stays `cancelled`, simulated stored rows untouched.

**Contract** — echo payload + `worker_activity` row shape validate against `shared/schemas`.

**Auth** — verified via the **web e2e path** (Supabase) in Verification step 4 (no FastAPI test).

---

## Env vars (`.env.example`; user fills `.env` / `web/.env.local`)

| Var | Service | Notes |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | web | public |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | web | public |
| `SUPABASE_URL` | web (server) | |
| `SUPABASE_SERVICE_ROLE_KEY` | web (server) | **server-only**, never in the browser |
| `SUPABASE_DB_URL` | worker | **new** — direct Postgres connection (asyncpg) |
| `WORKER_CONCURRENCY`, `HEARTBEAT_INTERVAL`, `WATCHDOG_INTERVAL`, `STALE_TIMEOUT_SECONDS`, `POLL_INTERVAL` | worker | tunable constants (no hard-coding) |

*(Removed vs. the prior FastAPI plan: `SUPABASE_JWT_SECRET` — no JWT verifier; `CORS_ALLOW_ORIGINS`
— no API service.)*

---

## Verification (end-to-end)

1. `supabase start`, apply migrations → confirm tables/RPCs exist (`supabase db diff` clean).
2. `pytest` in `worker/` → queue + contract suites green. The contention test is the key SKIP-LOCKED
   proof.
3. Manually enqueue an `echo` job row → `python -m worker.main` → observe claim, heartbeats, `done`
   status, echoed payload. Kill mid-run → watchdog reclaims → resumes from checkpoint. Insert a
   cancel → job ends `cancelled` cleanly.
4. Once the user supplies creds + `web/.env.local`: `npm run dev` → sign up / log in → redirected to
   `/dashboard`; visiting `(app)` routes while logged out redirects to `/login`; TopNav shows the
   signed-in cluster; sign out works. `npm run build` clean.

---

## Doc updates on completion (per CLAUDE.md)

- `context/log.md` — Phase 1 entry (newest first), incl. the eliminate-FastAPI note.
- `context/map.md` — add `supabase/`, `worker/`, `shared/`, and the new `web/` files.
- `context/decisions.md` — record: **eliminate FastAPI / Supabase-native**; browser/Next-RLS vs
  worker-bypass split; claim wrapped in `claim_job` RPC; in-process watchdog (pg_cron noted future);
  graceful-shutdown drain + reclaim; **Next.js 16 auth via `proxy.ts` + `@supabase/ssr` + Server
  Actions + async `cookies()`**.
- `context/PRD.md` — Tech Stack edit: remove the FastAPI Web Service; Backend = Next.js Server
  Actions + Supabase; Worker is the only Python service. *(Flagged PRD change.)*
- `context/deferredwork.md` — add `SUPABASE_DB_URL`; note `SUPABASE_SERVICE_ROLE_KEY` is now used
  server-side by Next.js; enable the Realtime publication (Phase 7); Render service creation (web +
  worker); `npm install @supabase/ssr @supabase/supabase-js`. **Alert the user.**
