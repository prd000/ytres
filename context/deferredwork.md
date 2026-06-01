# Deferred Work

Things to be implemented later, deferred in favor of a working prototype, or that require the user to supply something (API keys, accounts, secrets). Alert the user whenever an item is added here.

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

Every screen in `ytres/web/` currently renders against mocked fixture data (`src/lib/data/fixtures.ts`). Swap each surface for real data by replacing the corresponding `client.ts` function with a live Supabase/REST call.

| Surface | Mock source | Replace in |
|---|---|---|
| Dashboard project list | `getProjects()` → `PROJECTS` fixture | Phase 2 |
| Project header + status | `getProject(id)` → `PROJECTS` fixture | Phase 2 |
| Plan subtopics | `getSubtopics(projectId)` → `SUBTOPICS` fixture | Phase 5 |
| Source tier settings | embedded in `PROJECTS` fixture | Phase 2 |
| Research worker activity | `getWorkerActivity(projectId)` → `WORKER_ACTIVITY` fixture | Phase 7 |
| Sources by subtopic | `getSources(projectId)` → `SOURCES` fixture | Phase 6 |
| Chat messages + citations | `getChatMessages(projectId)` → `CHAT_MESSAGES` fixture | Phase 9 |
| Report markdown | `getReport(projectId)` → `REPORTS` fixture | Phase 10 |

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

## Phase 3 user actions required (added 2026-05-31)

Search keys are now read by `worker/worker/config.py` but are all optional — the keyless Semantic Scholar + trafilatura path works without any of them. To use Brave or Tavily, set the correct key in `worker/.env` and in Render's env vars:

- `BRAVE_SEARCH_API_KEY` (not `BRAVE_API_KEY`) for Brave Search
- `TAVILY_API_KEY` for Tavily
- `JINA_API_KEY` for Jina Reader (fallback extractor; free tier)

Set `web_provider = "brave"` or `"tavily"` in `config.toml [search]` to choose the active provider.

## Pre-Phase-6 action required: `SUPABASE_DB_URL` percent-encoding

The `_encode_db_url()` fix in `worker/worker/config.py` handles the encoding at import time. Before Phase 6 wiring, verify the worker boots cleanly against the real Supabase DB URL by running it locally: `python -m worker.main`. If the URL still breaks asyncpg, manually percent-encode special chars in the password: `@`→`%40`, `?`→`%3F`, `%`→`%25`, `&`→`%26`, `,`→`%2C`.

## Open questions to resolve

- _(resolved 2026-05-29)_ ~~DeepSeek "V4 Pro" / "Flash" model IDs~~ — confirmed real: `deepseek-v4-pro` and `deepseek-v4-flash`, both 1M-token context. The 100K handoff ceiling is a self-imposed cost/quality cap, not a model limit.
