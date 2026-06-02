# Plan: Fix Bug #3 — LangSmith tracing not working

## Context

LangSmith shows the `ytres` project **empty / "waiting for traces"** even though the worker
(on Render) makes many LLM calls. Phase 6 wired the env vars and a startup diagnostic, yet no
traces appear.

**Root cause — CONFIRMED from Render worker logs (2026-06-02):**

```
INFO  __main__         LangSmith tracing: ACTIVE (project=ytres)
WARNING langsmith.client Failed to multipart ingest runs: ... HTTPError(
  '403 Client Error: Forbidden for url: https://api.smith.langchain.com/runs/multipart',
  '{"error":"Forbidden"}')
```

Tracing **is** active, the key **is** loaded on Render, and traces **are** being POSTed — but
**LangSmith rejects every upload with `403 Forbidden`**. This is an auth/authorization failure
on the key itself, not a missing-key or flush problem. A 403 (not 401) on `/runs/multipart`
means one of:

1. The API key is **revoked / rotated / truncated** (copy-paste error or trailing whitespace
   when pasted into Render's env field), or
2. The key belongs to a **different workspace** than the one showing the empty `ytres` project, or
3. A **region mismatch** — an EU LangSmith account must POST to
   `https://eu.api.smith.langchain.com`, but `config.py:101-102` **hardcodes the US endpoint**
   `https://api.smith.langchain.com`. An EU key against the US endpoint returns exactly 403.

The reason this went unnoticed: the startup diagnostic (`main.py:34-38`) only checks
`bool(key)` — it logs "ACTIVE" even when the key is rejected — and the langsmith tracer
downgrades the 403 to a buried per-job `WARNING` instead of failing loudly.

**Intended outcome:** a valid key + correct region so traces land in `ytres`, plus a startup
probe that turns a future 403/401 into one loud, explained log line instead of silent emptiness.

> The `generate_report` DeepSeek 400 ("json") error in the same logs is a **separate bug owned
> by another agent** — explicitly out of scope here.

**Region note:** check the LangSmith URL — `smith.langchain.com` = US (current hardcoded
endpoint is correct → 403 is a bad/wrong-workspace key); `eu.smith.langchain.com` = EU (the
hardcoded US endpoint is the cause → set `LANGCHAIN_ENDPOINT` to the EU URL). The plan keeps
the endpoint configurable so either case is covered without a code change.

## Files involved

- `worker/worker/config.py` — make the LangSmith endpoint configurable (drop the hardcode)
- `config.toml` — add `langchain_endpoint` under `[observability]`
- `worker/worker/observability.py` — **new** helper: active auth probe (+ optional flush)
- `worker/worker/main.py` — call the probe at startup instead of the present-only check
- `context/deferredwork.md`, `context/log.md`, `context/bug-corrections.md`, `.env.example` — docs

## Implementation

### Step 1 — Primary fix: valid key + correct region on Render (USER ACTION — deferred work)
This is the actual cause of the 403; the code steps below make it observable and configurable.
- In the LangSmith workspace that owns (or should own) the `ytres` project: **Settings → API
  Keys → create a new key** (Personal Access Token `lsv2_pt_…` or a Service key with trace
  write). Confirm the workspace matches the UI where you expect `ytres`.
- Note the **region**: US accounts → `https://api.smith.langchain.com`; EU accounts →
  `https://eu.api.smith.langchain.com`.
- In **Render → service → Environment**: set `LANGCHAIN_API_KEY` to the new key with **no
  quotes/trailing spaces**; if EU, also set the new `LANGCHAIN_ENDPOINT` (see Step 2). Redeploy.

Document this in `context/deferredwork.md` and **alert the user** (per CLAUDE.md), since the
key/region live outside the repo.

### Step 2 — Make the LangSmith endpoint configurable (remove hardcode)
`config.py:101-102` hardcodes the US endpoint. Per CLAUDE.md ("avoid hard-coding"), add a
config knob:
- `config.toml [observability]`: add `langchain_endpoint = "https://api.smith.langchain.com"`.
- `config.py`: read `_endpoint = _obs.get("langchain_endpoint", "https://api.smith.langchain.com")`
  and use it in both `setdefault("LANGCHAIN_ENDPOINT", _endpoint)` and
  `setdefault("LANGSMITH_ENDPOINT", _endpoint)`. An env var still overrides (setdefault), so
  Render can set `LANGCHAIN_ENDPOINT` directly for EU without a config edit. Export it as
  `LANGCHAIN_ENDPOINT` for the startup log.

### Step 3 — Active auth probe at startup (turn the silent 403 into a loud line)
Add `worker/worker/observability.py` with `check_langsmith() -> None`:
- If inactive (no key) → `WARNING` with the "set it in Render env, not .env" hint.
- If active → instantiate `langsmith.Client()` and make **one authenticated call** —
  `client.create_project(LANGCHAIN_PROJECT)` catching the already-exists conflict (idempotent),
  or `client.read_project(project_name=…)`. On success log:
  `LangSmith OK — project=%s endpoint=%s key=…%s` (mask key to last 4 chars).
  On failure log at **ERROR** with the status and remediation, e.g.
  `LangSmith auth FAILED (403) — key revoked/rotated, wrong workspace, or wrong region
  (EU keys need LANGCHAIN_ENDPOINT=https://eu.api.smith.langchain.com). endpoint=%s`.
- Wrap so a probe failure never crashes startup (log + continue).

Wire into `main.py:34-38`, replacing the current ACTIVE/INACTIVE block with
`from worker.observability import check_langsmith; check_langsmith()`.

### Step 4 — (Optional) Flush on shutdown
Render restarts can kill the process mid-batch. Add `flush_traces()` wrapping
`wait_for_all_tracers()` (`from langchain_core.tracers.langchain import wait_for_all_tracers`,
confirmed present) and call it from `main.py`'s `finally` (via `run_in_executor`, it's sync).
Lower priority than Steps 1–3 since the current failure is rejection, not loss.

### Step 5 — Docs
Update `.env.example` (note EU endpoint option), `context/log.md`, and mark Bug #3 resolved in
`context/bug-corrections.md`.

## Verification

1. **Local probe test:** run the new `check_langsmith()` with the current (bad) key → must log
   the `403 ... FAILED` ERROR line. Swap in the new valid key → must log `LangSmith OK`.
2. **On Render:** set the new key (+ region endpoint if EU), redeploy, read logs — confirm
   `LangSmith OK — project=ytres …` and that the per-job `403 Forbidden` WARNING is **gone**.
3. **End-to-end:** trigger a job (approve a plan → `generate_plan`, or re-run a report) and
   confirm a run appears in the `ytres` LangSmith project within ~1 minute.
4. **Regression:** run worker `pytest` to confirm `main`/config changes don't break startup.
