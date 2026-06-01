# Plan: Remove all dummy data, wire frontend to real Supabase

## Context

The ytres frontend was deliberately built in Phase 0 as a "navigable shell" rendering entirely against an in-memory mock dataset (`web/src/lib/data/fixtures.ts`), reached through a single swap-seam (`web/src/lib/data/client.ts` — 7 async functions). Phase 1 wired real Supabase auth + schema + the worker queue, but the data-access functions still return fixtures; the original schedule deferred swapping them to Phases 2–10.

Now that Supabase is the live backend, the user wants **all dummy data expunged**. The complication surfaced during exploration: simply deleting the fixtures would leave a fully empty, un-populatable app, because **there is no create-project flow** — `/project/new` is linked from the dashboard and empty state but has no `page.tsx` (clicking "New project" 404s). Per the user's direction, we will build that create flow now.

**Decisions confirmed with the user:**
- **Scope:** Wire all `client.ts` reads to real Supabase **and** build the missing create-project flow so the app works end-to-end with real, user-created data.
- **Chat & Report:** Their real backends (RAG = Phase 9, coordinator = Phase 10) don't exist. Disable those mock interactions **gracefully** (no fake content generated).
- **Worker echo handler + pytest fixtures:** **Keep** — legitimate test/POC infrastructure, not user-facing dummy data. No changes there.

Outcome: zero dummy data in the app's runtime path; every screen reads live Supabase data scoped to the signed-in user via existing owner-RLS; tables start empty and are populated by creating a project.

## Schema reference (snake_case DB → camelCase TS)

RLS is owner-scoped (`supabase/migrations/0005_rls_policies.sql`), so the authenticated anon client (via `@/lib/supabase/server`) automatically returns only the current user's rows — no manual `owner_id` filter needed. `worker_activity` is read-only to owners (worker writes via service role).

| TS type (`web/src/lib/data/types.ts`) | Table / columns |
|---|---|
| `Project` | `projects`: `research_question`→`researchQuestion`, `source_tier_settings`→`sourceTierSettings`, `owner_id`→`ownerId`, `created_at`→`createdAt`, `updated_at`→`lastUpdated` |
| `Subtopic` | `subtopics`: `project_id`→`projectId`, `information_objective`→`informationObjective`, `source_tier_preferences`→`sourceTierPreferences`, `sort_order`→`sortOrder` |
| `Source` | `sources`: `full_text`→`fullText`, `key_takeaway`→`keyTakeaway`, `score_*`→`scores.{relevance,credibility,uniqueness,actionability}`, `stored_at`→`storedAt`; `subtopicIds` from joined `source_subtopics(subtopic_id)` |
| `WorkerActivity` | `worker_activity`: `subtopic_id`→`subtopicId`, `latest_activity`→`latestActivity`, `sources_stored`→`sourcesStored`, `why_nothing_report`→`whyNothingReport` |
| `ChatMessage` | `chat_messages`: `project_id`→`projectId`, `created_at`→`createdAt` (citations is jsonb) |
| `Report` | `reports`: `source_refs`→`sourceRefs`, `generated_at`→`generatedAt` |

Note: Supabase returns `timestamptz` as ISO strings; the TS types use `Date`. Mappers must wrap date fields in `new Date(...)` (call sites like `client.ts` sorts and date formatting rely on `Date`).

## Changes

### 1. Rewrite the data seam — `web/src/lib/data/client.ts`
Replace every fixture-backed function body with a real query using `createClient()` from `@/lib/supabase/server`. Keep the exact same function signatures and return types so **no page/component call site changes**.

- Add private row→domain **mapper helpers** (one per entity) at the top of the file (avoids hardcoding/duplication, per CLAUDE.md modularity guidance). Each maps snake_case columns → camelCase and converts timestamps to `Date`.
- `getProjects()` → `.from("projects").select("*").order("updated_at", { ascending: false })`
- `getProject(id)` → `.select("*").eq("id", id).maybeSingle()` → mapper or `null`
- `getSubtopics(projectId)` → `.eq("project_id", projectId).order("sort_order")`
- `getSources(projectId)` → `.select("*, source_subtopics(subtopic_id)").eq("project_id", projectId)`; map join rows into `subtopicIds`
- `getWorkerActivity(projectId)` → `.from("worker_activity").select("*").eq("project_id", projectId)`
- `getChatMessages(projectId)` → `.eq("project_id", projectId).order("created_at")`
- `getReport(projectId)` → most-recent report: `.eq("project_id", projectId).order("generated_at", { ascending: false }).limit(1).maybeSingle()`

On Supabase errors, throw (let the page error boundary handle it); empty results return `[]`/`null` so existing empty-states render.

### 2. Delete the fixtures — `web/src/lib/data/fixtures.ts`
Delete the file. Confirm via search that nothing else imports `fixtures` (only `client.ts` does). `types.ts` stays (still the domain contract).

### 3. Build the create-project flow (NEW)
- **`web/src/app/(app)/project/actions.ts`** (new, `"use server"`): `createProject(formData)` — get user via `@/lib/supabase/server`; insert into `projects` with `owner_id = user.id`, `research_question`, `source_tier_settings` (built from the four tier toggles + recency), `status: "draft"`; `.select("id").single()`; `redirect(\`/project/${id}/plan\`)`. Mirror the error-handling shape of `web/src/app/(auth)/actions.ts`.
- **`web/src/app/(app)/project/new/page.tsx`** (new): server component rendering a client form component.
- **`web/src/components/features/project/NewProjectForm.tsx`** (new, `"use client"`): research-question textarea (required), four source-tier toggles (academic/government/news/industry), optional recency-months input, submit button. Style strictly with existing design tokens / primitives (`PageContainer`, button/input classes already used in `ChatTab`/auth forms) — reference `context/DESIGN.md` before styling. Reuse `TIER_LABELS` pattern already defined in `PlanTab.tsx`/`SourceCard.tsx`.

### 4. Disable Chat gracefully — `web/src/components/features/chat/ChatTab.tsx`
Remove the mock assistant-message generation in `handleSend` (lines 23–44, the `"*(Mock response …)*"` block). Disable the composer input + Send button and update the placeholder/Callout to indicate chat becomes available once the RAG backend is connected. Continue rendering any real `initialMessages` (will be empty for now). No fake content is ever produced.

### 5. Disable Report generation gracefully — `web/src/components/features/report/ReportTab.tsx`
Remove the `mockReport` generation in `handleGenerate` (lines 37–46). Disable the "Generate report" button with a Callout noting report generation arrives in a later phase. Keep source-selection UI and the `Download .md` button functional for any **real** `existingReport`. No fake markdown generated.

### 6. Docs (required by CLAUDE.md)
- **`context/log.md`** — log this change (dummy data removed; real Supabase reads; create-project flow added; chat/report disabled).
- **`context/deferredwork.md`** — update the "Dummy / placeholder data in use" table: mark the read surfaces as now live; record that Chat (Phase 9 RAG) and Report generation (Phase 10 coordinator) are **disabled in UI** pending backends; note project create now exists.
- **`context/decisions.md`** — record the decision to remove the Phase 0 mock seam and wire real reads + create-project ahead of the original phase schedule, and to disable chat/report generation until their backends land.
- **`context/map.md`** — `fixtures.ts` removed; `client.ts` is now real Supabase queries; add new files (`project/new/page.tsx`, `project/actions.ts`, `NewProjectForm.tsx`).

### Out of scope (unchanged)
`worker/worker/handlers/echo.py`, `worker/tests/*`, `shared/schemas/job_payloads.py` (test/POC infra — user said keep). `config.toml`, `tokens.ts`, UI label maps (config, not dummy data).

## Verification

1. **Typecheck/lint:** `cd web && npx tsc --noEmit` (and lint) — confirm the snake_case→camelCase mappers satisfy the `types.ts` contract and no `fixtures` import remains.
2. **Build:** `cd web && npm run build` — must compile with the new pages/actions.
3. **Manual end-to-end** (`npm run dev`, signed in against the live Supabase project):
   - Dashboard loads with **empty state** (no fixture projects).
   - Click **New project** → form renders (no 404) → submit → redirects to the new project's Plan tab.
   - New project now appears on the dashboard; Plan/Research/Sources tabs render real (empty) data without errors.
   - Chat tab: composer disabled with the "coming soon" message; no mock reply on attempted send.
   - Report tab: Generate disabled with the later-phase note; no mock report.
   - Confirm the row exists in Supabase (`projects` table) with correct `owner_id`.
4. **Worker tests untouched:** `cd worker && pytest` still passes (no changes to worker/tests).
