# Phase 10 Plan — Reports (pulled ahead of Phase 9)

**Status:** planned, not started. **Author date:** 2026-06-01.

> **Phase reorder.** The PRD module order lists Phase 9 (RAG Chatbot) before Phase 10
> (Reports). We are doing **Reports first**. Reports depends only on Phase 4 (storage)
> and Phase 6 (stored sources) — both complete — and has **no dependency on the
> chatbot**, so nothing blocks pulling it ahead. RAG Chatbot becomes the following
> phase. This reorder is recorded in `decisions.md` when the build starts.

---

## 1. Goal (PRD §Phase 10, User Stories 18–23)

Turn a project's stored sources into a citable markdown report. Two entry paths:

- **Curated** — the user browses sources by subtopic, selects up to 25, optionally
  provides instructions (tone / audience / focus), and generates.
- **Auto-draft** — the LLM reviews all key takeaways, selects the top 25, then
  synthesizes (no manual selection).

Report generation **runs as a job** (PRD §Report Synthesis: "async, not streamed").
Output is markdown, rendered for preview and downloadable as `.md`.

**Scope decisions (confirmed with user 2026-06-01):**
- **Markdown-only** this phase. PDF export stays in `deferredwork.md` (needs a
  server-side renderer — Puppeteer / @react-pdf / headless Chrome on Render).
- **Both** curated and auto-draft modes ship in this phase.

---

## 2. What already exists (UI is largely built)

| Asset | State |
|---|---|
| `report/ReportTab.tsx` | Source selector, 25-cap, **Select all/Deselect all**, `.md` download, preview pane. **Only the Generate button is disabled.** |
| `report/SourceSelector.tsx` | Checkbox list w/ cap enforcement — done. |
| `report/ReportPreview.tsx` | react-markdown with design-token components — done. |
| `reports` table (migration 0002) | `markdown`, `source_refs uuid[]`, `generated_at` — done. |
| RLS (migration 0005) | `reports_select` (can_access_project), `reports_insert` (can_write_project), `reports_delete` — done. |
| `getReport()` / `getSources()` (`data/client.ts`) | done. |

Phase 10 is therefore **backend + wiring the existing UI live**, not new UI from scratch.

---

## 3. ⚠️ Realtime gap to close

`reports` is **NOT in the Supabase Realtime publication.** Migration `0002` publishes
`projects, subtopics, sources, source_subtopics`; `0003` adds `jobs, worker_activity`.
Without publishing `reports`, a freshly generated report will not appear in the open
tab until a manual refresh — breaking the two-plane "browser is a pure projection"
invariant. **The migration below adds it.**

---

## 4. Backend (build first, per CLAUDE.md)

### 4.1 Migration `0012_report_realtime.sql`
```sql
alter publication supabase_realtime add table reports;
```
Idempotency note: like prior phases, may be applied directly to live Supabase over
`SUPABASE_DB_URL` if the CLI isn't linked; record in `deferredwork.md`.

### 4.2 Contract — `shared/schemas/job_payloads.py`
Add and register in `JOB_PAYLOAD_MODELS`:
```python
class GenerateReportPayload(BaseModel):
    """Payload for the 'generate_report' job type (Phase 10 reports)."""
    project_id: str
    mode: Literal["curated", "auto"]
    source_ids: list[str] = []          # curated: user selection; auto: ignored
    instructions: str | None = None     # optional tone/audience/focus
    progress: str | None = None
```

### 4.3 LLM schemas — `worker/worker/llm/schemas.py`
```python
class AutoDraftSelection(BaseModel):
    """Auto-draft mode: LLM picks the top sources to include (<=25)."""
    selected_source_ids: list[str]

class ReportDraft(BaseModel):
    """Report synthesis output."""
    markdown: str
    source_ids_used: list[str]          # records reports.source_refs; validated subset
```

### 4.4 Handler — `worker/worker/handlers/report.py` (job type `generate_report`)
Mirror `handlers/coordinator.py`'s shape (cancellation checks at entry + post-LLM,
`progress` checkpointing).

Steps:
1. Load project (`research_question`); guard not-found.
2. **Select sources:**
   - `auto`: load every source's `{id, title, key_takeaway}` → `invoke_structured(AutoDraftSelection)` → take its ids, **server-side capped at 25**.
   - `curated`: use `payload.source_ids`, **server-side capped at 25** (never trust the client cap).
3. Load full rows for chosen ids (`title, url, key_takeaway, full_text`), truncating
   `full_text` per a tunable `REPORT_SOURCE_CHARS` budget (config.toml `[report]`) so
   the synthesis prompt stays under the context ceiling. Sources scoped to
   `project_id` (isolation).
4. `invoke_structured(ReportDraft)` with the research question, the selected sources,
   and optional `instructions`. Prompt for **inline citations as markdown links** to
   source URLs plus a **References** section. Validate `source_ids_used ⊆ provided set`
   (drop any hallucinated ids).
5. Insert a `reports` row (`markdown`, `source_refs = source_ids_used`). Realtime
   delivers it to the open tab.

Register in `handlers/__init__.py`. **No project-status change** — projects are
already `complete` after research; report generation is independent and repeatable
(each run inserts a new `reports` row; `getReport` returns the latest).

### 4.5 Config — `worker/config.toml [report]`
- `report_source_chars` (per-source full-text truncation budget).
- `report_source_cap = 25` (single source of truth for the cap; used server-side).

---

## 5. Frontend (wire after backend)

### 5.1 Server Action — `(app)/project/[id]/report/actions.ts`
`generateReport(projectId, { mode, sourceIds, instructions })`:
- auth check (pattern from `project/actions.ts`),
- insert a `generate_report` job (`payload` per 4.2),
- `revalidatePath('/project/[id]/report')`.

### 5.2 `report/ReportTab.tsx`
- Enable **Generate report** (curated; uses `selectedIds`, validates ≥1 selected).
- Add an **Auto-draft** button (ignores selection; `mode:"auto"`).
- Add an optional **instructions** textarea (tone/audience/focus).
- Remove the two "Phase 10" warning Callouts.
- Show a **"Generating…"** pending state until the report arrives (optimistic on
  action submit; cleared when Realtime delivers the new `reports` row).
- Reference `DESIGN.md` for the new controls (per CLAUDE.md UI rule).

### 5.3 `report/ReportRealtime.tsx`
`"use client"` Supabase Realtime subscription to `reports` INSERTs for this project
→ `router.refresh()`. Same pattern as `realtime/ProjectRealtime.tsx`. Functional once
migration 0012 lands. Mount in the report page (or project layout).

---

## 6. Tests (PRD §Testing — reports)

`worker/tests/test_report.py` (mocked LLM + DB):
- curated mode caps at 25 server-side even if more ids are passed,
- auto-draft selects from all takeaways and respects the cap,
- generated markdown cites only sources in the used set,
- `source_refs` recorded correctly,
- project-isolation (only this project's sources are ever loaded),
- pre-LLM and post-LLM cancellation exit cleanly.

`worker/tests/test_contract.py`: add `GenerateReportPayload` round-trip.

---

## 7. Doc updates on completion (per CLAUDE.md)

- `log.md` — Phase 10 entry.
- `map.md` — new `handlers/report.py`, `report/actions.ts`, `report/ReportRealtime.tsx`,
  migration `0012`, schema additions.
- `decisions.md` — (a) **reorder: Reports before RAG**; (b) report-as-a-job confirmation;
  (c) markdown-only / PDF deferred.
- `deferredwork.md` — apply migration 0012 + enable `reports` Realtime in the Supabase
  dashboard (same operator step as prior phases); PDF export remains deferred.
- Flip the Report surface row in `deferredwork.md`'s status table to **live**.

---

## 8. Build order (backend → frontend, per CLAUDE.md)

1. Migration 0012 + contract `GenerateReportPayload`.
2. LLM schemas (`AutoDraftSelection`, `ReportDraft`) + config `[report]`.
3. `handlers/report.py` + register + `test_report.py` (TDD-friendly: mock LLM/DB).
4. Server Action `generateReport`.
5. `ReportTab.tsx` enablement (Generate + Auto-draft + instructions) + `ReportRealtime.tsx`.
6. Docs.
