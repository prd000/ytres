"""
Worker configuration — secrets from env (.env), tuning from config.toml.
"""
import os
import tomllib
from pathlib import Path
from urllib.parse import quote


def _encode_db_url(raw: str) -> str:
    """Percent-encode the password in a postgres DSN.

    Supabase passwords can contain chars like %, @, comma that break asyncpg's
    URL parser unless they are properly escaped.
    """
    if "://" not in raw:
        return raw
    scheme, rest = raw.split("://", 1)
    # The userinfo/host boundary is the LAST "@" — the host never contains "@",
    # but the password may (along with "?", "%", "," etc.). Splitting on "?" or
    # the first "@" before this point would slice the password in half.
    at = rest.rfind("@")
    if at == -1:
        return raw
    userinfo, hostpart = rest[:at], rest[at + 1:]
    # The user never contains ":" (Supabase users are "postgres" / "postgres.ref"),
    # so the first ":" splits user from password; the password keeps the rest.
    colon = userinfo.find(":")
    if colon == -1:
        return raw
    user, password = userinfo[:colon], userinfo[colon + 1:]
    # Encode every reserved char in the password, including any "?". The host part
    # (and any real "?sslmode=..." query string) is already valid, so leave it as-is.
    encoded = quote(password, safe="")
    return f"{scheme}://{user}:{encoded}@{hostpart}"

# ── Config file (repo root) ───────────────────────────────────────────────────
_cfg_path = Path(__file__).parent.parent.parent / "config.toml"
with open(_cfg_path, "rb") as _f:
    _cfg = tomllib.load(_f)

_w   = _cfg["worker"]
_obs = _cfg.get("observability", {})
_res = _cfg.get("research", {})
_rep = _cfg.get("report", {})

# ── Database ──────────────────────────────────────────────────────────────────
# Direct asyncpg connection string (bypasses RLS by design — trusted server).
SUPABASE_DB_URL: str = _encode_db_url(os.environ["SUPABASE_DB_URL"])

# ── Concurrency & polling ─────────────────────────────────────────────────────
WORKER_CONCURRENCY: int   = _w["concurrency"]
POLL_INTERVAL: float      = _w["poll_interval"]

# ── Heartbeat & stale-job reclaim ─────────────────────────────────────────────
# HEARTBEAT_INTERVAL must be well under STALE_TIMEOUT_SECONDS (< half) so a
# single missed heartbeat doesn't trigger reclaim.
HEARTBEAT_INTERVAL: float        = _w["heartbeat_interval"]
WATCHDOG_INTERVAL: float         = _w["watchdog_interval"]
STALE_TIMEOUT_SECONDS: int       = _w["stale_timeout_seconds"]
COORDINATOR_SWEEP_INTERVAL: float = _w["coordinator_sweep_interval"]

# ── Graceful shutdown ─────────────────────────────────────────────────────────
# On SIGTERM/SIGINT the loop stops claiming and waits up to this many seconds
# for in-flight jobs to finish before the process exits.
GRACE_SHUTDOWN_SECONDS: float = _w["grace_shutdown_seconds"]

# ── Research pipeline ──────────────────────────────────────────────────────────
# Self-imposed ceiling on cumulative Pro-eval input tokens per handler invocation.
# Before an eval that would push past this, the handler enqueues a continuation
# job and exits cleanly — tunable without a code deploy.
CONTEXT_CEILING_TOKENS: int = _res.get("context_ceiling_tokens", 100_000)

# ── Report generation ──────────────────────────────────────────────────────────
REPORT_SOURCE_CAP: int   = _rep.get("report_source_cap", 25)
REPORT_SOURCE_CHARS: int = _rep.get("report_source_chars", 4000)

# ── Search provider keys (optional — keyless Semantic Scholar + trafilatura path
# works without them; keys are only required to use Brave/Tavily/Jina) ─────────
BRAVE_SEARCH_API_KEY: str | None = os.environ.get("BRAVE_SEARCH_API_KEY")
TAVILY_API_KEY:       str | None = os.environ.get("TAVILY_API_KEY")
JINA_API_KEY:         str | None = os.environ.get("JINA_API_KEY")

# ── LLM / Embeddings ──────────────────────────────────────────────────────────
DEEPSEEK_API_KEY: str | None = os.environ.get("DEEPSEEK_API_KEY")
OPENAI_API_KEY:   str | None = os.environ.get("OPENAI_API_KEY")

# ── Observability — wire LangSmith so any installed SDK version finds the key ──
# LangChain SDK reads LANGCHAIN_API_KEY; older versions read LANGSMITH_API_KEY.
# We read both, export both, and set the endpoint + tracing mirror so the
# installed SDK works regardless of which env-var generation it expects.
_langsmith_key: str | None = (
    os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
)
_langchain_project: str = _obs.get("langchain_project", "ytres")
_tracing_enabled: str = str(_obs.get("langchain_tracing", False)).lower()

os.environ.setdefault("LANGCHAIN_TRACING_V2", _tracing_enabled)
os.environ.setdefault("LANGSMITH_TRACING",    _tracing_enabled)
os.environ.setdefault("LANGCHAIN_PROJECT",     _langchain_project)
os.environ.setdefault("LANGCHAIN_ENDPOINT",   "https://api.smith.langchain.com")
os.environ.setdefault("LANGSMITH_ENDPOINT",   "https://api.smith.langchain.com")

if _langsmith_key:
    os.environ.setdefault("LANGCHAIN_API_KEY", _langsmith_key)
    os.environ.setdefault("LANGSMITH_API_KEY", _langsmith_key)

# Exported flag — read by main.py for the startup diagnostic log.
LANGSMITH_ACTIVE: bool = bool(_langsmith_key)
LANGCHAIN_PROJECT: str = _langchain_project
