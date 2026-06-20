# Deferred Work

Things to be implemented later, deferred in favor of a working prototype, or that require the user to supply something (API keys, accounts, secrets). Alert the user whenever an item is added here.

## Major Feature #4 — Failed report job leaves "Generating…" indicator stuck (added 2026-06-19)

After a `generate_report` job fails, `getActiveReportJob` returns `false` only after a manual page refresh (the job row moves to `failed` status but there is no Realtime event to clear the indicator). The `ReportRealtime` component only subscribes to `reports` INSERT events, not `jobs` status changes. Acceptable for now; a fix would subscribe to `jobs` UPDATE events and call `router.refresh()` on `status = 'failed'`.

---

## Bug #3 fix — user action required: replace LangSmith API key on Render (added 2026-06-02)

The worker logs confirmed `403 Forbidden` on every trace upload — the API key is revoked, rotated, or belongs to a different workspace than the `ytres` project you're watching.

**Steps:**
1. Open the LangSmith workspace that owns (or should own) the `ytres` project.
   - Confirm the URL: `smith.langchain.com` = US; `eu.smith.langchain.com` = EU.
2. Go to **Settings → API Keys → Create new key** (Personal Access Token `lsv2_pt_…` or Service key with trace-write permission).
3. In **Render → ytres-worker → Environment**:
   - Set `LANGCHAIN_API_KEY` to the new key — **no quotes, no trailing spaces**.
   - If the workspace is EU, also add `LANGCHAIN_ENDPOINT=https://eu.api.smith.langchain.com`.
4. **Redeploy** the worker. The startup log should now show `LangSmith OK — project=ytres …` instead of the `auth FAILED (403)` error.

The code changes (configurable endpoint, `check_langsmith()` probe, `flush_traces()` on shutdown) are already deployed.

---

## Manual Supabase dashboard config (user must do — code is ready, these make it take effect)

Added 2026-06-01 alongside the `/auth/confirm` server-side email-confirmation handler. The route + `emailRedirectTo` wiring are in code, but Supabase's hosted-project settings (which `supabase/config.toml` does **not** control — that file only governs the local CLI stack) must be set in the dashboard:

1. **Authentication → URL Configuration → Site URL** → set to the Render URL (e.g. `https://<app>.onrender.com`). This is what made confirmation links point at `localhost:3000`.
2. **Authentication → URL Configuration → Redirect URLs** → add `https://<app>.onrender.com/**` and `http://localhost:3000/**` (so dev still works). `emailRedirectTo` must match an allow-listed pattern.
3. **Authentication → Emails → "Confirm signup" template** → change the link to the token-hash form so our handler is hit and the session is set server-side:
   ```html
   <a href="{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email&next=/dashboard">Confirm your email</a>
   ```
   (Default template uses `{{ .ConfirmationURL }}`, which routes through Supabase's implicit-flow verify endpoint and does **not** establish the cookie-based server session.)

## Migration 0010 applied directly to prod (sync the CLI tracker when convenient)

`supabase/migrations/0010_fix_projects_select_returning.sql` (bug #1 fix) was applied **directly to the live Supabase DB** over the `SUPABASE_DB_URL` connection, not via `supabase db push` (the CLI isn't linked locally). The statements are idempotent (`drop policy if exists …; create policy …`), so a later `supabase db push` is safe and just records it in the migration tracker; fresh environments pick it up automatically. No action required unless you rely on `supabase migration list` being in sync — if so, run `supabase db push` once.

## API Keys / Environment Variables needed (user must provide)

These are required before the corresponding phase can run for real. None are wired yet (Phase 0 is mocked data only).

| Env var (proposed) | Service | Needed by phase | Notes |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase | Phase 1 | Public project URL + anon key (browser-safe). |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Supabase | Phase 1 | Server-only. Service-role key is used by **Next.js Server Actions** (the rare privileged op) and the worker — never exposed to the browser. |
| `SUPABASE_DB_URL` | Supabase | Phase 1 | **New.** Direct Postgres connection string for the worker's `asyncpg` pool. |
| `DEEPSEEK_API_KEY` | DeepSeek (coordinator/workers/classification) | Phase 5 | Used via LangChain's OpenAI-compatible interface. Model IDs confirmed: `deepseek-v4-pro` (reasoning) and `deepseek-v4-flash` (classification), both 1M-token context. Avoid the deprecated `deepseek-chat`/`deepseek-reasoner` aliases (EOL 2026-07-24). |
| `OPENAI_API_KEY` | OpenAI `text-embedding-3-small` | Phase 4 | Embeddings only. |
| `BRAVE_SEARCH_API_KEY` *or* `TAVILY_API_KEY` | Brave Search or Tavily | Phase 3 | Pick one web-search provider. The correct env var name is **`BRAVE_SEARCH_API_KEY`** (not `BRAVE_API_KEY`). Semantic Scholar needs no key. |
| `JINA_API_KEY` | Jina Reader API | Phase 3 | Fallback content extractor; free tier. trafilatura (primary) needs no key. |
| `LANGSMITH_API_KEY` (+ `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_PROJECT`) | LangSmith | Phase 5 | Tracing on every LLM call. |
| Render account + service config | Render | Phase 1 (deploy) | Frontend as a Web Service, worker as a Background Worker. **No API service** (FastAPI eliminated — see `decisions.md`). |

## Dummy / placeholder data in use

`fixtures.ts` has been deleted. All `client.ts` read functions now query live Supabase. Tables start empty; data is created by the user via the create-project flow and by the worker pipeline. The two disabled UI surfaces are noted below.

| Surface | Status | Notes |
|---|---|---|
| Dashboard project list | **Live** — real Supabase `projects` table | |
| Project header + status | **Live** — real Supabase `projects` table | |
| Plan subtopics | **Live** — real Supabase `subtopics` table | |
| Source tier settings | **Live** — embedded in `projects.source_tier_settings` jsonb | |
| Research worker activity | **Live** — real Supabase `worker_activity` table | |
| Sources by subtopic | **Live** — real Supabase `sources` + `source_subtopics` join | |
| Chat messages + citations | **Live** reads, **UI disabled** — composer + Send locked; Callout shown | Connect RAG backend (Phase 9) to re-enable |
| Report generation | **Live** — Generate report + Auto-draft wired; Realtime delivers new report row | Requires migration 0012 + `reports` Realtime enabled in Supabase dashboard |
| Report download | **Live** — Download .md functional for any real `reports` row | |

## Font substitution (pre-acknowledged in DESIGN.md)

Copernicus (display serif) and StyreneB (humanist sans) are licensed Anthropic typefaces unavailable as public web fonts. Phase 0 uses:
- **Cormorant Garamond** (weight 400/500/600) as the closest open-source serif substitute
- **Inter** (variable) as the StyreneB substitute

These are not a bug — they are pre-acknowledged Known Gaps in `DESIGN.md`. Replace with licensed fonts if they become available.

## PDF export (Report tab)

The Report tab's "Download .md" button is wired client-side. PDF export is deferred — the server-side renderer (Puppeteer / @react-pdf/renderer / headless Chrome on Render) was out of scope for Phase 10. Implement in a later phase.

## Phase 10 user actions required (added 2026-06-01)

1. **Apply migration 0012** (`0012_report_realtime.sql`) to live Supabase:
   ```
   supabase db push
   ```
   or apply directly over `SUPABASE_DB_URL`:
   ```sql
   alter publication supabase_realtime add table reports;
   ```
   Statement is idempotent — safe to re-apply.

2. **Enable `reports` Realtime in the Supabase dashboard** — go to Database → Replication, verify `reports` appears in the publication. Without this step, generated reports won't appear in the open tab until a manual refresh.

## Phase 1 user actions required (added 2026-05-31)

Before Phase 1 can run end-to-end, the user must:

1. **Create a Supabase project** at supabase.com and copy `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_DB_URL` into `web/.env.local` and `worker/.env`.
2. **Apply migrations** via `supabase db push` (from repo root, after `supabase login`). Or run `supabase start` for local dev then `supabase db push --local`.
3. **Enable the Realtime publication** on the tables listed in `0002_core_tables.sql` and `0003_jobs_and_activity.sql` (the `alter publication supabase_realtime add table …` statements run as part of the migrations, but must be enabled in the Supabase dashboard's Realtime settings if not done automatically).
4. **Create Render services**: one Web Service pointing at `web/` and one Background Worker pointing at `worker/`. Set env vars from `.env.example`.
5. **Run `npm install`** if you see missing-module errors for `@supabase/ssr`, `@supabase/supabase-js`, or `server-only` (these were installed during Phase 1 development but are captured in `package.json`).

## ~~Tailwind token collision — `--spacing-*` vs container scale~~ — RESOLVED 2026-06-01

`web/src/app/globals.css` `@theme` defines named spacing tokens (`--spacing-xs/sm/md/lg/xl/…`) that mirror the DESIGN.md spacing table. In Tailwind v4 these **shadow the built-in container scale** for the matching t-shirt-size keys, so `max-w-sm` → 12px and `max-w-md` → 16px instead of 24rem/28rem — the real cause of bug #1 and the broken dashboard/chat empty states and mobile nav drawer.

**Resolved:** added semantic, non-colliding layout-width tokens (`--container-card` 28rem, `--container-panel` 24rem, `--container-content` 75rem) and switched all affected components to `max-w-card` / `max-w-panel` / `max-w-content`. DESIGN.md and the spacing tokens are unchanged. See `decisions.md` (2026-06-01) for the full rationale and the documented convention (use the semantic width utilities, not the bare `max-w-{sm,md,lg,xl}`).

## Phase 3 user actions required (added 2026-05-31)

Search keys are now read by `worker/worker/config.py` but are all optional — the keyless Semantic Scholar + trafilatura path works without any of them. To use Brave or Tavily, set the correct key in `worker/.env` and in Render's env vars:

- `BRAVE_SEARCH_API_KEY` (not `BRAVE_API_KEY`) for Brave Search
- `TAVILY_API_KEY` for Tavily
- `JINA_API_KEY` for Jina Reader (fallback extractor; free tier)

Set `web_provider = "brave"` or `"tavily"` in `config.toml [search]` to choose the active provider.

## Deploy action required: `SUPABASE_DB_URL` must be the Supabase **Session pooler** URL (not the direct connection)

**Symptom:** worker crashes on Render with `OSError: [Errno 101] Network is unreachable` at `sock.connect()`.

**Cause:** Supabase's **direct** connection host (`db.<project-ref>.supabase.co`) is **IPv6-only**, and Render has **no IPv6 egress**, so the socket connect fails. Unrelated to password encoding (already handled by `_encode_db_url`).

**Fix (operator action, no code change needed):** In Supabase dashboard → **Connect** → **Session pooler**, copy that string and set it as `SUPABASE_DB_URL` on the Render `ytres-worker` service. It must use host `aws-N-<region>.pooler.supabase.com` (IPv4-proxied for free), username `postgres.<project-ref>` (dotted suffix), port `5432` (Session mode — keeps asyncpg prepared statements working). The current live value (pooler host, port 5432) is correct; after changing it, redeploy with **Clear build cache** so a fresh run picks it up.

After redeploy, `worker/worker/db.py` logs `DB host <host>:<port> resolves to: IPv4/IPv6` at startup. If it prints **IPv6 only**, the env var is still the direct host. (Transaction-mode pooler on port `6543` also works — `db.py` auto-disables the statement cache — but Session mode is preferred for the long-lived worker pool.) The paid Supabase **dedicated IPv4 add-on** for the direct connection is an alternative but unnecessary — the pooler does the same job for free.

---

## Pre-Phase-6 action required: `SUPABASE_DB_URL` percent-encoding

The `_encode_db_url()` fix in `worker/worker/config.py` handles the encoding at import time. Before Phase 6 wiring, verify the worker boots cleanly against the real Supabase DB URL by running it locally: `python -m worker.main`. If the URL still breaks asyncpg, manually percent-encode special chars in the password: `@`→`%40`, `?`→`%3F`, `%`→`%25`, `&`→`%26`, `,`→`%2C`.

## Phase 4+5 user actions required (added 2026-05-31)

### API keys — now required to run end-to-end

| Env var | Service | Notes |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek | Coordinator/worker/classifier. Add to `worker/.env` and Render `ytres-worker` env vars. |
| `OPENAI_API_KEY` | OpenAI | `text-embedding-3-small` embeddings. Add to `worker/.env` and Render env vars. |
| `LANGCHAIN_API_KEY` | LangSmith | Tracing on every LLM call (`LANGCHAIN_TRACING_V2=true` already set in config.toml). Add to `worker/.env`. |

### Migrations — apply before testing

```
supabase db push
```

Migrations 0007 (vector indexes), 0008 (match_chunks function), 0009 (social_media enum value) must be applied.

Confirm in Supabase dashboard:
- `source_tier` enum includes `social_media`
- `match_chunks` function exists in the public schema
- Realtime is enabled for `subtopics` and `projects` tables

### ivfflat REINDEX after data

The ivfflat index (migration 0007) trains on data at CREATE time. After substantial source_chunks data exists:
```sql
REINDEX INDEX CONCURRENTLY <index_name>;
```
HNSW is the no-tuning upgrade path for a future migration when scale justifies it.

### ~~Phase 6 deferred wiring~~ — RESOLVED 2026-06-01

- ~~`approvePlan` did not enqueue `research_subtopic` jobs~~ — now enqueues one job per subtopic.
- ~~`social_media` tier had no router entry~~ — now routes to the web provider (`TIER_ROUTING`).

### Phase 6 live-run verification (requires real Supabase + API keys)

Implemented and statically verified. The following require a live stack to confirm end-to-end:
1. **LangSmith tracing** — with `DEEPSEEK_API_KEY` + `LANGCHAIN_API_KEY` set, run the worker and confirm startup log says `tracing: ACTIVE` and a trace appears in the LangSmith `ytres` project.
2. **Full research pipeline** — create a project → approve plan → watch Research tab update live (queued→running→stored counts→complete) without manual refresh.
3. **Sources stored** — verify `sources` and `source_chunks` rows appear with correct scores and embeddings.
4. **Why-nothing report** — trigger on a deliberately barren subtopic; confirm `worker_activity.why_nothing_report` is populated.
5. **Cancel mid-run** — delete the project during research; confirm worker stops and stored sources are preserved until cascade delete.

Add `LANGCHAIN_API_KEY` to `worker/.env` and Render env vars before deploying Phase 6.

## Phase 8 user actions required (added 2026-06-01)

1. **Apply migration 0011** to live Supabase before Phase 8 runs:
   ```
   supabase db push
   ```
   Confirms: `subtopics.wave` column exists, `enqueue_ready_coordinator_reviews()` + `complete_research()` RPCs exist, `jobs_review_wave_uniq` partial index exists.

2. **Barrier/RPC integration tests** (`test_barrier.py`) — verified statically; live run pending (no local Supabase on this machine). Run after migration 0011 is applied.

3. **Coordinator handler tests** (`test_coordinator.py`) — DB-integrated but LLM + `complete_research` are mocked. Run after migration 0011 is applied.

4. **Single gap-fill round enforced by two-wave cap** — lifting to 3+ waves requires incrementing the `rev.next_wave <= 2` guard in the `enqueue_ready_coordinator_reviews()` RPC.

5. **Pre-existing `test_planner.py` `_invoke_structured` mis-patch** — `test_planner.py` patches `planner_module._invoke_structured` (an attribute that doesn't exist; the real function is `invoke_structured` imported bare). The tests pass because `monkeypatch.setattr` on a missing attribute creates it, but the actual production `invoke_structured` is not intercepted — the planner tests make real LLM calls if DEEPSEEK_API_KEY is set, or hit the mock only if the attribute happens to shadow the import. Logged here as a separate pre-existing cleanup item, out of scope for Phase 8.

## Open questions to resolve

- _(resolved 2026-05-29)_ ~~DeepSeek "V4 Pro" / "Flash" model IDs~~ — confirmed real: `deepseek-v4-pro` and `deepseek-v4-flash`, both 1M-token context. The 100K handoff ceiling is a self-imposed cost/quality cap, not a model limit.
