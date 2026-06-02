# Phase 9 — RAG Chatbot

## Context

When Phase 10 (Reports) was pulled ahead of schedule (decisions.md, 2026-06-01), Phase 9 (RAG Chatbot) became the remaining gap. Every dependency is now in place: stored sources with embeddings (Phase 4/6), the `match_chunks()` hybrid-search SQL function (migration 0008), the worker job-queue + handler pattern (Phase 1/6/8/10), and the chat UI shell + `ChatMessage`/`Citation` types (Phase 0). Today the Chat tab renders message history but the composer is disabled with a "coming soon" callout.

This phase makes the Chat tab live: a user asks a question, the worker retrieves relevant chunks from *this project's* corpus, synthesizes a cited answer, and — when it can't answer confidently — offers a one-click button to spawn new research that grows the corpus. This is the last research-pipeline user story (PRD user stories 14–17).

**Confirmed design decisions (this session):**
- **Delivery:** Async job + Realtime, no streaming. Enqueue a `chat_respond` job → worker writes the assistant `chat_messages` row → Realtime pushes it to the open tab. This is the committed architecture (decisions.md "Eliminate FastAPI").
- **Spawn research:** User-confirmed button on low-confidence answers (not auto-spawn). Clicking creates one new subtopic + enqueues a `research_subtopic` job.

## Architecture flow

```
User types → Server Action sendChatMessage():
  1. INSERT user chat_messages row (role=user)
  2. INSERT jobs row (type=chat_respond, payload={project_id, question})
Realtime (chat_messages INSERT) → user message appears immediately
Worker claims chat_respond job → chat handler:
  1. Embed question (Embedder)
  2. match_chunks(project_id, embedding, question)  ← RLS-bypassing direct conn, project-scoped
  3. Load parent source rows (title/url) for cited chunks
  4. invoke_structured(ChatAnswer) → {answer_markdown, cited_source_ids, confidence}
  5. Build citations [{sourceId, sourceTitle, url}] from cited_source_ids
  6. INSERT assistant chat_messages row (role=assistant, content, citations, confidence)
Realtime (chat_messages INSERT) → assistant message appears
If confidence == "low": assistant message UI shows "Research this" button
  → Server Action spawnResearchFromChat() creates subtopic + research_subtopic job
```

The worker bypasses RLS via its direct asyncpg connection, so it calls `match_chunks` directly — no authenticated SQL wrapper needed (Decision 2026-05-31 Phase 4+5 #2 deferred that wrapper "to Phase 9"; the job-based path means we never need it).

## Backend (build first, per CLAUDE.md)

### 1. Migration `supabase/migrations/0013_chat_realtime.sql`
```sql
alter publication supabase_realtime add table chat_messages;
alter table chat_messages add column confidence text;  -- nullable; 'high'|'medium'|'low' on assistant rows
```
`chat_messages` is currently absent from the Realtime publication (only 0002/0003/0012 added tables). Without this, INSERT events never reach the tab. The `confidence` column lets the projection plane decide whether to render the spawn button.

### 2. LLM schema — `worker/worker/llm/schemas.py`
Add a `ChatAnswer` Pydantic model in the report-schemas section:
```python
class ChatAnswer(BaseModel):
    answer_markdown: str
    cited_source_ids: list[str]          # subset of the source IDs provided in context
    confidence: Literal["high", "medium", "low"]
```
Follows the existing `ReportDraft` pattern (markdown + id-subset). The handler validates `cited_source_ids ⊆ provided set` (drop hallucinated IDs) exactly like `report.py` does.

### 3. Shared payload contract — `shared/schemas/job_payloads.py`
Add `ChatRespondPayload(project_id: str, question: str, progress: str | None = None)` and register `"chat_respond"` in `JOB_PAYLOAD_MODELS`. Mirror the existing payload models.

### 4. Chat handler — `worker/worker/handlers/chat.py` (new)
Model the structure on `handlers/report.py`. `handle(ctx)`:
- Parse payload; early `ctx.is_cancelled()` guard before the LLM call (as report/research do).
- Embed the question via `Embedder` (reuse from `worker/worker/storage/embeddings.py`).
- `async with pool.acquire() as conn:` call `match_chunks(conn, project_id=..., query_embedding=..., query_text=question, match_count=CHAT_MATCH_COUNT)` (from `storage/search.py`).
- If zero chunks: write an assistant message stating the corpus has nothing relevant, `confidence="low"` → still emits the spawn affordance. (Deterministic empty-corpus message, no LLM call.)
- Load parent `sources` rows (`id, title, url, key_takeaway`) for the distinct `source_id`s in the matches, scoped to `project_id` (isolation).
- Build the synthesis prompt: question + numbered source blocks (`[ID:<uuid>] Title / URL / chunk content`, chunk truncated to `CHAT_CHUNK_CHARS`). System prompt instructs: answer ONLY from provided sources, cite inline as markdown links `[Title](URL)`, set `confidence`, return `cited_source_ids`. Include the explicit JSON-schema hint line (DeepSeek json_mode requirement — same fix as report/coordinator, see log.md 2026-06-02).
- `invoke_structured(llm, ChatAnswer, messages, "chat_answer")` with `build_chat_model(cfg, "coordinator", tags=["chat", f"project:{project_id}"])`.
- Validate `cited_source_ids ⊆ provided`; build `citations` list as `[{"sourceId": id, "sourceTitle": title, "url": url}]` — **camelCase keys**, because `mapChatMessage` in `web/src/lib/data/client.ts` passes `row.citations` through verbatim into the `Citation` TS type.
- INSERT assistant `chat_messages` row (`role='assistant'`, `content=answer_markdown`, `citations=<jsonb>`, `confidence=...`). The jsonb codec (db.py) lets us pass the Python list directly.
- Post-LLM cancellation guard before the INSERT (report.py pattern).

Register in `worker/worker/handlers/__init__.py`: `"chat_respond": chat_handle`.

### 5. Config — `worker/config.toml` + `worker/worker/config.py`
Add a `[chat]` section: `chat_match_count = 12` (chunks retrieved), `chat_chunk_chars = 1500` (per-chunk truncation in the prompt). Export `CHAT_MATCH_COUNT`, `CHAT_CHUNK_CHARS` from `config.py`, mirroring the `[report]` → `REPORT_SOURCE_CAP` wiring. Avoids hard-coding (CLAUDE.md modularity rule).

### 6. Tests — `worker/tests/test_chat.py` (new) + `test_contract.py`
- `test_chat.py` (mocked LLM + Embedder + `match_chunks` + DB, mirroring `test_report.py`): cited-IDs subset validation drops hallucinations; citations shape correctness (`sourceId/sourceTitle/url`); project isolation (only this project's chunks/sources used); empty-corpus path writes a low-confidence message without crashing; pre-LLM and post-LLM cancellation guards.
- `test_contract.py`: add `ChatRespondPayload` round-trip tests (follow the existing `GenerateReportPayload` tests).

## Frontend (wire up after backend)

### 7. Chat Server Actions — `web/src/app/(app)/project/[id]/chat/actions.ts` (new)
Two `"use server"` actions, following `report/actions.ts` (auth check → insert → `revalidatePath`):
- `sendChatMessage(projectId, question)`: insert the user `chat_messages` row (role=user, empty citations), then insert the `chat_respond` job. RLS `chat_messages_insert` (`can_write_project`) gates the user row; `jobs_insert` gates the job.
- `spawnResearchFromChat(projectId, question)`: insert one `subtopics` row (title/objective derived from the question; `wave` set to a value the Phase-8 coordinator barrier ignores — see Risks) + insert a `research_subtopic` job. Reuses the exact enqueue shape from `approvePlan` in `project/actions.ts`.

### 8. Chat Realtime — `web/src/components/features/realtime/ChatRealtime.tsx` (new)
Clone `ReportRealtime.tsx`: subscribe to `chat_messages` INSERT filtered by `project_id=eq.${projectId}`, call `router.refresh()`. Mount it in `chat/page.tsx` alongside `<ChatTab>` (mirrors how `report/page.tsx` mounts `<ReportRealtime>`).

### 9. Activate the composer — `web/src/components/features/chat/ChatTab.tsx`
- Remove the "Chat coming soon" `Callout` and the disabled input/Send block.
- Add a real composer: controlled input + Send button calling `sendChatMessage`. Use `useTransition`/`useActionState` for the pending state; show an assistant "typing…" affordance while a `chat_respond` job is in flight (e.g., when the last message is from the user). Optimistically clear the input on submit; the user message arrives via Realtime (or use `useOptimistic` for instant echo).
- Reference DESIGN.md for the composer styling (coral CTA, hairline border, cream canvas) — the disabled markup already encodes the intended layout; re-enable it.

### 10. Spawn button + confidence wiring — `web/src/components/features/chat/ChatMessage.tsx`
- Thread the new `confidence` field through `web/src/lib/data/types.ts` (`ChatMessage.confidence?: "high"|"medium"|"low"`) and `mapChatMessage` in `client.ts`.
- For assistant messages with `confidence === "low"`, render a "Research this" button (DESIGN.md `secondary`/`text` Button) that calls `spawnResearchFromChat`.

## Files to touch
- New: `supabase/migrations/0013_chat_realtime.sql`, `worker/worker/handlers/chat.py`, `worker/tests/test_chat.py`, `web/src/app/(app)/project/[id]/chat/actions.ts`, `web/src/components/features/realtime/ChatRealtime.tsx`
- Edit: `worker/worker/llm/schemas.py`, `shared/schemas/job_payloads.py`, `worker/worker/handlers/__init__.py`, `worker/config.toml`, `worker/worker/config.py`, `worker/tests/test_contract.py`, `web/src/components/features/chat/ChatTab.tsx`, `web/src/components/features/chat/ChatMessage.tsx`, `web/src/app/(app)/project/[id]/chat/page.tsx`, `web/src/lib/data/types.ts`, `web/src/lib/data/client.ts`
- Docs (per CLAUDE.md): `context/log.md` (always), `context/decisions.md` (chat-as-job + confidence-column decisions), `context/map.md` (new files)

## Risks / must-handle

- **Coordinator barrier re-trigger.** A chat-spawned `research_subtopic` completing on a `complete` project could let the Phase-8 sweep (`enqueue_ready_coordinator_reviews`) fire an unwanted coordinator review. Mitigation: give chat-spawned subtopics a `wave` value outside the barrier's range (it caps at wave 2) — e.g. a dedicated sentinel — OR confirm the barrier RPC already guards on `project.status = 'researching'`. **Verify the barrier's guard in `migrations/0011` before implementing** so chat spawn stays fire-and-forget (adds sources, no review, no status flip).
- **Citations key contract.** Worker must emit `sourceId/sourceTitle/url` (camelCase) since `mapChatMessage` does no key remapping. Covered by a test.
- **DeepSeek json_mode.** New chat prompt must contain the word "json" / a schema hint (the `_ensure_json_keyword` safety net covers it, but include the explicit hint as report/coordinator do).

## Verification (end-to-end)

1. **Migrations:** `supabase db reset` (or apply 0013) so `chat_messages` joins the Realtime publication and the `confidence` column exists.
2. **Worker tests:** `cd worker && uv run pytest tests/test_chat.py tests/test_contract.py -v` — all pass.
3. **Live smoke (DESIGN.md surfaces):** run the worker (`python -m worker.main`) + `cd web && npm run dev`. Open a project with stored sources → Chat tab. Ask a question answerable from the corpus → assistant reply with inline citation chips appears via Realtime within a few seconds (no refresh). Verify the cited links resolve to real stored sources.
4. **Isolation:** ask the same question in a second project with a different corpus → answers never reference project 1's sources.
5. **Spawn flow:** ask something the corpus can't answer → low-confidence reply renders "Research this" → click → a new subtopic appears and a `research_subtopic` job runs (watch the Research tab); confirm no spurious `coordinator_review` job is enqueued.
6. **Two-plane durability:** submit a question, immediately switch tabs / refresh → the assistant reply still arrives (work ran server-side, Realtime reconciles on re-mount).
