# PRD: AI-Powered Research Pipeline (v2)

> **v2 note:** This is a fresh attempt. The defining change from v1 is the execution model: there is no Celery and no Redis. Agent work runs as a **database-backed job queue** (Postgres `FOR UPDATE SKIP LOCKED`) with `asyncio` concurrency, and the **database is the single source of truth** for both data and in-flight work. The browser is a pure projection of database state, so navigating away from a project — or between tabs — can never orphan agent work. Hosting is committed to **Render** (plus managed **Supabase**).

## Problem Statement

Conducting deep research on a question requires manually searching across disparate sources, evaluating relevance and credibility, extracting key findings, and synthesizing results. This is time-consuming, inconsistent, and lacks structured persistence. Researchers need a system that automates discovery across web and academic sources, evaluates quality, stores findings in a queryable corpus, and produces cited reports — while keeping research projects isolated from one another, and while never losing the state of long-running research when the user navigates the app.

## Solution

A multi-agent research pipeline web application where users submit a research question, receive an AI-generated research plan with subtopics and source preferences, approve it, and watch as parallel research agents search the web and academic databases, evaluate sources, and store quality findings into a project-isolated vector database. Users can interrogate their collected corpus through a RAG chatbot that cites sources inline, spawn new research when answers are missing, and synthesize selected sources into a citable markdown report.

All agent work runs server-side, fully decoupled from the browser, and every state change is persisted to the database as it happens. Closing a tab, switching tabs, or refreshing the page never interrupts or orphans research — on return, the UI simply re-reads current state from the database.

## User Stories

1. As a researcher, I want to create a new research project by submitting a question, so that I can organize my research efforts around a central topic.
2. As a researcher, I want an AI coordinator to generate a structured research plan with subtopics and information objectives, so that I don't have to manually break down my question.
3. As a researcher, I want to see the generated plan and either approve it or provide feedback for regeneration, so that the research direction matches my intent.
4. As a researcher, I want to edit my research question and regenerate the plan, so that I can iterate until the plan is right.
5. As a researcher, I want to set global source tier preferences (academic papers, government sources, news, industry reports) and recency filters, so that the research aligns with my quality standards.
6. As a researcher, I want research subtopics executed by parallel AI agents that search across web and academic databases, so that research completes quickly and thoroughly.
7. As a researcher, I want to see real-time progress of each research agent (what source it's reading, what it's storing), so that the process doesn't feel like a black box.
8. As a researcher, I want each stored source to have a 1-2 sentence key takeaway, so that I can quickly understand what was found without reading every source.
9. As a researcher, I want agents to evaluate sources on relevance, credibility, uniqueness, and actionability before storing them, so that my research corpus isn't polluted with low-quality content.
10. As a researcher, I want agents to automatically retry with different search angles if the first pass finds nothing useful, so that subtopics aren't abandoned prematurely.
11. As a researcher, I want to see a "why nothing" report if a subtopic yields zero quality sources, so that I understand what was attempted and can decide next steps.
12. As a researcher, I want agents to skip paywalled sources, so that every stored source is fully accessible.
13. As a researcher, I want duplicate sources (same URL across subtopics) to be linked rather than stored twice, so that my corpus stays clean.
14. As a researcher, I want to chat with my collected sources through a RAG chatbot, so that I can interrogate the research corpus conversationally.
15. As a researcher, I want the chatbot to cite specific sources inline in its responses, so that I can verify claims and dive deeper.
16. As a researcher, I want the chatbot to offer to spawn a new research agent when it cannot answer my question, so that the corpus grows to cover gaps.
17. As a researcher, I want the chatbot-spawned research to create new subtopics under the existing project, so that follow-up research integrates seamlessly.
18. As a researcher, I want to browse all stored sources organized by subtopic with their key takeaways, so that I can review findings before synthesis.
19. As a researcher, I want to select specific sources for report generation (up to a cap), so that the report only includes what I deem important.
20. As a researcher, I want an auto-draft option that uses all sources to generate a report, so that I can get a report quickly without manual curation.
21. As a researcher, I want generated reports in markdown format with inline citations, so that I can edit, export, and share them easily.
22. As a researcher, I want to download reports as PDF or Markdown, so that I can use them outside the application.
23. As a researcher, I want to edit the generated report markdown before downloading, so that I can refine the output.
24. As a researcher, I want to cancel a running research project while preserving stored sources, so that I can re-plan without losing progress.
25. As a researcher, I want to be notified if external APIs fail and be given the option to retry, so that transient failures don't permanently block research.
26. As a researcher, I want to manage multiple research projects, so that I can work on different questions without cross-contamination.
27. As a researcher, I want project data fully isolated between projects, so that answers from one project never bleed into another.
28. As a user, I want to create an account and log in, so that my research projects are private and persistent.
29. As a user, I want to share a project with another user as a viewer or collaborator, so that I can collaborate with friends.
30. As a user, I want to see a dashboard of all my research projects with their status, so that I can pick up where I left off.
31. As a user, I want research that was running when I closed the tab to still be running (or already finished) when I return, so that I never have to manually restart or "redeploy" agents.

## Implementation Decisions

### Core Principle: Two Planes — Execution and Projection

The system is split into two strictly separated planes. This separation is the single most important architectural decision in v2 and directly fixes the v1 orphaning problem.

- **Execution plane (server-only).** A Next.js **Server Action** *triggers* research by inserting job rows and returns immediately. Agents run in a server-side worker process that has zero dependency on an open browser. Every state change — job status, per-subtopic activity, stored sources — is written to Postgres *as it happens*. Triggering is not running: the browser can close entirely and the work continues.
- **Projection plane (browser).** The UI is a pure projection of database state. On mount it reads current state from Supabase (RLS-scoped, via the `@supabase/ssr` server client); then it subscribes to Supabase Realtime for live deltas. Navigating away unsubscribes; returning re-reads and re-subscribes. Because no work and no progress state ever live in the browser, there is nothing to orphan. Re-mounting always reflects true state.

### Agent Execution: Database-Backed Job Queue (no Celery, no Redis)

Agent work is I/O-bound (waiting on search APIs, LLM responses, and content fetches), so concurrency comes from `asyncio`, not from a distributed task broker.

- **`jobs` table in Supabase** is the queue. Each unit of work (e.g. one subtopic to research, or a worker handoff continuation) is a row with: `id`, `project_id`, `type`, `status` (`queued` → `running` → `done` / `failed` / `cancelled`), `payload` (JSON), `attempts`, `heartbeat_at`, `claimed_by`, `created_at`, `updated_at`.
- **Worker process** (`worker.py`, a plain async polling loop — a Render Background Worker) claims work with:
  ```sql
  SELECT * FROM jobs
  WHERE status = 'queued'
  ORDER BY created_at
  FOR UPDATE SKIP LOCKED
  LIMIT 1;
  ```
  `FOR UPDATE SKIP LOCKED` lets multiple worker instances claim distinct rows safely without ever grabbing the same one — Postgres provides the queue semantics natively.
- **`asyncio` concurrency inside the worker** runs multiple subtopic agents simultaneously, bounded by a semaphore (the concurrency cap from Budget Guardrails). More parallelism on one box = raise the semaphore; more throughput across boxes = run another worker instance (no code change, thanks to `SKIP LOCKED`).
- **Heartbeats + self-healing watchdog.** A running job updates `heartbeat_at` periodically. A watchdog (a periodic sweep in the worker loop, or Supabase `pg_cron`) resets any `running` job whose `heartbeat_at` is stale back to `queued`, incrementing `attempts`. This reclaims work from a crashed or restarted worker automatically, resuming from the last persisted checkpoint — the user never has to "redeploy agents."
- **Idempotency.** Workers checkpoint progress to the database (which queries ran, which sources are stored) so that a reclaimed job resumes rather than restarting, and re-processing the same source is a no-op (URL dedup at the data layer).

### Architecture: Hybrid Coordinator/Worker Multi-Agent System

The research pipeline uses a coordinator-worker pattern with two waves of execution. Coordinator and workers are roles within the job-queue model above, not separate infrastructure.

**Phase 1 — Plan & Probe:** The coordinator LLM takes the research question and produces a structured plan. Each subtopic contains: a title, an information objective (what we need to learn), and source tier preferences. The plan is displayed to the user for approval, along with global source tier settings and a feedback field for regeneration.

**Phase 2 — Parallel Workers:** Each approved subtopic is enqueued as a job. A worker generates search queries from its objective, searches across configured APIs, and evaluates each result through a two-pass process:
- Pass 1 (Flash model): classify relevance and accessibility from the snippet.
- Pass 2 (Pro model): full content evaluation against relevance, credibility, uniqueness, and actionability. If stored, generate the key takeaway.

**Phase 3 — Coordinator Review:** After all subtopic jobs complete, a coordinator job reviews coverage reports and may enqueue a single wave of gap-filling jobs with refined objectives. Research then ends. The chatbot can spawn additional research later.

### Agent Hierarchy

- **Coordinator (DeepSeek V4 Pro):** Generates research plans, reviews worker coverage reports, spawns gap-filling workers, generates reports.
- **Workers (DeepSeek V4 Pro):** Execute subtopic research: query generation, final source evaluation, takeaway generation. Limited to 100K token context window — if exceeded, the remaining work is enqueued as a fresh continuation job (handoff).
- **Classification (DeepSeek Flash):** Source relevance filtering, source tier classification, accessibility checks. Runs at high volume on search result snippets.

All LLM calls go through LangChain's OpenAI-compatible interface to stay model-agnostic, and every LLM call is traced in LangSmith.

### What Uses an LLM vs. What Does Not

A clean split keeps cost predictable and LangSmith traces meaningful — only genuinely "intelligent" steps incur tokens or appear in traces.

| Uses an LLM (traced in LangSmith) | Deterministic plumbing (no LLM, not traced) |
|---|---|
| Plan / subtopic generation (coordinator) | Web & academic search API calls |
| Search query generation | Content extraction (trafilatura / Jina) |
| Pass-1 relevance & accessibility classification | Fixed-size chunking (~500 tok / ~100 overlap) |
| Pass-2 four-dimension source scoring | Embedding generation (a model call, but deterministic — not agentic) |
| Key-takeaway generation | Vector + keyword (hybrid) search |
| Coverage / gap analysis | URL deduplication, storage writes |
| RAG answer synthesis + confidence assessment | Project isolation / RLS enforcement |
| Report synthesis / auto-draft curation | Job claim/heartbeat/status transitions, budget enforcement, cancellation, Realtime event emission |

### Source Evaluation

Each source is scored 1-5 on four dimensions: relevance, credibility, uniqueness, actionability. Store if average ≥ 3 and no dimension scores 1. The "no 1s" rule ensures paywalled or low-credibility sources are always excluded.

Uniqueness is evaluated against key takeaways from already-stored sources for that subtopic, not full text, to keep context windows manageable.

### Search & Content Fetching

Multi-source search with tier routing:
- Academic sources: Semantic Scholar API (free, metadata + abstracts + open-access PDF links).
- Web/general sources: Brave Search API or Tavily.
- Content extraction: trafilatura (primary, free), Jina Reader API (fallback, free tier).

API failures are handled with exponential backoff retry, then graceful degradation (switch APIs), then surfaced to the user with a retry option. Failures and retries are recorded on the job row so they survive worker restarts.

### Data Model

Supabase database with row-level security enforcing project isolation. Core tables:
- `projects` — project metadata, research question, status, source tier settings, owner.
- `subtopics` — plan subtopics with objectives, source tier preferences, status.
- `sources` — stored sources with full text, scores, key takeaway, URL, source tier.
- `source_subtopics` — many-to-many junction between sources and subtopics (enables URL-based dedup).
- `source_chunks` — fixed-size text chunks (~500 tokens, ~100 overlap) with pgvector embeddings.
- `chat_messages` — per-project chat history with inline citation metadata.
- `reports` — generated markdown reports with references to source IDs.
- `jobs` — the work queue (see Database-Backed Job Queue). Drives all agent execution and is the recoverable record of in-flight work.
- `worker_activity` — one row per subtopic capturing the latest human-readable activity (e.g. "reading example.com", "stored 4 sources"), so live progress is recoverable on re-mount.

Project isolation: every query filters by `project_id`. This is enforced at the data access layer and by RLS, never delegated to the LLM.

### Chunking & Vectorization

Fixed-size chunking: ~500 token chunks with ~100 token overlap. Full text stored separately. Embeddings via OpenAI `text-embedding-3-small` (1536 dimensions). RAG retrieval uses hybrid search: pgvector cosine similarity combined with keyword/full-text search.

### RAG Chatbot

Hybrid vector + keyword search retrieves relevant chunks. The LLM synthesizes an answer with inline citations. If confidence is low, the chatbot offers to spawn new research, which simply enqueues a subtopic job — the chatbot is just a different UI entry point into the same worker pipeline. Chat history persists in `chat_messages`.

### Report Synthesis

Curated collection flow: the user browses sources by subtopic, selects up to 25, optionally provides instructions (tone, audience, focus), and generates a markdown report. Auto-draft option: the LLM first reviews all key takeaways to select the top 25, then synthesizes the report. Report generation runs as a job (async, not streamed). Output is markdown rendered for preview, downloadable as `.md` or PDF.

### Real-Time Progress

Live progress is delivered via **Supabase Realtime** WebSocket subscriptions — the browser subscribes directly to database table changes, which makes "the database is the source of truth" automatic. The project layout maintains a persistent channel per project, subscribing to changes on `projects`, `subtopics`, `sources`, `source_subtopics`, `jobs`, and `worker_activity`. Tab navigation does not interrupt the subscription; unmounting unsubscribes and remounting re-reads current state (REST) before re-subscribing, so no event gap can leave the UI stale.

There is no separate SSE/Redis event stream. Workers do not publish events to a broker — they write rows, and Supabase Realtime propagates the change. Polling a REST status endpoint is the fallback if a Realtime subscription drops.

### Tech Stack

- **Frontend / data & mutations:** React (Next.js) with Supabase auth. Reads go through the `@supabase/ssr` server client (RLS-enforced, so the read row shape matches the Realtime delta shape); CRUD, the status state machine, and job-enqueue run as Next.js **Server Actions** against Supabase (RLS + `SECURITY DEFINER` RPCs). Deployed as a Render Web Service. **No standalone API service** — Postgres is the single source of truth. *(Supersedes the prior FastAPI service — see `decisions.md`.)*
- **Worker:** Python async polling loop (`worker.py`) — **the only backend service and the agent orchestrator.** Deployed as a Render Background Worker. Claims and runs jobs (asyncio + `SKIP LOCKED`); writes all progress to Supabase.
- **Async model:** Database-backed job queue (Postgres `FOR UPDATE SKIP LOCKED`) + `asyncio` concurrency. **No Celery, no Redis.**
- **Database:** Supabase (PostgreSQL + pgvector + Realtime + Auth), managed.
- **Auth:** Supabase Auth.
- **LLM Orchestration:** LangChain (model-agnostic, OpenAI-compatible interface).
- **Observability:** LangSmith on every LLM call.
- **Models:** DeepSeek V4 Pro (`deepseek-v4-pro`) for coordinator/workers, DeepSeek V4 Flash (`deepseek-v4-flash`) for classification, OpenAI `text-embedding-3-small` (embeddings). Both DeepSeek models expose a **1M-token context window** and three reasoning-effort modes (low/med/max). Do not use the legacy `deepseek-chat` / `deepseek-reasoner` aliases — deprecated 2026-07-24.
- **Search:** Brave Search API or Tavily, Semantic Scholar API.
- **Content Extraction:** trafilatura, Jina Reader API.
- **Hosting:** **Render** for the frontend (Web Service) and worker (Background Worker); **Supabase** managed for database/auth/realtime.

### Multi-User & Sharing

Each user has their own projects via Supabase Auth. Projects can be shared with other users as viewers or collaborators via a simple invite mechanism. RLS enforces access at the database layer.

### Cancellation & Error Handling

Users can cancel an entire running project. Cancellation sets project status to `cancelled` and marks the project's `queued`/`running` jobs as `cancelled`; the worker checks for cancellation at each checkpoint and stops cleanly. Stored sources are preserved. Failed API calls retry with exponential backoff, degrade gracefully, and ultimately surface a retry option to the user. Job state (`attempts`, `status`, checkpoint in `payload`) is persisted so retries resume from where they left off and survive worker restarts.

### Budget Guardrails

- Search budget: 3-5 queries per subtopic, top 5 results each (25 candidates max).
- Source cap per subtopic: 12 maximum, 3 minimum target.
- Context window: 100K token **self-imposed** ceiling for cost/quality control (the model itself supports 1M — this cap is a budget guardrail, not a model limit); a worker enqueues a fresh continuation job when exceeded (handoff). The ceiling is a tunable constant, not a hard-coded assumption.
- Concurrency cap: an `asyncio` semaphore bounds simultaneously-running agents per worker instance.
- Report cap: 25 sources maximum.
- Two-wave maximum for gap-filling (research ends after wave 2).
- No hard monthly budget cap needed — projected cost is under $20/month at 1 project/week.

## Testing Decisions

### What Makes a Good Test

Tests verify external behavior, not implementation details. They test: given these inputs, does the module produce the expected outputs? Tests do not assert on internal prompts, chain structures, or implementation-specific details that would break during refactoring.

### Modules Tested

All modules except the UI receive automated tests:
- **auth:** Session creation, `proxy.ts` route protection, RLS-based access enforcement.
- **projects:** CRUD operations, status transitions, `project_id` isolation enforcement.
- **queue:** Job claim under contention (`SKIP LOCKED` correctness), heartbeat updates, stale-job reclaim by the watchdog, cancellation propagation, idempotent resume from checkpoint.
- **planner:** Plan generation from question, regeneration from feedback, source tier merging.
- **workers:** Search query generation, evaluation pipeline, takeaway generation, context window handoff (continuation-job enqueue), auto-retry with different angles, "why nothing" report generation.
- **search:** API routing by source tier, content extraction fallback chain, retry with backoff, graceful degradation.
- **storage:** Chunking correctness, embedding dimensions, vector similarity search, hybrid search, URL dedup, `project_id` filtering.
- **chat:** Retrieval pipeline, citation formatting, confidence assessment, research-spawning logic.
- **reports:** Source selection cap enforcement, markdown generation with citations, auto-draft curation.

### Test Approach

Unit tests for pure logic (chunking, scoring, dedup). Integration tests for database operations (vector search, project isolation, CRUD, job-queue claim/heartbeat/reclaim). Mocked external APIs for LLM calls, search APIs, and content extraction. Contract tests for job `payload` schemas and `worker_activity` row shapes.

## Out of Scope

- Per-subtopic source tier editing (global only for v1).
- Guided outline report builder.
- Team-based multi-tenancy.
- Pause/resume for individual workers (project-level cancel only).
- Content-hash deduplication (URL-based only for v1).
- Cross-project search or analysis.
- Semantic chunking or hierarchical chunking (fixed-size only for v1).
- Custom embedding models.
- Public sharing links (user-to-user invite only for v1).
- Direct inline editing of the research plan (feedback-based regeneration only for v1).
- Streaming report generation (report is generated async, not streamed).
- Distributed task brokers (Celery/Redis) — explicitly replaced by the database-backed queue.

## Module Development Order

The build is front-loaded with a navigable, QA-able UI shell so the experience can be evaluated from day one, then proceeds bottom-up: infrastructure, data primitives, intelligence, then the remaining user-facing features.

### Phase 0: Navigable Frontend Shell (QA from the jump)
- Next.js scaffold with the full navigation structure: auth screens, project dashboard, and the project shell with all tabs (Plan / Research / Sources / Chat / Report).
- All routes render and are navigable against mocked/placeholder data — no backend required yet.
- Design system from `DESIGN.md` applied (cream canvas, coral CTAs, Copernicus/StyreneB type, alternating surface rhythm).
- Goal: a clickable product to QA navigation and look-and-feel immediately. State persistence is proven in later phases once the backend exists.
- **Depends on:** nothing.
- **Unblocks:** every UI feature can be wired into a real shell instead of built blind.

### Phase 1: Infrastructure & Auth
- Supabase project provisioning, database schema (including `jobs` and `worker_activity`), pgvector extension, RLS policies.
- Supabase Auth integration (signup, login, session management via `proxy.ts`); wire real auth into the Phase 0 shell.
- Worker scaffold (`worker.py`): the polling loop, `SKIP LOCKED` claim, heartbeat, and watchdog — built and tested early since the whole pipeline depends on it.
- Render deployment of the frontend (Web Service) and worker (Background Worker).
- **Depends on:** Phase 0 (shell to wire into).
- **Unblocks:** everything.

### Phase 2: Projects Module
- Project CRUD (create, read, update, delete).
- `project_id` isolation enforcement at the data access layer and via RLS.
- Status state machine (draft → planning → researching → complete / cancelled).
- Source tier preference storage (global, per-project).
- First real persistence milestone: create a project, navigate away, return — state intact (validates the two-plane model end-to-end).
- **Depends on:** Phase 1 (auth, database).
- **Unblocks:** planner, dashboard.

### Phase 3: Search Infrastructure
- Brave Search / Tavily API client with exponential backoff retry.
- Semantic Scholar API client.
- Content extraction: trafilatura (primary) → Jina Reader API (fallback).
- Source tier routing (academic → Semantic Scholar, web → Brave/Tavily).
- Graceful degradation when APIs fail.
- **Depends on:** Phase 1 (no project dependency — pure API clients).
- **Unblocks:** workers.

### Phase 4: Storage & Embeddings
- Fixed-size chunking (~500 tokens, ~100 overlap).
- OpenAI `text-embedding-3-small` integration.
- pgvector storage and cosine similarity search.
- Hybrid search (vector + keyword/full-text).
- URL-based deduplication (same URL across subtopics → linked, not duplicated).
- Full-text storage separate from chunks.
- **Depends on:** Phase 1 (database, pgvector).
- **Unblocks:** workers, chat.

### Phase 5: Planner Module
- LLM plan generation from research question (coordinator prompt).
- Plan regeneration from user feedback.
- Source tier merging (global defaults + per-project overrides).
- Plan serialization to `subtopics` table.
- **Depends on:** Phase 2 (projects), LLM orchestration (LangChain).
- **Unblocks:** workers.

### Phase 6: Worker Pipeline
- Subtopic job enqueue on plan approval.
- Search query generation from subtopic objectives.
- Two-pass evaluation: Flash (relevance/accessibility) → Pro (full scoring).
- Four-dimension scoring (relevance, credibility, uniqueness, actionability) with "no 1s" rule.
- Key takeaway generation (1-2 sentences per stored source).
- Context window monitoring and worker handoff (continuation-job enqueue) at the 100K token ceiling.
- Auto-retry with different search angles on empty results.
- "Why nothing" report generation for barren subtopics.
- Source cap enforcement (12 max, 3 min target per subtopic).
- Checkpointing to the job row for idempotent resume.
- **Depends on:** Phase 1 (queue), Phase 3 (search), Phase 4 (storage), Phase 5 (planner).
- **Unblocks:** coordinator review, real-time progress, chat (spawning).

### Phase 7: Real-Time Progress
- `worker_activity` writes from the worker pipeline (worker started, reading source, source stored with takeaway, worker complete, worker failed).
- Supabase Realtime subscriptions in the project layout; persistent channel per project.
- Frontend progress display component, wired into the Phase 0 Research tab.
- Re-mount reconciliation (REST read before re-subscribe).
- **Depends on:** Phase 6 (workers emit activity).
- **Unblocks:** (polish layer).

### Phase 8: Coordinator Review
- Post-worker coverage analysis (comparing findings against objectives).
- Single wave of gap-filling jobs with refined objectives.
- Research completion logic (mark project complete after wave 2).
- **Depends on:** Phase 6 (worker pipeline).
- **Unblocks:** (terminal phase of research).

### Phase 9: RAG Chatbot
- Retrieval pipeline: hybrid search → chunk fetch → LLM synthesis.
- Inline citation formatting (source links in responses).
- Confidence assessment (low confidence → offer to spawn research).
- Research spawning from chat (creates new subtopic, enqueues a job).
- Chat history persistence in `chat_messages`.
- **Depends on:** Phase 4 (storage/embeddings), Phase 6 (worker spawning).
- **Unblocks:** (none).

### Phase 10: Reports
- Source browser UI (by subtopic, with key takeaways).
- Source selection for report (user-curated, 25 max).
- Auto-draft mode (LLM selects top 25 from all key takeaways).
- Markdown report generation with inline citations (runs as a job).
- Report preview (rendered markdown).
- PDF and Markdown download.
- **Depends on:** Phase 4 (storage), Phase 6 (sources exist).
- **Unblocks:** (none).

### Phase 11: Dashboard & Sharing
- Project dashboard (list all projects with status, last updated).
- Project sharing via user invitation (viewer / collaborator roles).
- Multi-project navigation.
- **Depends on:** Phase 2 (projects), Phase 1 (auth).
- **Unblocks:** (polish layer).

### Rationale

Phase 0 exists so there is something navigable to QA from the very first day, and so every later UI feature is wired into a real shell rather than built blind. The job queue and worker loop are built in Phase 1 (not deferred) because the entire pipeline's durability rests on them — `SKIP LOCKED` claiming, heartbeats, and the self-healing watchdog are foundational, not polish. Search (Phase 3) and Storage (Phase 4) precede Workers (Phase 6) because workers need both. Planner (Phase 5) precedes workers — the plan defines what workers execute. The RAG Chatbot (Phase 9) follows Workers so "spawn research from chat" reuses the worker pipeline end-to-end. Real-Time Progress (Phase 7) can be built in parallel with Coordinator Review (Phase 8).

## Further Notes

- This is a greenfield v2 with no existing codebase constraints.
- The project is intended as a portfolio piece for AI engineer positions — architecture decisions should favor clarity, observability, and demonstrating understanding of multi-agent tradeoffs. The database-backed queue is a deliberate "right-sized" choice over Celery/Redis and should be presented as such.
- DeepSeek V4 is the target model family for v1 (`deepseek-v4-pro` for reasoning, `deepseek-v4-flash` for high-volume classification), but all LLM calls go through LangChain with the OpenAI-compatible interface to remain model-agnostic.
- LangSmith must be enabled on every LLM call for full observability of the agent pipeline.
- Context window management is critical: the token ceiling and worker handoff (continuation-job) mechanism should be built and tested early, as it's foundational to cost control and output quality.
- The browser must never run or hold agent work. It only triggers (via API) and projects (via Realtime). This invariant is what makes navigation safe.
