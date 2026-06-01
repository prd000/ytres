# Plan — Phase 4 (Storage & Embeddings) + Phase 5 (Planner), with Realtime pulled forward + `social_media` tier

## Context

Phases 0–3 are complete: the Next.js shell, Supabase infra/auth, the Projects module, and the deterministic search package (`worker/worker/search/`). The app can create a project and lands the user on the Plan tab — but that tab is a **dead end**: the Approve/Regenerate buttons are mocked client-state only (`PlanTab.tsx:104,111`), no plan is ever generated, and **no LLM layer exists yet** (only LangChain *tracing* env vars are wired).

This phase delivers the two remaining prerequisites for the Phase 6 worker pipeline, chosen to be built together:

- **Phase 5 — Planner:** the first real AI moment. Submitting a research question enqueues a worker job; a DeepSeek coordinator (via LangChain) generates 3–8 subtopics and writes them to `subtopics`. This establishes the **LLM scaffolding** (LangChain + DeepSeek + LangSmith) and the **web→worker job-enqueue pattern** that every later phase reuses, and brings the Plan tab to life.
- **Phase 4 — Storage & Embeddings:** the deterministic storage backbone Phase 6 workers will call — fixed-size chunking, OpenAI embeddings, pgvector indexing, hybrid (vector+keyword) search, and URL-dedup source writes. No UI surface; delivered as a tested worker library + SQL migrations.

Two user-chosen scope additions:
- **Pull Supabase Realtime forward** (instead of interim polling): a minimal subscription so the Plan tab updates live the instant the worker writes subtopics — the seam the project layout already reserves (`[id]/layout.tsx:15`).
- **Add a `social_media` source tier** (from `bug-corrections.md` — "Reddit is useful"), folded in since the planner already touches tiers end-to-end.

> ⚠️ **Next.js 16 caveat:** `web/AGENTS.md` warns this is a breaking-change Next.js with non-standard APIs. **Before writing any web code, read the relevant guides in `web/node_modules/next/dist/docs/`** (Server Actions, client components, `revalidatePath`, typed `LayoutProps`/`PageProps`). `params` is a Promise; `cookies()` is async.

> **Build order (per CLAUDE.md):** backend first (migrations → worker), then wire the frontend.

---

## Part A — Worker LLM layer (NEW `worker/worker/llm/`)

First LLM integration. Use **`langchain-openai` `ChatOpenAI` pointed at DeepSeek's OpenAI-compatible endpoint** (PRD mandates the model-agnostic OpenAI-compatible interface — provider swap = config edit, no code change).

- `llm/config.py` — frozen `LLMConfig` dataclass + `from_env()`, mirroring `worker/worker/search/config.py` exactly (reads `config.toml [llm]` + secrets from env; kept separate from `worker.config` so tests don't need `SUPABASE_DB_URL`). Fields: model ids per role (coordinator/worker/classifier), `base_url`, `temperature`, `timeout`, `max_retries`, embedding model/dimensions, `deepseek_api_key`, `openai_api_key`.
- `llm/factory.py` — `build_chat_model(cfg, role, *, temperature=None, tags=None) -> BaseChatModel` returning `ChatOpenAI(model=cfg.model_for(role), api_key=cfg.deepseek_api_key, base_url=cfg.base_url, temperature=…, timeout=…, max_retries=…, tags=[…, f"role:{role}"])`.
- `llm/schemas.py` — the planner's structured-output Pydantic models (see Part C).
- **Structured output:** `llm.with_structured_output(ResearchPlan, method="function_calling")` then `await chain.with_config({"run_name": "generate_plan"}).ainvoke(messages)`. ⚠️ *Uncertain:* DeepSeek tool-calling support — **fallback** `method="json_mode"` (DeepSeek supports `response_format={"type":"json_object"}`) or `PydanticOutputParser` with format instructions in the system prompt. Wrap in a small helper that degrades gracefully.
- **LangSmith** tracing is already auto-enabled via env (`config.py:72`); just ensure `LANGCHAIN_API_KEY` is set in env and add per-call `run_name`/`tags`.

**`config.toml`** — append:
```toml
[llm]
base_url             = "https://api.deepseek.com/v1"
coordinator_model    = "deepseek-v4-pro"
worker_model         = "deepseek-v4-pro"
classifier_model     = "deepseek-v4-flash"
temperature          = 0.2
timeout              = 120.0
max_retries          = 3
embedding_model      = "text-embedding-3-small"
embedding_dimensions = 1536
```
**`worker/worker/config.py`** — add after the search-keys block (~line 69):
```python
DEEPSEEK_API_KEY: str | None = os.environ.get("DEEPSEEK_API_KEY")
OPENAI_API_KEY:   str | None = os.environ.get("OPENAI_API_KEY")
```
**`worker/pyproject.toml`** — add deps: `langchain-core>=0.3`, `langchain-openai>=0.2`, `openai>=1.40`, `tiktoken>=0.7`.

---

## Part B — Storage & Embeddings (Phase 4, NEW `worker/worker/storage/`)

Pure-ish, testable library consumed later by Phase 6. The worker uses a **direct asyncpg connection that bypasses RLS** (per design), so writes are unrestricted.

- `storage/chunking.py` (pure, unit-testable) — `count_tokens(text)` and `chunk_text(text, *, chunk_tokens=500, overlap_tokens=100) -> list[Chunk]` using `tiktoken.get_encoding("cl100k_base")`; sliding window with `stride = chunk_tokens - overlap_tokens`; `[]` for empty; `ValueError` if `overlap >= chunk_tokens`.
- `storage/embeddings.py` — `Embedder(cfg, client=None)` wrapping `AsyncOpenAI` (injectable for tests); `async embed_texts(texts) -> list[list[float]]`, batched ≤128, order-preserving, asserts dim == 1536. (Raw `openai` SDK, not LangChain — embeddings are deterministic plumbing, not traced reasoning.)
- `storage/store.py` — pgvector writes via **string-literal cast** (no codec registration): `_vector_literal(vec) -> "[…]"`, inserted with `$N::vector`.
  - `store_source(conn, …) -> (source_id, created: bool)` — honors `unique(project_id, url)` via `insert … on conflict (project_id,url) do update set url = sources.url returning id, (xmax = 0) as created`, then links `source_subtopics` with `on conflict do nothing`.
  - `store_chunks(conn, source_id, project_id, chunks, embeddings) -> int` via `executemany`.
- `storage/search.py` — thin wrapper calling the `match_chunks(...)` SQL function (Part D) and mapping rows to `ChunkMatch`.

---

## Part C — Planner handler (Phase 5, NEW `worker/worker/handlers/planner.py`, job type `generate_plan`)

**Payload** — append to `shared/schemas/job_payloads.py` and register in `JOB_PAYLOAD_MODELS`:
```python
class GeneratePlanPayload(BaseModel):
    project_id: str
    feedback: str | None = None     # present on REGENERATE
    progress: str | None = None
```
**Structured-output models** (`llm/schemas.py`) — `SourceTier = Literal["academic","government","news","industry","social_media"]`; `PlannedSubtopic{title, information_objective, source_tier_preferences: list[SourceTier]}`; `ResearchPlan{subtopics: list[PlannedSubtopic]}` with `min_length=3, max_length=8` (encodes the PRD budget guardrail).

**Flow** (mirrors `handlers/echo.py` contract — `async def handle(ctx) -> dict`):
1. `is_cancelled()` early-out → read `projects` row (`research_question`, `source_tier_settings`); raise if missing → loop fails the job.
2. `checkpoint(progress="planning")`.
3. Build coordinator messages (system: decompose into 3–8 non-overlapping subtopics, each a concrete `information_objective` + 1–3 tier prefs honoring `source_tier_settings`; revise prior plan if `feedback` present) → `await structured.ainvoke(...)`.
4. cancellation re-check (don't write if cancelled post-LLM).
5. **One asyncpg transaction:** `delete from subtopics where project_id=$1` then loop-insert new rows (`sort_order=i`, `status='queued'`, `source_tier_preferences` cast `$N::source_tier[]`). Delete-then-insert makes the handler **idempotent on resume and identical for first-plan vs regenerate**.
6. `checkpoint(progress="done", subtopic_count=N)`; return.

**Do NOT mutate `project.status`** in the worker — the web sets `planning` on enqueue; *presence of subtopics* signals "ready to review" (single responsibility, no races). Register in `handlers/__init__.py`: `"generate_plan": planner_handle`.

---

## Part D — SQL migrations (NEW files after `0006`)

- **`0007_vector_indexes.sql`** — `create index … on source_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);` + GIN FTS index `using gin (to_tsvector('english', content))` + `(project_id)` btree. *Note: ivfflat trains poorly on an empty table — REINDEX once real chunks exist; HNSW is the no-tuning upgrade path.*
- **`0008_match_chunks.sql`** — `match_chunks(p_project_id uuid, p_query_embedding vector(1536), p_query_text text, p_match_count int default 12)` `language sql stable`: vector CTE (`1 - (embedding <=> q)` cosine sim, ranked) `full outer join` keyword CTE (`ts_rank`/`plainto_tsquery`), fused via **Reciprocal Rank Fusion** (`1/(60+rank)`), `order by score desc limit p_match_count`, scoped `where project_id = p_project_id`. Lives as a migration function so the worker now and the Phase 9 RAG share one canonical implementation. (Not `SECURITY DEFINER` — worker bypasses RLS; a definer wrapper for `authenticated` callers is deferred to Phase 9.)
- **`0009_social_media_tier.sql`** — `alter type source_tier add value if not exists 'social_media';` (own file; `ADD VALUE` cannot run mid-transaction with same-tx use — isolating it is safest).

---

## Part E — Web wiring (Server Actions + Plan tab)

Establish the first job-enqueue from the web. Authenticated `createClient()` inserts into `jobs` directly — RLS `jobs_insert` already checks `can_write_project` (no service-role needed). Reuse the `createProject` pattern in `web/src/app/(app)/project/actions.ts` (auth via `supabase.auth.getUser()`, `{error}` returns, `redirect()`).

- **`createProject` (modify):** after inserting the project, set `status: "planning"` (not `"draft"`) and **enqueue a `generate_plan` job** (`jobs.insert({project_id, type:"generate_plan", payload:{project_id}})`) so submitting the question auto-starts planning (PRD user story #2). Then `redirect(/project/${id}/plan)`.
- **`regeneratePlan(projectId, feedback)` (new action):** insert a `generate_plan` job with `payload:{project_id, feedback}`, ensure status `planning`, `revalidatePath`.
- **`approvePlan(projectId)` (new action):** update `projects.status` → `"researching"`. *(Phase 6 will hook research-job enqueue here; for now this only transitions status — do NOT enqueue `research_subtopic` jobs, there's no handler yet.)*
- **`PlanTab.tsx` (rewrite the action area):** replace mocked `setApproved`/`setFeedback` buttons with the real actions (`useActionState`/form actions). Render by state:
  - `status==="planning"` & **no** subtopics → "Generating your research plan…" loading state (Realtime will populate).
  - `status==="planning"` & subtopics present → plan list + **Approve** (→ `approvePlan`) / **Regenerate with feedback** (→ `regeneratePlan`).
  - `status==="researching"|"complete"` → approved view (existing callout).
  - Keep a "Generate plan" CTA for the legacy `draft` path as a fallback. Reference `DESIGN.md` for the loading/empty-state styling (coral CTAs, cream surfaces).

---

## Part F — Realtime (pulled forward)

Minimal subscription so the Plan tab (and later tabs) reflect worker writes live; this is the Phase 7 seam, started early.

- **`web/src/components/features/realtime/ProjectRealtime.tsx`** (`"use client"`) — takes `projectId`; uses browser `createClient()` (`supabase/client.ts`); subscribes to `postgres_changes` on **`subtopics`** (`filter: project_id=eq.${projectId}`) and **`projects`** (`filter: id=eq.${projectId}`); on any event calls `router.refresh()` (`next/navigation`) to re-run server components / re-fetch via `client.ts`. Cleanup `supabase.removeChannel(channel)` on unmount.
- **Mount in `(app)/project/[id]/layout.tsx`** (stays mounted across tabs — the reserved seam at line 15).
- The Realtime publication already includes these tables (migrations `0002`/`0003`). ⚠️ **RLS-over-Realtime gotcha:** the stream must carry the user JWT for `can_access_project` to authorize it. `@supabase/ssr` `createBrowserClient` should propagate the session; if events don't arrive, call `supabase.realtime.setAuth()` with the session token. Verify during testing.

---

## Part G — `social_media` source tier (cross-cutting)

Backend enum migration is Part D (`0009`). Then thread the value through:
- **Worker:** the `SourceTier` literal in `llm/schemas.py` already includes `social_media` (Part C).
- **Web types** (`web/src/lib/data/types.ts`): add `"social_media"` to `SourceTier`; add `socialMedia: boolean` to `SourceTierSettings`.
- **Create form** (`NewProjectForm.tsx`): add `{ key: "social_media", label: "Social media" }` to `TIERS`. *(Form field `name` is the checkbox key — confirm `createProject` parses it into `source_tier_settings`.)*
- **`createProject` / `client.ts mapProject`:** include the `social_media` ↔ `socialMedia` mapping in the jsonb read/write.
- **`PlanTab.tsx`:** add `social_media: "Social media"` to `TIER_LABELS` and to the displayed tier array (line 43).
- Reference `DESIGN.md` for the new chip/badge — reuse existing tier-pill styling (no new tokens).

---

## Tests (`worker/tests/`, LLM + embeddings MOCKED — no real API/network)

Reuse `conftest.py` (`db` fixture, `_seed_user/_seed_project/_seed_subtopic`, force-rollback per test).
- `test_chunking.py` (pure) — empty→`[]`; short→1 chunk; long→overlapping sequential chunks, `token_count ≤ chunk_tokens`; `overlap≥chunk`→`ValueError`.
- `test_embeddings.py` (fake `AsyncOpenAI`) — 1536-dim, order/count preserved, 300 inputs→3 batched calls, empty→no call.
- `test_storage.py` (integration vs real PG) — `store_source` insert→`(id,True)`; duplicate `(project_id,url)`→`(same_id,False)` + idempotent link; `store_chunks` writes non-null `vector` rows with correct `chunk_index`/`token_count`.
- `test_hybrid_search.py` (integration; needs `0007`+`0008`) — seed chunks with hand-crafted embeddings + distinct keyword text; assert vector-near ranks high, keyword chunk surfaces, only seeded project returned, `len ≤ match_count`, scores descending.
- `test_planner.py` (mocked structured LLM; fake `JobContext`) — canned `ResearchPlan(4)` → 4 subtopic rows, `sort_order` 0..3, enum array persisted, `status='queued'`; **regenerate** (pre-seed 2 → plan of 3 → exactly 3 remain); **idempotent resume** (run twice → N rows); **cancellation** before/after LLM → no writes; `project.status` unchanged.
- `test_contract.py` (extend) — `GeneratePlanPayload` valid/invalid; registry has `generate_plan`.

Run: `cd worker && pytest`. Web: `cd web && npx tsc --noEmit && npm run build`.

---

## Config / deferred work / env vars (alert the user)

These move from "future" to **required to run this phase end-to-end** — update `deferredwork.md` and alert:
- `DEEPSEEK_API_KEY` — coordinator/worker/classifier (planner won't generate without it).
- `OPENAI_API_KEY` — `text-embedding-3-small` (Phase 4 storage).
- `LANGCHAIN_API_KEY` — LangSmith tracing (tracing flag already on).
- Add all three to `worker/.env`, `.env.example`, and Render `ytres-worker` env.
- Apply migrations: `supabase db push` (0007–0009). Confirm Realtime is enabled for `subtopics`/`projects` in the Supabase dashboard.

---

## Verification (end-to-end)

1. **Migrations:** `supabase db push`; confirm `source_tier` has `social_media`, the ivfflat/GIN indexes and `match_chunks` exist.
2. **Worker unit/integration:** `cd worker && pytest` — all green (LLM/embeddings mocked).
3. **Planner live (needs `DEEPSEEK_API_KEY`):** run the worker (`python -m worker.main`); from the app, create a project → lands on `/plan` showing "Generating…" → within seconds the subtopics appear **without a manual refresh** (proves Realtime). Enter feedback → Regenerate → subtopic list replaces live. Approve → status flips to `researching`.
4. **Storage (needs `OPENAI_API_KEY`):** covered by `test_storage.py`/`test_hybrid_search.py`; no UI surface until Phase 6.
5. **LangSmith:** confirm the `generate_plan` run appears in the LangSmith project.
6. **Social tier:** new-project form shows "Social media"; selecting it persists; the planner may assign it; it renders in the Plan tab.

---

## Doc updates (required by CLAUDE.md)

- `log.md` — new dated entry (newest first) covering Parts A–G.
- `map.md` — add `worker/worker/llm/*`, `worker/worker/storage/*`, `handlers/planner.py`, the three migrations, `ProjectRealtime.tsx`, new Server Actions; update the `agent/` vs `agent-complete/` rows.
- `decisions.md` — record: (1) `ChatOpenAI`+DeepSeek base_url over `langchain-deepseek`; (2) hybrid search as a SQL `match_chunks` function w/ RRF; (3) pgvector via `$N::vector` string cast (no codec); (4) planner runs as a worker job, web sets `planning`/subtopic-presence signals ready; (5) Realtime pulled forward into Phase 5.
- `deferredwork.md` — mark `DEEPSEEK_API_KEY`/`OPENAI_API_KEY`/`LANGCHAIN_API_KEY` as now-active; note ivfflat REINDEX-after-data; note Phase 6 will wire `approvePlan`→research enqueue and tier→search routing (incl. `social_media`→web/Reddit).
- `bug-corrections.md` — mark the social-media tier feature done (the sign-in spacing bug remains open/out of scope here).
- Move this plan to `agent-complete/` when finished (per repo convention).
