# Build Log

Newest-first. One entry per milestone or significant bug fix.

---

## Tuning: lower worker concurrency 5 → 3 (2026-06-06)

A research project crashed on Render (free plan, limited RAM) from too many jobs running at once. Lowered `[worker] concurrency` in `config.toml` from `5` to `3` to reduce peak concurrent memory. The value flows through `worker/worker/config.py` (`WORKER_CONCURRENCY`) into the `asyncio.Semaphore` in `worker/worker/loop.py`, which hard-caps simultaneously-running handlers. Config-only change; no code edits. Takes effect on next worker restart/deploy.

---

## Phase 9 — RAG Chat (2026-06-02)

Live chat tab: user asks a question → worker embeds it, hybrid-searches the project corpus, synthesizes a cited answer, and delivers it via Realtime. Low-confidence replies surface a "Research this →" button that spawns a new `research_subtopic` job.

**Backend:**
- Migration `0013_chat_realtime.sql` — adds `chat_messages` to `supabase_realtime` publication + adds nullable `confidence text` column (set to `'high'|'medium'|'low'` on assistant rows by the worker).
- `worker/worker/llm/schemas.py` — added `ChatAnswer` Pydantic model (`answer_markdown`, `cited_source_ids`, `confidence`).
- `shared/schemas/job_payloads.py` — added `ChatRespondPayload` (`project_id`, `question`) + registered `"chat_respond"` in `JOB_PAYLOAD_MODELS`.
- `config.toml [chat]` — added `chat_match_count = 12` (chunks retrieved) and `chat_chunk_chars = 1500` (per-chunk truncation). No hard-coding.
- `worker/worker/config.py` — reads `[chat]` section, exports `CHAT_MATCH_COUNT` and `CHAT_CHUNK_CHARS`.
- `worker/worker/handlers/chat.py` (new) — `chat_respond` handler: embeds question via `Embedder`, calls `match_chunks()` (hybrid RRF search), handles empty-corpus path (low-confidence reply, no LLM call), loads parent source rows scoped to `project_id`, builds synthesis prompt with numbered source blocks + JSON schema hint (DeepSeek `json_mode` requirement), invokes `ChatAnswer` via `invoke_structured`, validates `cited_source_ids ⊆ provided set` (drops hallucinated IDs), builds camelCase `citations` list (`sourceId/sourceTitle/url` — matches TS `Citation` type), INSERTs assistant `chat_messages` row with `confidence` column. Pre- and post-LLM cancellation guards follow `report.py` pattern.
- `worker/worker/handlers/__init__.py` — registered `"chat_respond": chat_handle`.
- `worker/tests/test_chat.py` (new) — 6 mocked tests: camelCase citations contract, hallucinated ID drop, empty corpus no-LLM path, project isolation, pre-LLM cancellation, post-LLM cancellation. All pass.
- `worker/tests/test_contract.py` — 5 new `ChatRespondPayload` round-trip tests. All 38 contract tests pass.

**Frontend:**
- `web/src/lib/data/types.ts` — added optional `confidence?: "high"|"medium"|"low"` field to `ChatMessage`.
- `web/src/lib/data/client.ts` — `mapChatMessage` threads `row.confidence` through to the domain type.
- `web/src/app/(app)/project/[id]/chat/actions.ts` (new) — two `"use server"` actions: `sendChatMessage` (inserts user `chat_messages` row + `chat_respond` job); `spawnResearchFromChat` (inserts subtopic with `wave=99` sentinel + `research_subtopic` job).
- `web/src/components/features/realtime/ChatRealtime.tsx` (new) — Supabase Realtime subscription on `chat_messages` INSERT scoped to `project_id`; calls `router.refresh()`. Mirrors `ReportRealtime.tsx`.
- `web/src/components/features/chat/ChatTab.tsx` — "Chat coming soon" `Callout` and disabled composer removed; real composer wired (`useTransition`, controlled input, `sendChatMessage` on submit); "Thinking…" affordance while a `chat_respond` job is in flight (last message is from user OR `isPending`).
- `web/src/components/features/chat/ChatMessage.tsx` — now a `"use client"` component; `projectId` prop added; low-confidence assistant messages render a "Research this →" button that calls `spawnResearchFromChat`.
- `web/src/app/(app)/project/[id]/chat/page.tsx` — mounts `<ChatRealtime>` alongside `<ChatTab>` (mirrors `report/page.tsx`).

**Coordinator barrier safety (verified):** `enqueue_ready_coordinator_reviews()` (migration 0011) guards on `p.status = 'researching'` — complete projects are immune. Chat-spawned subtopics also use `wave=99` (outside the two-wave cap) as belt-and-suspenders.

---

## Bug #3: LangSmith tracing 403 — configurable endpoint + active auth probe (2026-06-02)

**Root cause (confirmed from Render logs):** every trace upload returned `403 Forbidden` from `api.smith.langchain.com/runs/multipart`. Tracing was active and the key was loaded, but the key was revoked/rotated or belongs to a different workspace. The startup check only tested `bool(key)` and logged "ACTIVE" even when the key was rejected; the langsmith tracer downgraded the 403 to a buried per-job `WARNING`.

**Code fixes:**
- `config.toml [observability]` — added `langchain_endpoint` knob (default: US endpoint). An `LANGCHAIN_ENDPOINT` env var still overrides, so EU accounts can fix a region mismatch with a single Render env change and no config edit.
- `worker/worker/config.py` — reads `langchain_endpoint` from config; uses it in `setdefault("LANGCHAIN_ENDPOINT", …)` and `setdefault("LANGSMITH_ENDPOINT", …)` (replaces hardcode). Exports `LANGCHAIN_ENDPOINT`.
- `worker/worker/observability.py` (new) — `check_langsmith()`: if inactive, logs a `WARNING` with setup hint; if active, instantiates `langsmith.Client()` and calls `create_project` (idempotent — catches 409 conflict) to verify auth. On 403/401 logs an `ERROR` naming the three causes (revoked key, wrong workspace, EU/US region mismatch). `flush_traces()`: wraps `wait_for_all_tracers()` for clean shutdown.
- `worker/worker/main.py` — startup ACTIVE/INACTIVE block replaced with `check_langsmith()`; `finally` block adds `await loop.run_in_executor(None, flush_traces)`.
- `.env.example` — added commented `LANGCHAIN_ENDPOINT` line for EU accounts.

**User action required:** rotate/replace `LANGCHAIN_API_KEY` in Render env — see `deferredwork.md`.

---

## Bug: DeepSeek json_mode "json" keyword + error visibility (2026-06-02)

**Root cause:** DeepSeek's API requires the word "json" to appear somewhere in the prompt when using `response_format=json_object`. LangChain's `json_mode` path sets that API parameter but does NOT inject the word into raw message lists — it trusts the caller's prompt to contain it. The research handler's prompts already included explicit "Respond with a JSON object matching the X schema" lines; the report and coordinator handlers did not.

**Fixes:**
- `worker/worker/handlers/report.py` — `_build_auto_select_messages` and `_build_synthesis_messages` now include explicit JSON schema hints in the system message.
- `worker/worker/handlers/coordinator.py` — `_build_messages` now includes the CoverageReview JSON schema hint.
- `worker/worker/llm/factory.py` — added `_ensure_json_keyword()` safety-net: in the json_mode fallback path it checks for "json" in the messages and injects a schema description if absent, protecting all future handlers.
- `worker/worker/loop.py` — error storage increased from 2000 → 8000 chars; log now emits the full traceback so the actual exception is visible in both Render logs and Supabase.

---

## Bug: Error truncation fix (2026-06-01)
`worker/worker/loop.py` — increased `last_error` storage from 2000 → 8000 chars and switched the error log from single-line to full traceback so the actual exception message is visible in Supabase and Render logs when a job fails.

---

## Phase 10 — Reports (2026-06-01)

Full report-generation pipeline. Both **curated** and **auto-draft** modes ship. Backend-first per CLAUDE.md.

**Backend:**
- Migration `0012_report_realtime.sql` — adds `reports` to `supabase_realtime` publication so INSERT events reach the open tab.
- `shared/schemas/job_payloads.py` — `GenerateReportPayload` (`mode: Literal["curated","auto"]`, `source_ids`, `instructions`) added + registered in `JOB_PAYLOAD_MODELS`.
- `worker/worker/llm/schemas.py` — `AutoDraftSelection` (LLM picks top ≤25 source IDs) + `ReportDraft` (markdown + `source_ids_used`) added.
- `config.toml [report]` — `report_source_cap = 25`, `report_source_chars = 4000` tunable in config; no code deploy needed to adjust.
- `worker/worker/config.py` — reads `[report]` section, exports `REPORT_SOURCE_CAP` + `REPORT_SOURCE_CHARS`.
- `worker/worker/handlers/report.py` — `generate_report` handler: loads project, selects sources (server-side cap enforced on both modes), loads full rows with truncated full_text, invokes `ReportDraft`, validates `source_ids_used ⊆ provided set` (drops hallucinated IDs with a warning), inserts `reports` row. Realtime delivers it to the open tab. No project-status change.
- `worker/worker/handlers/__init__.py` — registered `generate_report`.
- `worker/tests/test_report.py` — 7 new mocked tests: server-side cap (curated + auto), hallucinated ID drop, source_refs correctness, project isolation, pre/post-LLM cancellation. All pass.
- `worker/tests/test_contract.py` — 7 new `GenerateReportPayload` round-trip tests. All 27 contract tests pass.

**Frontend:**
- `web/src/app/(app)/project/[id]/report/actions.ts` — `generateReport` Server Action: auth check, inserts `generate_report` job, `revalidatePath`.
- `web/src/components/features/realtime/ReportRealtime.tsx` — `"use client"` Supabase Realtime subscription on `reports` INSERT for this project; calls `router.refresh()`.
- `web/src/app/(app)/project/[id]/report/page.tsx` — mounts `<ReportRealtime>` alongside `<ReportTab>`.
- `web/src/components/features/report/ReportTab.tsx` — Generate report (curated, ≥1 required), Auto-draft (LLM selects), optional instructions textarea, "Generating…" pending state, cleared when new report arrives via Realtime. Two "Phase 10" warning Callouts removed.

## Feature: "Select all" sources for report (2026-06-01)
Bug-corrections #2. Added a `Select all` / `Deselect all` toggle (Button `text` variant, `sm`) to the Report tab source selector header (`report/ReportTab.tsx`). "Select all" caps at `SOURCE_CAP` (25) — selecting the first 25 when more sources exist; the button flips to "Deselect all" once every selectable slot is filled. Reuses the existing `selectedIds` Set + cap logic; `SourceSelector.tsx` unchanged.

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
