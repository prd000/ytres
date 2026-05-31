"""
Worker configuration — all tunable constants come from environment variables.
No hard-coded values for anything that might need adjustment per deployment.
"""
import os


# ── Database ──────────────────────────────────────────────────────────────────
# Direct asyncpg connection string (bypasses RLS by design — trusted server).
SUPABASE_DB_URL: str = os.environ["SUPABASE_DB_URL"]

# ── Concurrency & polling ─────────────────────────────────────────────────────
WORKER_CONCURRENCY: int   = int(os.getenv("WORKER_CONCURRENCY",   "5"))
POLL_INTERVAL: float       = float(os.getenv("POLL_INTERVAL",       "2.0"))

# ── Heartbeat & stale-job reclaim ─────────────────────────────────────────────
# HEARTBEAT_INTERVAL must be well under STALE_TIMEOUT_SECONDS (< half) so a
# single missed heartbeat doesn't trigger reclaim.
HEARTBEAT_INTERVAL: float  = float(os.getenv("HEARTBEAT_INTERVAL",  "10.0"))
WATCHDOG_INTERVAL: float   = float(os.getenv("WATCHDOG_INTERVAL",   "60.0"))
STALE_TIMEOUT_SECONDS: int = int(os.getenv("STALE_TIMEOUT_SECONDS", "90"))

# ── Graceful shutdown ─────────────────────────────────────────────────────────
# On SIGTERM/SIGINT the loop stops claiming and waits up to this many seconds
# for in-flight jobs to finish before the process exits.
GRACE_SHUTDOWN_SECONDS: float = float(os.getenv("GRACE_SHUTDOWN_SECONDS", "30.0"))
