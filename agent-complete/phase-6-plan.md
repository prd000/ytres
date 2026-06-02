# Phase 6 — Worker Pipeline (+ LangSmith fix, + live progress)

## Context

Phases 0, 1, 3, 4, 5 are complete. The system can create a project, generate & approve a
plan, and has all the *ingredients* of research — a durable job queue (P1), a search
router (P3), chunking/embeddings/storage (P4), and an LLM layer (P5) — but **nothing
consumes them together**. `approvePlan` flips a project to `researching` yet enqueues no
work; there is no `research_subtopic` handler. The Research tab UI already reads
`worker_activity`, but no code writes those rows.

Phase 6 builds the agent that does the actual research: for each approved subtopic, an
async worker generates queries, searches, evaluates sources in two passes, stores
quality findings with embeddings, and reports progress — durably, with checkpointing,
cancellation, source caps, retry, and context-window handoff. This is the keystone that
makes the product real and unblocks chat (P9) and reports (P10).

Two confirmed scope additions:
- **Fix LangSmith tracing first** (`bug-corrections.md` #1). Phase 6 multiplies LLM calls;
  observability must work before we add them. Root cause is known (below).
- **Make the Research tab live** — worker writes `worker_activity`, and `ProjectRealtime`
  subscribes to `worker_activity` + `sources` (the front-end half of Phase 7, pulled forward).

Build order per CLAUDE.md: **backend first, then wire the frontend.**

---

## Step 0 — Fix LangSmith tracing (root cause)

**Diagnosis (grounded in code):**
- `worker/worker/config.py:76-77` sets only `LANGCHAIN_TRACING_V2` and `LANGCHAIN_PROJECT`.
  **No LangSmith API key is ever read or exported.** LangChain's tracer silently no-ops
  without `LANGCHAIN_API_KEY`/`LANGSMITH_API_KEY` — so the LLM call succeeds but no trace
  is pushed (exactly the reported symptom).
- `load_dotenv()` runs **only** in `worker/tests/conftest.py:16`, never in the worker
  runtime — `main.py` doesn't load `.env`. Local runs rely on whatever is in the ambient
  env. (On Render this is masked because env vars come from the dashboard.)

**Fix:**
- `worker/worker/main.py` — call `load_dotenv()` **before** `import worker.config` so the
  runtime loads `.env` like the tests do.
- `worker/worker/config.py` — read `LANGCHAIN_API_KEY` (fallback `LANGSMITH_API_KEY`) and
  export **both** names, plus default `LANGCHAIN_ENDPOINT`/`LANGSMITH_ENDPOINT`
  (`https://api.smith.langchain.com`) and `LANGSMITH_TRACING` (mirror of the V2 flag) so it
  works regardless of which env-var generation the installed SDK reads. Add a startup log
  line: `LangSmith tracing: ACTIVE (project=ytres)` vs `INACTIVE (no API key)` — mirrors the
  existing `db.py` diagnostic pattern so a future "no traces" issue is self-explaining.
- `.env.example` + `context/deferredwork.md` — document `LANGCHAIN_API_KEY` as the canonical
  name (the P4+5 table used `LANGCHAIN_API_KEY`, the older one `LANGSMITH_API_KEY`; both now work).

The factory already passes `tags`/`run_name` (`factory.py:32`, `planner.py:75`), so once the
key is wired, all existing and new calls trace automatically — no per-call change needed.

---

## Step 1 — Backend: new job type & payload contract

- `shared/schemas/job_payloads.py` — add `ResearchSubtopicPayload`:
  `{ project_id, subtopic_id, progress?, checkpoint? }` where `checkpoint` is the
  resume state (see Step 4). Register `"research_subtopic"` in `JOB_PAYLOAD_MODELS`.

## Step 2 — Backend: LLM schemas for the pipeline

`worker/worker/llm/schemas.py` — add structured-output models:
- `SearchQuerySet { queries: list[str] }` (Field min 3, max 5) — query generation.
- `Pass1Batch { items: list[Pass1Item] }`, `Pass1Item { index:int, relevant:bool, accessible:bool }`
  — one batched Flash call classifies all snippets (cheap, few calls).
- `SourceEvaluation { score_relevance:int, score_credibility:int, score_uniqueness:int,
  score_actionability:int, key_takeaway:str }` — Pro pass-2 (ints 1–5 via `Field(ge=1, le=5)`).
- "Why-nothing" uses a plain text completion (no schema needed).

Reuse `_invoke_structured()`'s function_calling→json_mode fallback (currently private in
`planner.py:71`) — **lift it into `worker/worker/llm/factory.py`** as a shared helper so both
handlers use one implementation.

## Step 3 — Backend: activity + subtopic-status write helpers

`worker/worker/storage/activity.py` (new) — small asyncpg helpers (worker bypasses RLS):
- `upsert_activity(conn, *, subtopic_id, project_id, latest_activity, sources_stored, status, why_nothing_report=None)`
  → `INSERT … ON CONFLICT (subtopic_id) DO UPDATE` against `worker_activity`
  (columns verified in `0003_jobs_and_activity.sql:25-33`).
- `set_subtopic_status(conn, subtopic_id, status)` → update `subtopics.status`
  (enum `subtopic_status`: queued/running/complete/failed/cancelled).

The worker owns these data writes (matches Decisions §"Decision 4 — web owns status
transitions, worker owns data writes").

## Step 4 — Backend: the research handler (the core)

`worker/worker/handlers/research.py` — `handle(ctx)`, registered as `"research_subtopic"`
in `handlers/__init__.py`. Mirrors `planner.py`'s structure (cancellation checks,
`ctx.checkpoint(payload)` between stages, pool usage).

Pipeline per subtopic:
1. Load subtopic (`title`, `information_objective`, `source_tier_preferences`) + project
   `source_tier_settings`. Cancellation check. Set subtopic `running` + activity
   "Generating search queries".
2. **Query generation** (Pro/`worker` role) → `SearchQuerySet` (3–5 queries).
3. **Search** via `SearchRouter` (`worker.search.build_router(SearchConfig.from_env())`):
   run each query, collect ≤25 candidates, **dedup by URL**. Activity "Searching…".
4. **Pass 1 (Flash/`classifier`)**: one batched call over snippets → drop
   irrelevant/paywalled (`accessible=false`). Activity "Filtered N candidates".
5. For survivors: **extract full text** via `ExtractionChain`
   (`worker.search.extraction.chain`) — raw_content short-circuit → trafilatura → Jina.
   Skip on `ExtractionFailed`. Activity "Reading <domain>".
6. **Pass 2 (Pro/`worker`)**: per source → `SourceEvaluation`. Uniqueness is judged against
   the **key-takeaways of already-stored sources for this subtopic** (passed in the prompt,
   per PRD — not full text). **Store rule: avg(scores) ≥ 3 AND no dimension == 1.**
7. On store: `chunk_text` → `Embedder.embed` → `store_source` + `store_chunks` in one
   transaction (all exist in `worker/worker/storage/`). Increment `sources_stored`; append
   takeaway to the in-memory uniqueness list; activity "Stored: <title> (N sources)".
8. **Caps/targets:** stop at **12 stored**; **min target 3**.
9. **Auto-retry (one extra wave):** if 0 stored (or < min) after wave 1, regenerate queries
   with a "previous angle found nothing — try different terms/sources" instruction and retry.
10. **"Why-nothing" report:** if still 0 after retry, Pro generates a short explanation of
    what was attempted → `worker_activity.why_nothing_report`. Subtopic → `complete`.
11. **Context-window handoff (100K self-imposed ceiling):** track cumulative tokens fed to
    Pro evals via `count_tokens` (`storage/chunking.py`). Before an eval that would exceed
    the ceiling, **enqueue a continuation `research_subtopic` job** carrying a `checkpoint`
    payload `{ processed_urls, stored_count, queries, query_index, stored_takeaways }` and
    return cleanly. Ceiling is a tunable constant (new `[worker] context_ceiling_tokens =
    100000` in `config.toml`, read in `worker/worker/config.py`). Add a thin
    `enqueue_job(conn, project_id, type, payload)` helper in `worker/worker/queue.py`
    (currently the queue has no enqueue path — jobs are only inserted from the web).
12. **Idempotent resume:** on claim, if `payload.checkpoint` is present, skip
    `processed_urls` and resume from `query_index`. DB-side URL dedup (`store_source`'s
    `unique(project_id,url)`) makes re-processing a no-op regardless.
13. Final: subtopic `complete`, activity `complete`, checkpoint done.

Cancellation: check `ctx.is_cancelled()` before each LLM/search batch and before every DB
write, exactly like `planner.py:91,127`.

## Step 5 — Backend: social_media tier routing

`worker/worker/search/router.py:14` — add `"social_media": "web"` to `TIER_ROUTING`
(closes a `deferredwork.md` Phase-6 item; the planner already emits this tier).

## Step 6 — Frontend wiring (after backend)

- `web/src/app/(app)/project/actions.ts` `approvePlan` — after `status='researching'`,
  `select id from subtopics where project_id=…` and bulk-`insert` one
  `{ project_id, type:'research_subtopic', payload:{ project_id, subtopic_id } }` job per
  subtopic. (Mirrors the existing `createProject` enqueue at `actions.ts:50`.) Optionally
  upsert `worker_activity` queued rows for instant UI; the tab already tolerates missing rows.
- `web/src/components/features/realtime/ProjectRealtime.tsx` — add two more
  `.on("postgres_changes", …)` handlers for `worker_activity` and `sources`
  (`filter: project_id=eq.${projectId}`), each calling `router.refresh()`. No new component;
  it already lives in the project layout and stays mounted across tabs.

`ResearchTab.tsx` and `data/client.ts:getWorkerActivity` already consume every field
(`latestActivity`, `sourcesStored`, `whyNothingReport`, `status`) — **no UI changes needed**.

## Step 7 — Tests (mocked external APIs, per PRD testing decisions)

- `worker/tests/test_research.py` (new) — fake LLM + fake `SearchRouter` + fake `Embedder`:
  store rule (avg≥3 & no-1), source cap (12), min-target triggers second angle, why-nothing
  on empty, pre/post-LLM cancellation, idempotent resume from `checkpoint`, handoff enqueues
  a continuation job, `worker_activity` upsert sequence.
- `worker/tests/test_contract.py` — extend with `ResearchSubtopicPayload` valid/invalid/missing-id.
- `worker/tests/test_search_router.py` — assert `social_media` routes to web.
- Optional `test_observability.py` — config exports both API-key env names + endpoint when key present.

## Step 8 — Docs (required by CLAUDE.md)

- `context/log.md` — Phase 6 entry (newest first).
- `context/map.md` — add `handlers/research.py`, `storage/activity.py`, new schemas, test file.
- `context/decisions.md` — record: two-pass eval + store rule, handoff checkpoint shape,
  `social_media`→web routing, LangSmith key-wiring fix, `enqueue_job` worker helper.
- `context/deferredwork.md` — add `LANGCHAIN_API_KEY`; remove the now-done Phase-6 deferred
  items (approvePlan enqueue, social_media routing); note any new key needs.
- `context/bug-corrections.md` — mark tracing bug #1 fixed.

---

## Verification (end-to-end)

This machine has **no local Supabase/Docker** (noted repeatedly in `log.md`), so split it:

1. **Static/CI-able now:** `python -m py_compile` on changed files; `cd web && npx tsc --noEmit`;
   run the mocked worker suite `pytest worker/tests/test_research.py test_contract.py
   test_search_router.py` (no network/DB).
2. **Tracing:** with `DEEPSEEK_API_KEY` + `LANGCHAIN_API_KEY` set, run the worker, trigger a
   `generate_plan`, confirm the startup log says `tracing: ACTIVE` and the run appears in the
   LangSmith `ytres` project. (Closes bug #1.)
3. **Full pipeline (needs live Supabase + keys):** create a project → approve plan → watch the
   Research tab update live (queued→running→stored counts→complete) without refresh; verify
   `sources`/`source_chunks` rows and a `why_nothing_report` on a deliberately barren subtopic;
   cancel mid-run and confirm the worker stops and sources are preserved.

Items requiring the live stack will be flagged in `log.md` as "verified statically; live run
pending" — consistent with prior phases.

## Risks / open items

- **DeepSeek structured-output reliability** at pass-2 volume — mitigated by the existing
  function_calling→json_mode fallback (now shared).
- **Token-ceiling accounting** is an estimate (`count_tokens` on inputs); the handoff is a
  safety valve, not exact. Acceptable per PRD ("self-imposed guardrail, tunable constant").
- **Cost** — real DeepSeek + OpenAI + search keys are consumed during live verification (step 3).
