# Decisions Log

This file tracks architectural decisions and any deviations from the original PRD vision. Newest first.

---

## 2026-06-01 — Semantic layout-width tokens to resolve the Tailwind v4 spacing/container collision

**Decision:** Keep DESIGN.md's named spacing scale (`--spacing-xxs … --spacing-section`) exactly as-is, and introduce a separate set of **semantic layout-width tokens** in `globals.css @theme` for `max-w-*`: `--container-card` (28rem), `--container-panel` (24rem), `--container-content` (75rem / ~1200px). Components use `max-w-card` / `max-w-panel` / `max-w-content`; the bare Tailwind t-shirt width utilities (`max-w-md`, `max-w-sm`, …) are **not** used for layout.

**Why:** In Tailwind v4, a custom `--spacing-md` token shadows the built-in `--container-md`, so `max-w-md` compiled to `var(--spacing-md)` = 16px (and `max-w-sm` = 12px). That was the true cause of bug #1 (login card collapsed to a thin column) and also broke the dashboard/chat empty states and the mobile nav drawer. The two scales genuinely share the `sm/md/lg/xl` keyspace, so you cannot have both `--spacing-md` (for `p-md`) and `max-w-md` = 28rem — one key has one meaning. Rather than drop the DESIGN.md-faithful spacing tokens, we move layout widths onto a non-colliding, semantically-named namespace. Bonus: `--container-content` now encodes DESIGN.md's "~1200px centered" rule as a real token instead of a hard-coded `max-w-[1200px]` repeated across `PageContainer` and `ProjectShellHeader`.

**Trade-off / convention:** The bare `max-w-{sm,md,lg,xl}` utilities remain shadowed (still resolve to the small spacing values). This is unavoidable while the named spacing scale exists. Convention: always use `max-w-card/panel/content` for layout widths; a comment in `globals.css` documents this. DESIGN.md is unchanged.

## 2026-05-31 — Phase 4+5 architectural decisions

**Decision 1 — `ChatOpenAI` + DeepSeek `base_url` over `langchain-deepseek` package.**
Use `langchain_openai.ChatOpenAI` with `base_url="https://api.deepseek.com/v1"` and `api_key=DEEPSEEK_API_KEY`. This is the PRD-mandated model-agnostic OpenAI-compatible interface: changing the provider = changing config.toml + env vars, zero code change. The `langchain-deepseek` package is a thin wrapper that adds a dependency without enabling anything that the OpenAI-compatible interface doesn't already provide.

**Decision 2 — Hybrid search as a SQL `match_chunks` function with Reciprocal Rank Fusion.**
The vector CTE (cosine similarity via pgvector) and keyword CTE (FTS via `ts_rank`/`plainto_tsquery`) are full-outer-joined and their ranks fused with RRF (`1/(60+rank)`) in a single `language sql stable` function. Lives as a migration so the Phase 6 worker pipeline and the Phase 9 RAG chatbot share one canonical implementation with no drift risk. Not `SECURITY DEFINER` — the worker bypasses RLS; an authenticated wrapper is deferred to Phase 9.

**Decision 3 — pgvector via `$N::vector` string-cast, no codec registration.**
Vectors are inserted as PostgreSQL text literals (`[1.0, 2.0, ...]`) and cast with `$N::vector` in the SQL statement. asyncpg passes the string as `text` and PostgreSQL handles the cast. This avoids the asyncpg codec registration ceremony and works correctly with `executemany`.

**Decision 4 — Planner runs as a worker job; web sets `planning`; subtopic presence signals ready.**
`createProject` and `regeneratePlan` Server Actions set `project.status = "planning"` and enqueue a `generate_plan` job. The worker never mutates `project.status` — the presence of subtopics is the signal that the plan is ready for review. This keeps responsibilities cleanly separated: web owns status transitions triggered by user actions; worker owns data writes.

**Decision 5 — Realtime pulled forward into Phase 5 (was Phase 7).**
The Plan tab needs live subtopic updates when the planner worker finishes. Adding `ProjectRealtime.tsx` now (subscribed to `subtopics` + `projects` changes, calls `router.refresh()`) avoids building interim polling and uses the architecture already committed to. The component lives in the project layout so it stays mounted across tab switches — exactly the Phase 7 seam, just activated early.

---

## 2026-05-31 — Remove Phase 0 mock seam; wire real Supabase reads + create-project flow ahead of schedule

**Decision:** Delete `fixtures.ts` and rewrite all seven `client.ts` functions to query live Supabase ahead of the originally scheduled phases (Phases 2/5/6/7/9/10). The create-project flow (`/project/new` page + `createProject` Server Action) was also built now to give the app a real data-entry point. Chat composer and Report generation are disabled in the UI with informational callouts until their backends land (Phase 9 RAG, Phase 10 coordinator).

**Why:** The Supabase schema, RLS policies, and auth are all live from Phase 1. Running the app against fixtures while the real DB exists served no purpose and actively obscured whether the data layer worked. Building the create-project flow now was required — without it, deleting fixtures would leave the app unactionable (empty state with no way to add data).

**Consequences:**
- The dashboard and all project tabs now render live data scoped to the signed-in user via RLS.
- `fixtures.ts` is permanently deleted; `client.ts` is now the Supabase query layer.
- Chat and Report generation show "coming soon" callouts instead of mock content — no fake data is ever produced.
- The `/project/new` 404 is fixed; the flow inserts a real row and redirects to the new project's Plan tab.

---

## 2026-05-31 — Phase 3 search infrastructure decisions

**Decision 1 — Swappable web provider (default Brave).**
Implement Brave + Tavily behind a single `WebSearchProvider` ABC. `config.toml [search] web_provider` selects the active one; callers never reference a specific provider. `build_web_provider(name, cfg)` in `web/factory.py` is the only place the name is resolved. This means the active provider can be changed with a config edit, no code change required.

**Decision 2 — Provider-aware extraction (raw_content short-circuit).**
When a `SearchResult.raw_content` is present and its word count meets `extraction_min_words`, `ExtractionChain` returns `ExtractedContent(extractor="provider")` immediately — no network call. Only when raw content is absent or too short does the chain fall through to trafilatura → Jina. This is Tavily-specific behavior today but is transparent to the router.

**Decision 3 — Tenacity retry + trafilatura→Jina fallback; no auto provider-switch in v1.**
`with_retry()` in `retry.py` uses tenacity `AsyncRetrying` for exponential-backoff on transient HTTP errors (TransportError + 429/5xx). 4xx (excluding 429) fail fast without retry. On exhaustion, `ProviderUnavailable` is raised. A `web_fallback_provider` config key exists in `config.toml` but is disabled (`""`) in v1 — automatic Brave↔Tavily failover is deferred.

**Why:** Keeps the retry contract simple and observable: one provider per call. Failover introduces complexity around result de-duplication and quota tracking that isn't justified at current scale.

---

## 2026-05-31 — Eliminate FastAPI; go Supabase-native

**Decision:** Drop the planned FastAPI backend entirely. The web app (Next.js) talks to Supabase directly — **reads** via the `@supabase/ssr` server client (RLS-enforced), **writes / CRUD / status-machine / job-enqueue** via Next.js **Server Actions** (RLS + `SECURITY DEFINER` RPCs). The **Python worker remains the only backend service** and is the agent orchestrator (`FOR UPDATE SKIP LOCKED` + `asyncio` + semaphore). Postgres is the single source of truth and RLS is the single isolation layer.

**Why:**
- FastAPI's only roles were auth, CRUD, and job-enqueue — a thin shim that forwards writes to Postgres. It **never orchestrated agents**; the worker does. So removing it loses no agent capability.
- Reading through the Supabase server client makes the read row shape **identical to the Phase 7 Realtime delta shape** (one mapping layer, cleanest projection-plane fit) and exercises **RLS as a real control**, not just defense-in-depth.
- One fewer service to build/deploy/monitor; no duplicate config/auth/clients across api + worker; no API client or token-forwarding in the web. Same "right-sized" ethos as choosing the DB-backed queue over Celery/Redis.
- The two-plane invariant is preserved: a Server Action inserting a job row is just as valid a *trigger* as an API call — triggering ≠ running.

**Consequences:**
- The project **status state machine** lives in Postgres (transition-guard trigger + RPCs), enforced regardless of caller; project CRUD/isolation is verified via **DB-integration tests** (Supabase local stack) rather than Python service tests.
- **RAG chat** is handled as a **job** (enqueue → worker synthesizes → writes the assistant message → Realtime pushes it back). A small synchronous Python endpoint is **deferred to Phase 9** and added only if interactive latency proves unacceptable.
- A server-only Supabase **service-role** client exists for the rare privileged Server Action, but `SECURITY DEFINER` RPCs are preferred so the service-role key is seldom needed.

**Trade-off accepted:** isolation rests entirely on RLS (no server-side second gate), so policies must be airtight and are tested as the key proof. Business logic in Postgres/Server Actions is less familiar than a Python service to some readers, but is fully testable.

**Supersedes:** the PRD's "Backend API: FastAPI" tech-stack line and the original `agent/phase-1-plan.md` FastAPI scaffold (§3), JWT verifier, `/me`, the `api` Render service, and the `SUPABASE_JWT_SECRET` / `CORS_ALLOW_ORIGINS` env vars. `agent/phase-1-plan.md` was rewritten FastAPI-free on 2026-05-31.

---

## 2026-05-31 — Next.js 16 auth: proxy.ts + @supabase/ssr + Server Actions + async cookies()

**Decision:** Auth in the Next.js 16 shell uses `proxy.ts` (renamed from `middleware.ts` in Next.js 16) for optimistic session refresh and route-level redirects only. Server Actions (`login`, `signup`, `signOut`) with `useActionState` handle mutations. `cookies()` is async in Next.js 16; `.set`/`.delete` work only in Server Actions/Route Handlers. The DAL (`dal.ts`) centralizes `getCurrentUser()` with React `cache()`.

**Why:** This is the correct Next.js 16 + Supabase SSR integration. Proxy handles refresh + optimistic redirects; real auth lives in the DAL close to the data. Using `useActionState` + `<form action={action}>` gives progressive-enhancement forms that work without JS.

---

## 2026-05-31 — In-process watchdog for stale job reclaim (pg_cron is a future option)

**Decision:** Stale-job reclaim runs as an asyncio coroutine inside the worker process (`_watchdog` in `loop.py`), not as a `pg_cron` job.

**Why:** Keeps the stack simple — no pg_cron setup required. Trade-off: if all workers are down, reclaim doesn't fire until a worker restarts. Acceptable at current scale. pg_cron is the right move when independent reclaim becomes necessary.

---

## 2026-05-31 — Claim logic wrapped in SECURITY DEFINER RPC

**Decision:** `FOR UPDATE SKIP LOCKED` claim is wrapped in `claim_job(p_worker_id)` SECURITY DEFINER function rather than raw SQL from the worker.

**Why:** Keeps canonical claim logic version-controlled in migrations (not scattered in application code), testable against the real DB, and callable from both worker and future privileged Server Actions.

---

## 2026-05-31 — Graceful shutdown: drain in-flight + watchdog reclaim overflow

**Decision:** On SIGTERM/SIGINT the worker stops claiming and waits up to `GRACE_SHUTDOWN_SECONDS` for in-flight tasks. Jobs that exceed the window are left `running`; the next worker's watchdog reclaims them from their last checkpoint.

**Why:** Simple, correct, matches Render's shutdown model. Heartbeat/checkpoint guarantees no work is lost.

---

## 2026-05-29 — Dark mode via CSS-variable remapping + next-themes

**Decision:** Implement dark mode by **remapping the design-system role tokens' CSS-variable values under a `.dark` selector**, rather than adding `dark:` utility variants across components. Toggle state is managed by `next-themes` (class strategy, `.dark` on `<html>`).

**Why:**
- Every component already styles with semantic token utilities (`bg-canvas`, `text-ink`, `border-hairline`) that Tailwind v4 compiles to `var(--color-*)`. Overriding those variables under `.dark` flips the entire app with near-zero component edits — far less surface area and risk than editing ~100 className strings.
- `next-themes` is the standard App-Router-safe solution for no-FOUC SSR, system-preference detection, and localStorage persistence. It's a tiny, focused dependency (consistent with the Phase 0 "minimal dependency surface" stance — same spirit as adopting Radix headless rather than shadcn).
- Keeps DESIGN.md as the source of truth: the dark palette is a warm-dark remap (never cool slate), preserving the brand's warm voltage in both modes.

**Token policy:** Only **role** tokens flip (canvas/surfaces/text/hairlines + a slight coral lift). The **literal always-dark** tokens (`surface-dark*`, `on-dark*`) and semantic accents (success/warning/error/teal/amber, on-primary) are intentionally NOT remapped, so the Footer, code blocks, and dark product cards stay coherent and status colors keep their meaning across both modes.

**Trade-off accepted:** In dark mode the deliberate light "cream → dark" pacing rhythm from DESIGN.md flattens (the page floor is now dark, so always-dark surfaces sit closer in value). This is inherent to any dark theme and is mitigated by keeping a distinct elevation hierarchy (canvas darkest → surface-card a step up).

---

## 2026-05-29 — Database-backed job queue instead of Celery + Redis

**Decision:** Run all agent work as a Postgres-backed job queue (`jobs` table, claimed via `FOR UPDATE SKIP LOCKED`) with `asyncio` concurrency inside a worker process. No Celery, no Redis.

**Why:**
- Agent work is entirely I/O-bound (search APIs, LLM calls, content fetches), so `asyncio` provides true concurrency in a single process — a distributed task broker is not needed for parallelism.
- Keeps the stack centered on Supabase/Postgres, which the user explicitly prefers for simplicity, and removes an entire service (Redis) and its failure modes.
- Postgres `SKIP LOCKED` gives native, safe multi-worker queue semantics; scaling out = run another worker instance, no code change.
- Durability/self-healing comes from job rows + heartbeats + a watchdog that reclaims stale `running` jobs — this is what eliminates the v1 "redeploy agents to resume" problem.

**Trade-off accepted:** We give up Celery's built-in scheduling/retry/rate-limiting niceties, re-implementing the small subset we need (retry via `attempts`, reclaim via heartbeat watchdog). At ~1 project/week scale this is a net simplification.

**Supersedes:** v1 PRD's Celery + Redis (Upstash) async-jobs design.

---

## 2026-05-29 — Two-plane architecture (execution vs. projection) to fix agent orphaning

**Decision:** Strictly separate the **execution plane** (server-only agents that run independent of the browser and write all state to Postgres) from the **projection plane** (browser is a pure read/subscribe view of DB state). The browser may *trigger* work via API but never *runs* or *holds* it.

**Why:** The v1 failure — navigating away or switching tabs orphaned in-flight agent work, requiring manual redeployment — was caused by work/progress state living in or being driven by the browser. Making the database the single source of truth for both data and in-flight work means re-mounting always reflects true state and there is nothing to orphan.

---

## 2026-05-29 — Supabase Realtime as the only UI sync mechanism

**Decision:** UI stays in sync via Supabase Realtime subscriptions to table changes (`projects`, `subtopics`, `sources`, `source_subtopics`, `jobs`, `worker_activity`). REST polling is the fallback if a subscription drops.

**Why:** Subscribing directly to the database makes "DB is the source of truth" automatic and requires no separate event stream to reconcile. **Resolves a v1 PRD contradiction** between a Supabase-Realtime design and a parallel SSE-over-Redis design — the SSE/Redis event stream is removed entirely.

---

## 2026-05-29 — Hosting committed to Render (+ managed Supabase)

**Decision:** Deploy the Next.js frontend and FastAPI API as Render Web Services, and the worker as a Render Background Worker. Supabase remains managed for database/auth/realtime.

**Why:** The worker needs a persistent (non-serverless) host; Render's Web Service + Background Worker service types map cleanly onto the three processes (web, api, worker). Replaces the v1 PRD's provider-agnostic "Vercel + VPS or equivalent" language with a concrete commitment.

---

## 2026-05-29 — Phase 0 implementation choices

**Decision:** Three implementation-level choices made during Phase 0:
1. **Repo layout:** Next.js app lives in `ytres/web/` — leaves room for `ytres/api/` and `ytres/worker/` later, matching Render's separate-services model.
2. **Components:** Hand-rolled primitives against DESIGN.md tokens + Radix headless (`@radix-ui/react-dialog` for mobile nav, `@radix-ui/react-tabs` available for future use). No shadcn/ui base — the cream/coral/serif brand fights generic library defaults.
3. **Mock depth:** Lightweight in-memory interactivity only (plan approve/regenerate toggles, chat composer append, source-selection checkboxes). Nothing persists across page loads.

**Why:** Keeps the design system faithful to DESIGN.md, minimizes dependency surface, and makes the mock→real seam as clean as possible (`client.ts` is the only thing Phases 1/2 replace).

---

## 2026-05-29 — Build order front-loads a navigable frontend shell (Phase 0)

**Decision:** Phase 0 is a navigable Next.js shell (all routes/tabs, mocked data, design system applied) before backend infrastructure, so the product is QA-able from day one. Real persistence is proven in Phase 2.

**Why:** User wants to QA navigation and look-and-feel from the start, and every later UI feature is better built into a real shell than blind.
