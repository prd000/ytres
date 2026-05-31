# Phase 2 — Projects Module (Supabase-native)

## Context

Phase 0 (mocked shell) and Phase 1 (Supabase-native infrastructure + auth) are both **built** as of
2026-05-31. Phase 2 is the **first real-persistence milestone**: create a project, navigate away,
come back, and find the state intact — the end-to-end proof of the two-plane (execution/projection)
model.

**Scope (PRD Phase 2):** project CRUD; `project_id` isolation at the data layer **and** via RLS; the
status state machine; and per-project source-tier settings.

**Architecture (per `decisions.md`):** reads via the Supabase **server client** (RLS-scoped); writes
via Next.js **Server Actions** (RLS + `SECURITY DEFINER` RPCs); the **status state machine lives in
Postgres** (a transition-guard trigger), so it holds for any caller.

### Resolved decisions (confirmed with the user, 2026-05-31)

1. **Delete = hard delete + confirm.** A project DELETE cascades to every child via the existing FK
   `on delete cascade`. Irreversible, owner-only. No `deleted_at`/archive (not in PRD scope). A
   confirm dialog guards it; the delete cancels in-flight jobs first.
2. **Lifecycle = re-plannable.** `cancelled → planning` and `complete → planning` are allowed so a
   cancelled or finished project can be re-planned **in place, keeping its stored sources** (PRD
   story #24). `researching` stays forward-only — cancel first to re-plan. (Full map in §1b.)
3. **Edit UX = Plan-tab inline editor.** An "Edit" affordance on the Plan tab's *Source preferences*
   card edits the research question + tier settings. No new route. Editing the question once a plan
   exists implies regeneration → wired in Phase 5; Phase 2 persists the edit and leaves regeneration
   mocked.

### Scope boundaries

- **Plan generation/regeneration is Phase 5.** `createProject` produces a `draft`; the Plan tab's
  "Approve / Regenerate" actions stay mocked.
- **Real jobs arrive in Phase 6.** `cancel_project` is wired now but has no real jobs to cancel yet.

---

## Foundation already in place (Phase 1) — what Phase 2 builds on

- **`projects`** (`0002_core_tables.sql`): `id`, `owner_id` (FK `auth.users` `on delete cascade`),
  `research_question`, `status project_status` (default `'draft'`), `source_tier_settings jsonb`
  (default `'{}'`), `created_at`, `updated_at`.
- **FK cascade:** `subtopics`, `sources`, `source_subtopics`, `source_chunks`, `chat_messages`,
  `reports`, `jobs`, `worker_activity` all `references projects(id) on delete cascade` → a project
  delete wipes the whole graph cleanly.
- **RLS (`0005_rls_policies.sql`) — already complete, no change needed:**
  - `projects_select … using (can_access_project(id))`
  - `projects_insert … with check (owner_id = auth.uid())`
  - `projects_update … using (can_write_project(id))`  *(owner or collaborator)*
  - `projects_delete … using (owner_id = auth.uid())`  *(owner only)*
  - Helpers `can_access_project(uuid)` and `can_write_project(uuid)` exist (SECURITY DEFINER STABLE).
- **`cancel_project_jobs(p_project_id uuid)`** RPC (`0006_rpc.sql`) — cancels a project's
  `queued`/`running` jobs.
- **Web:** `web/src/lib/supabase/{server,client,admin}.ts` (server = `createServerClient` bound to
  async `cookies()`), `web/src/lib/data/dal.ts` → `getCurrentUser()`.

**Gaps Phase 2 fills:** no status-transition guard; **no `updated_at` touch trigger** (columns exist,
trigger does not); no project mutation Server Actions; project reads still mocked in `client.ts`;
`/project/new` route missing; the `ProjectShellHeader` Cancel button is a no-op.

---

## Build order (DB first, then wire the frontend — per CLAUDE.md)

### 1. DB → `supabase/migrations/0007_project_lifecycle.sql`

**(a) `updated_at` touch trigger** — does not exist yet. `BEFORE UPDATE ON projects` →
`new.updated_at = now()`, so `lastUpdated` reflects edits/status changes. (Implement as a reusable
`touch_updated_at()` function so later phases can attach it to other tables.)

**(b) Status transition guard** — a `BEFORE UPDATE ON projects` trigger that fires only
`WHEN (old.status IS DISTINCT FROM new.status)` and rejects anything outside this **re-plannable**
map (raise `'invalid project status transition: % → %'`):

| From | Allowed to | Performed in |
|---|---|---|
| `draft` | `planning`, `cancelled` | planning: Phase 5 · cancel: **Phase 2** |
| `planning` | `researching`, `cancelled` | approve: Phase 6 · cancel: **Phase 2** |
| `researching` | `complete`, `cancelled` | complete: Phase 8 · cancel: **Phase 2** |
| `complete` | `planning` | re-plan/extend: Phase 5 (keeps sources) |
| `cancelled` | `planning` | re-plan: Phase 5 (keeps sources, **PRD #24**) |

- The initial `'draft'` is set on INSERT (not a transition).
- Same-status updates skip the check → Phase 5 "regenerate" (stays `planning`) is unaffected.
- **Phase 2 itself only ever drives `→ cancelled`** (plus the `draft` insert); the rest of the map is
  defined now so later phases aren't blocked.

**(c) `cancel_project(p_project_id uuid)` RPC** (`SECURITY DEFINER`): assert
`can_write_project(p_project_id)` (else raise); call `cancel_project_jobs(p_project_id)`;
`UPDATE projects SET status='cancelled' WHERE id = p_project_id AND status IN
('draft','planning','researching')`. Atomic; stored sources untouched. *(Note: this is the
access-checked wrapper around the existing `cancel_project_jobs`.)*

**(d) RLS:** unchanged — the `0005` policies above already cover every Phase 2 read/write.

### 2. Web read layer → `web/src/lib/data/client.ts` + new `web/src/lib/data/mappers.ts`

- `mappers.ts` → `rowToProject(row)`: `research_question`→`researchQuestion`, `source_tier_settings`
  jsonb→`SourceTierSettings`, `owner_id`→`ownerId`, `updated_at`→`lastUpdated` (`Date`),
  `created_at`→`createdAt` (`Date`), `status`→`ProjectStatus`. **`types.ts` stays verbatim.**
- Swap `getProjects()` / `getProject(id)` to query Supabase via `createServerClient`
  (`supabase/server.ts`); RLS scopes rows to the session user. `getProjects()` →
  `order by updated_at desc`, wrap in React `cache()`; `getProject(id)` → `Project | null`.
- Mark `client.ts` `"server-only"`. Server-Component call sites (`dashboard/page.tsx`,
  `project/[id]/layout.tsx`, tab pages) are unchanged. Other fns stay mocked until their phases.

### 3. Web mutations (Server Actions) → `web/src/lib/data/projects.actions.ts` (`"use server"`)

All use the user-session **server client** (RLS). Validation errors return `{error}` for
`useActionState`; mutations `revalidatePath` the dashboard + project routes.

- `createProject(prevState, formData)` — validate non-empty question (+ sane length); insert
  `{owner_id (= session user via getCurrentUser), research_question, status:'draft',
  source_tier_settings}`; `redirect('/project/<id>/plan')`.
- `updateProjectQuestion(id, question)` / `updateTierSettings(id, settings)` — RLS-gated UPDATEs
  (allowed by `can_write_project`). The `updated_at` trigger stamps the change.
- `cancelProject(id)` — `rpc('cancel_project', { p_project_id: id })`.
- `deleteProject(id)` — `rpc('cancel_project', …)` to stop in-flight jobs, then DELETE the row
  (RLS owner-only); FK cascade removes all children; `redirect('/dashboard')`. *(Worker tolerance
  for a vanished job row is a Phase 6 note; no real jobs exist yet.)*

### 4. Frontend wiring (reference DESIGN.md tokens/components — design tokens only, no inline hex)

- **Create** — new `web/src/app/(app)/project/new/page.tsx` → `NewProjectForm`
  (`web/src/components/features/dashboard/NewProjectForm.tsx`, `"use client"`,
  `useActionState(createProject)`). The route is **already linked** from `DashboardView` +
  `EmptyState`. Fields: research-question `Textarea`; source-tier toggle pills (reuse the `PlanTab`
  tier-pill pattern); recency select (None / 6 / 12 / 24 / 36 months); primary submit. Surface
  `state.error`; `AuthShell`-style card.
- **Edit (decision 3)** — add an "Edit" control to `PlanTab`'s *Source preferences* section
  (`PlanTab` is already `"use client"`) opening an inline editor for the question + tiers, calling
  `updateProjectQuestion` / `updateTierSettings`. In `draft`, edits apply directly. If a plan already
  exists, the question editor shows a "saving this will regenerate the plan" note (regeneration
  itself is Phase 5; Phase 2 just persists the new question).
- **Cancel** — extract `CancelProjectButton` (`"use client"`) from `ProjectShellHeader`; opens a
  confirm dialog (`@radix-ui/react-dialog`, already a dep) → `cancelProject(project.id)`. Keep the
  status-conditional render (`planning` / `researching` only).
- **Delete (decision 1)** — kebab/overflow action on `ProjectCard` (the card is a `Link`, so the
  menu button must `stopPropagation`) → confirm dialog with explicit **"permanently delete"** copy →
  `deleteProject`.
- Dashboard + project layout now render real data via the swapped `client.ts`.

### 5. Tests — DB integration against the Supabase CLI local stack (same harness/`conftest.py` as the Phase 1 queue tests)

- **RLS isolation (the key proof):** user A cannot SELECT / UPDATE / DELETE user B's project.
- **Transition guard:** assert **every allowed edge passes** (e.g. `cancelled→planning`,
  `complete→planning`, `draft→planning`, `*→cancelled`) and **representative disallowed edges raise**
  (e.g. `complete→researching`, `cancelled→draft`, `draft→complete`, `researching→planning`).
- **`cancel_project`:** `can_write_project` enforced; sets `cancelled`; cancels the project's
  `queued`/`running` jobs (seed a few); **stored `sources` preserved**.
- **Delete cascade + ownership:** deleting a project removes its subtopics/sources/jobs/etc.;
  non-owner delete is denied by RLS.
- **`updated_at` touch:** an UPDATE bumps `updated_at`.
- **CRUD happy paths:** INSERT honors `owner_id` WITH CHECK; tier-settings round-trip.
- *(Optional)* lightweight TS unit tests for Server Action input validation.

---

## Verification (end-to-end)

1. `supabase start` + migrations (incl. `0007`) applied; `supabase db diff` clean.
2. DB integration suite green — **RLS isolation** + **transition guard** are the critical proofs.
3. With creds + `web/.env.local`: `npm run dev` → sign in →
   - **New project** → submit question + tiers → lands on `/project/<id>/plan` as `draft`, appears on
     the dashboard.
   - **Two-plane proof:** close the tab, reopen, navigate back → project + tier settings intact.
   - **Edit** question/tiers on the Plan tab → persists across reload.
   - **Cancel** an active project → status flips to `cancelled`, the Cancel button hides, sources
     preserved.
   - **Re-plan proof (PRD #24):** from `cancelled`, a re-plan moves it back to `planning` with stored
     sources intact (transition allowed; full regeneration is Phase 5).
   - **Delete** from the dashboard → confirm → project gone permanently (children cascade away).
   - `npm run build` clean.

---

## Doc updates on completion (per CLAUDE.md)

- `context/log.md` — Phase 2 entry (newest first).
- `context/map.md` — add `supabase/migrations/0007_project_lifecycle.sql`,
  `web/src/lib/data/projects.actions.ts`, `web/src/lib/data/mappers.ts`,
  `web/src/app/(app)/project/new/page.tsx`, `NewProjectForm`, `CancelProjectButton`; note the
  `ProjectCard` delete menu + `PlanTab` editor; note `client.ts` project fns are now Supabase-backed.
- `context/decisions.md` — record the three resolved decisions: **hard delete (cascade) + confirm**;
  **re-plannable status map** (`cancelled/complete → planning`, per PRD #24); **Plan-tab inline edit
  placement**.
- `context/deferredwork.md` — in the "Dummy/placeholder data in use" table, mark Dashboard project
  list, Project header/status, and Source-tier settings as **real (Phase 2)**.
