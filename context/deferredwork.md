# Deferred Work

Things to be implemented later, deferred in favor of a working prototype, or that require the user to supply something (API keys, accounts, secrets). Alert the user whenever an item is added here.

## Manual Supabase dashboard config (user must do — code is ready, these make it take effect)

Added 2026-06-01 alongside the `/auth/confirm` server-side email-confirmation handler. The route + `emailRedirectTo` wiring are in code, but Supabase's hosted-project settings (which `supabase/config.toml` does **not** control — that file only governs the local CLI stack) must be set in the dashboard:

1. **Authentication → URL Configuration → Site URL** → set to the Render URL (e.g. `https://<app>.onrender.com`). This is what made confirmation links point at `localhost:3000`.
2. **Authentication → URL Configuration → Redirect URLs** → add `https://<app>.onrender.com/**` and `http://localhost:3000/**` (so dev still works). `emailRedirectTo` must match an allow-listed pattern.
3. **Authentication → Emails → "Confirm signup" template** → change the link to the token-hash form so our handler is hit and the session is set server-side:
   ```html
   <a href="{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email&next=/dashboard">Confirm your email</a>
   ```
   (Default template uses `{{ .ConfirmationURL }}`, which routes through Supabase's implicit-flow verify endpoint and does **not** establish the cookie-based server session.)

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
| Report generation | **UI disabled** — Generate button locked; Callout shown | Connect coordinator agent (Phase 10) to re-enable |
| Report download | **Live** — Download .md functional for any real `reports` row | |

## Font substitution (pre-acknowledged in DESIGN.md)

Copernicus (display serif) and StyreneB (humanist sans) are licensed Anthropic typefaces unavailable as public web fonts. Phase 0 uses:
- **Cormorant Garamond** (weight 400/500/600) as the closest open-source serif substitute
- **Inter** (variable) as the StyreneB substitute

These are not a bug — they are pre-acknowledged Known Gaps in `DESIGN.md`. Replace with licensed fonts if they become available.

## PDF export (Report tab)

The Report tab's "Download .md" button is wired client-side. PDF export is stubbed/disabled — listed as a later-phase feature. Implement in Phase 10 using a server-side PDF generation library (e.g. Puppeteer, @react-pdf/renderer, or a headless Chrome endpoint on Render).

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

### Phase 6 deferred wiring

- `approvePlan` Server Action transitions status to `"researching"` but does NOT enqueue `research_subtopic` jobs — there is no handler for that job type yet. Phase 6 will add the handler and wire `approvePlan` to enqueue one job per subtopic.
- `social_media` tier is stored and displayed but has no search router entry yet. Phase 6 will route it to a web/Reddit provider.

## Open questions to resolve

- _(resolved 2026-05-29)_ ~~DeepSeek "V4 Pro" / "Flash" model IDs~~ — confirmed real: `deepseek-v4-pro` and `deepseek-v4-flash`, both 1M-token context. The 100K handoff ceiling is a self-imposed cost/quality cap, not a model limit.
