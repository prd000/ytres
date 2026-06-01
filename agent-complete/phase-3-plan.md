# Phase 3 — Search Infrastructure

## Context

ytres is an AI research pipeline. Phases 0–2 are complete: the navigable frontend shell, the
Supabase infrastructure/auth/job-queue, and the Projects module (CRUD + RLS + status state machine).
The next milestone in the PRD build order is **Phase 3: Search Infrastructure** — the deterministic
"plumbing" the Phase 6 worker pipeline will consume to actually find and fetch sources.

Per the PRD, Phase 3 is **pure Python API-client code living in the worker**, with:
- **No project/DB dependency** (it's stateless clients — "Depends on: Phase 1, no project dependency").
- **No LLM calls** (it's deterministic plumbing, explicitly *not* traced in LangSmith).
- **Mocked-API tests only** (no real network or keys required to pass CI).

Scope (PRD §"Phase 3"): a web-search client (Brave/Tavily) with exponential-backoff retry; a
Semantic Scholar academic client (keyless); a trafilatura → Jina content-extraction fallback chain;
tier routing (academic → Semantic Scholar; government/news/industry → web); and graceful degradation
when APIs fail. It **unblocks the Phase 6 worker pipeline**.

### Resolved decisions (confirmed with user, 2026-05-31)
1. **Both web providers, swappable, default Brave.** Implement Brave + Tavily behind one
   `WebSearchProvider` interface; `config.toml` selects the active provider. Keep it modular so the
   provider can be swapped without touching callers.
2. **Provider-aware extraction.** When a web result already carries usable body text (Tavily's
   `raw_content`), use it directly and **skip** the trafilatura→Jina chain; fall through to the chain
   only when raw content is absent or too short.
3. **Retry + extraction fallback for v1 (tenacity).** Exponential-backoff retry on transient HTTP
   errors + trafilatura→Jina fallback. Partial failures surface as structured info. **No** automatic
   Brave↔Tavily failover in v1 (the router supports a `web_fallback_provider` hook, but it defaults
   to disabled).

### Heads-up (separate from Phase 3, surfaced because the line was highlighted)
The `SUPABASE_DB_URL` password in `.env` contains raw URL-reserved characters (`@`, `?`, `%`, `&`,
`,`). Unencoded, these will break `asyncpg`/URL parsing (the `@` in particular terminates the
userinfo segment early). Before the worker can connect for real, the password must be
percent-encoded (e.g. `@`→`%40`, `?`→`%3F`, `%`→`%25`, `&`→`%26`, `,`→`%2C`). Phase 3 tests don't
need the DB, so this doesn't block this phase — flagging it so it's fixed before Phase 6 wiring.

---

## Module layout — new `worker/worker/search/` package

```
worker/worker/search/
  __init__.py          # Public surface: build_router(), SearchRouter, models, errors
  models.py            # Pydantic: SearchResult, ExtractedContent, SearchResponse, SearchFailure, Tier
  errors.py            # Exception hierarchy: SearchError, ProviderUnavailable, ExtractionFailed, ...
  config.py            # Frozen SearchConfig dataclass, assembled from worker.config values
  retry.py             # tenacity async-retry policy + shared httpx.AsyncClient factory (make_client)
  base.py              # ABCs: WebSearchProvider, ContentExtractor
  web/
    brave.py           # BraveProvider(WebSearchProvider)   — snippets only
    tavily.py          # TavilyProvider(WebSearchProvider)  — sets raw_content on results
    factory.py         # build_web_provider(name, cfg) -> WebSearchProvider  (config-driven select)
  academic/
    semantic_scholar.py  # SemanticScholarClient — keyless Graph API; metadata + abstract + pdf_url
  extraction/
    trafilatura_extractor.py  # sync lib wrapped via asyncio.to_thread
    jina_extractor.py         # async Jina Reader fallback
    chain.py                  # ExtractionChain: provider raw_content → trafilatura → jina
  router.py            # SearchRouter — tiers→clients fan-out, merge, partial-failure collection
```

**Result-model location:** keep these in `worker/worker/search/models.py`, **not** in
`shared/schemas/job_payloads.py`. `shared/schemas` is the frontend↔worker *wire* contract (job
payloads / `worker_activity` rows mirrored in TS); Phase 3 results are internal worker plumbing
consumed by Phase 6 and never cross the TS boundary in this shape. Mirror the existing Pydantic
style from `shared/schemas/job_payloads.py`.

---

## Key abstractions (signatures)

```python
# models.py
Tier = Literal["academic", "government", "news", "industry"]

class SearchResult(BaseModel):
    title: str; url: str; tier: Tier; provider: str
    snippet: str | None = None
    raw_content: str | None = None        # set by Tavily; consumed by ExtractionChain to skip fetch
    published_at: str | None = None
    pdf_url: str | None = None            # academic open-access PDF
    metadata: dict = {}

class ExtractedContent(BaseModel):
    url: str; text: str; extractor: Literal["provider", "trafilatura", "jina"]
    title: str | None = None; word_count: int

class SearchFailure(BaseModel):            # JSON-serializable, recorded on the job row in Phase 6
    stage: Literal["web_search","academic_search","extraction"]
    provider: str | None; tier: Tier | None; url: str | None = None
    error_type: str; message: str; attempts: int

class SearchResponse(BaseModel):
    results: list[SearchResult]; failures: list[SearchFailure]   # partial degradation, not a raise

# base.py
class WebSearchProvider(ABC):
    name: str
    async def search(self, query: str, *, count: int, tier: Tier) -> list[SearchResult]: ...
class ContentExtractor(ABC):
    name: str
    async def extract(self, url: str) -> ExtractedContent: ...   # raises ExtractionFailed

# router.py
TIER_ROUTING = {"academic":"academic", "government":"web", "news":"web", "industry":"web"}
class SearchRouter:
    async def search(self, query, tiers: list[Tier], *, count=None) -> SearchResponse: ...
```

- **Router:** de-dupes tiers, fans out concurrently (`asyncio.gather`) — academic → Semantic Scholar,
  any web tier → the configured web provider (single web call, tier-tagged for v1) — merges results,
  and collects per-client `SearchFailure`s. Academic-OK-but-web-down returns results **plus** a
  failure entry (graceful degradation). All clients down → raise `SearchError(failures=[...])`.
- **ExtractionChain (provider-aware, per decision 2):** if `SearchResult.raw_content` is present and
  ≥ `extraction_min_words`, return `ExtractedContent(extractor="provider")` with no network call;
  else try trafilatura (off-thread) → Jina; raise `ExtractionFailed` only if all fail (carrying each
  step's `SearchFailure`).

---

## Retry & degradation (decision 3)

Centralized in `retry.py` using **tenacity** (`AsyncRetrying`, `wait_exponential`,
`stop_after_attempt`, `retry_if_exception_type`). Retry only transient errors —
`httpx.TransportError` and 429/5xx (`HTTPStatusError`); 4xx (401/400/etc.) fail fast, no retry.
Exhaustion raises `ProviderUnavailable(attempts=...)`. A shared `make_client()` builds the
`httpx.AsyncClient` with `cfg.timeout`. Auto provider-switch is **not** in v1 (the
`web_fallback_provider` hook exists but defaults off).

---

## Config wiring (backend first, per CLAUDE.md)

**`worker/worker/config.py`** — add optional secrets (use `os.environ.get`, so the worker still boots
without search keys; Semantic Scholar + trafilatura are keyless):
```python
BRAVE_SEARCH_API_KEY = os.environ.get("BRAVE_SEARCH_API_KEY")   # matches .env.example spelling
TAVILY_API_KEY       = os.environ.get("TAVILY_API_KEY")
JINA_API_KEY         = os.environ.get("JINA_API_KEY")
```
…and read a new `[search]` table from `config.toml` (`web_provider`, `web_fallback_provider`,
`results_per_query`, `timeout`, `max_retries`, `backoff_base`, `backoff_max`, `extraction_timeout`,
`extraction_min_words`). `search/config.py` assembles these into a frozen `SearchConfig`.

**`config.toml`** — add (safe to commit; no secrets):
```toml
[search]
web_provider          = "brave"   # "brave" | "tavily"  (swappable)
web_fallback_provider = ""        # "" = disabled (no auto-switch in v1)
results_per_query     = 10
timeout               = 20.0
max_retries           = 4
backoff_base          = 0.5
backoff_max           = 30.0
extraction_timeout    = 30.0
extraction_min_words  = 50        # raw_content/extraction below this → fall through to next extractor
```

**`worker/pyproject.toml`** — runtime: `httpx>=0.27`, `trafilatura>=1.8`, `tenacity>=8.2`; test:
`respx>=0.21`. (trafilatura is sync/CPU-bound → always invoked via `asyncio.to_thread`.)

---

## Build order (each step independently testable; follow the `tdd` skill — red/green)

1. `models.py` + `errors.py` → `tests/test_search_models.py`.
2. Config + deps: `pyproject.toml`, `config.py`/`config.toml`, `search/config.py`.
3. `retry.py` (+ `make_client`) → `tests/test_retry.py`.
4. `base.py` ABCs.
5. `web/brave.py`, `web/tavily.py`, `web/factory.py` → `tests/test_web_providers.py`.
6. `academic/semantic_scholar.py` → tests (mocked).
7. `extraction/{trafilatura_extractor,jina_extractor,chain}.py` → `tests/test_extraction.py`.
8. `router.py` → `tests/test_search_router.py`, `tests/test_degradation.py`.
9. `search/__init__.py` — re-export `build_router(cfg)`, `SearchRouter`, models, errors.

---

## Reused / referenced existing code
- `worker/worker/config.py` — the `os.environ` (secrets) + `tomllib` (tuning) split to extend.
- `worker/worker/loop.py` — `fail_job(job_id, error[:2000])` shows how Phase 6 will record the
  `SearchFailure` info Phase 3 returns; confirms the structured-failure contract.
- `shared/schemas/job_payloads.py` — Pydantic/`BaseModel` style to mirror in `search/models.py`.
- `worker/tests/conftest.py` — pytest style + `asyncio_mode="auto"`; Phase 3 adds respx HTTP-mock
  fixtures (no Postgres pool needed).
- `web/src/lib/data/types.ts` (`SourceTier`) + `0002_core_tables.sql` (`source_tier` enum) — the
  canonical tier values the `Tier` literal must match exactly.

---

## Testing strategy (all mocked — no network, no keys)
- **Models/contract:** required fields, literal validation, `SearchFailure` JSON round-trips.
- **Retry** (respx): 500,500,200 → succeeds after 3 calls; 429→retried; 401→single call, no retry;
  all-503 → `ProviderUnavailable(attempts==max_retries)`. Patch backoff to ~0 so tests don't sleep.
- **Web providers** (respx): canned Brave/Tavily JSON → `SearchResult[]`; Tavily sets `raw_content`;
  `build_web_provider("brave"|"tavily")` returns right class, unknown name raises; missing key → clear error.
- **Academic** (respx): Semantic Scholar JSON → results with `pdf_url`/metadata.
- **Extraction:** raw_content present → `extractor=="provider"`, no fetch; trafilatura good → `"trafilatura"`,
  Jina not called; trafilatura empty/short → Jina (`"jina"`); both fail → `ExtractionFailed`. Verify
  trafilatura runs via `asyncio.to_thread`. Mock trafilatura with `monkeypatch.setattr`.
- **Router/degradation:** `["academic"]` → only Semantic Scholar; web-only tiers → only web; mixed →
  both fan out, tier/provider tagging correct, tiers de-duped; web-down+academic-OK → partial
  `SearchResponse` (results + one failure, no raise); all down → `SearchError`.

---

## Verification (end-to-end for the phase)
1. `cd worker && pip install -e ".[test]"` (or `uv pip ...`) installs httpx/trafilatura/tenacity/respx.
2. `pytest worker/tests/ -q` → **all green**, including the new search suites; **no real network**
   (respx asserts on routes). The existing Phase 1 queue/contract tests still pass.
3. `python -c "from worker.search import build_router"` imports cleanly (package wiring sound).
4. (Optional, needs a real key) a tiny scratch script: `build_router(cfg).search("test query",
   ["academic","news"])` returns merged results — confirms live wiring before Phase 6 consumes it.

---

## Doc updates on completion (per CLAUDE.md)
- `context/log.md` — new Phase 3 entry (newest first).
- `context/map.md` — add the `worker/worker/search/` tree + the new test files.
- `context/decisions.md` — record: swappable web provider (default Brave); provider-aware extraction
  (raw_content short-circuit); tenacity retry + extraction-fallback, no auto provider-switch in v1.
- `context/deferredwork.md` — fix the `BRAVE_API_KEY` → **`BRAVE_SEARCH_API_KEY`** naming mismatch
  (`.env.example` is the source of truth); note search keys are now read by `config.py` but optional
  (keyless Semantic Scholar + trafilatura path works without them). Add the `SUPABASE_DB_URL`
  percent-encoding fix as a pre-Phase-6 action item.
