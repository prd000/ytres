"""
Worker configuration — secrets from env (.env), tuning from config.toml.
"""
import os
import tomllib
from pathlib import Path

# ── Config file (repo root) ───────────────────────────────────────────────────
_cfg_path = Path(__file__).parent.parent.parent / "config.toml"
with open(_cfg_path, "rb") as _f:
    _cfg = tomllib.load(_f)

_w   = _cfg["worker"]
_obs = _cfg.get("observability", {})

# ── Database ──────────────────────────────────────────────────────────────────
# Direct asyncpg connection string (bypasses RLS by design — trusted server).
SUPABASE_DB_URL: str = os.environ["SUPABASE_DB_URL"]

# ── Concurrency & polling ─────────────────────────────────────────────────────
WORKER_CONCURRENCY: int   = _w["concurrency"]
POLL_INTERVAL: float      = _w["poll_interval"]

# ── Heartbeat & stale-job reclaim ─────────────────────────────────────────────
# HEARTBEAT_INTERVAL must be well under STALE_TIMEOUT_SECONDS (< half) so a
# single missed heartbeat doesn't trigger reclaim.
HEARTBEAT_INTERVAL: float  = _w["heartbeat_interval"]
WATCHDOG_INTERVAL: float   = _w["watchdog_interval"]
STALE_TIMEOUT_SECONDS: int = _w["stale_timeout_seconds"]

# ── Graceful shutdown ─────────────────────────────────────────────────────────
# On SIGTERM/SIGINT the loop stops claiming and waits up to this many seconds
# for in-flight jobs to finish before the process exits.
GRACE_SHUTDOWN_SECONDS: float = _w["grace_shutdown_seconds"]

# ── Observability — set as env vars so LangChain SDK picks them up automatically
os.environ.setdefault("LANGCHAIN_TRACING_V2", str(_obs.get("langchain_tracing", False)).lower())
os.environ.setdefault("LANGCHAIN_PROJECT",    _obs.get("langchain_project", "ytres"))
