"""asyncpg connection pool — shared across the worker process.

Includes startup connection diagnostics: before opening the pool we log the
exact host/port being dialed (never the password) and which IP address families
that host resolves to. This makes "Network is unreachable" failures
self-explanatory — e.g. a host that resolves to IPv6 only cannot be reached
from an IPv4-only platform such as Render, and the log will say so explicitly.
"""
from __future__ import annotations

import json
import logging
import socket
from urllib.parse import urlsplit

import asyncpg

from worker.config import SUPABASE_DB_URL

log = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def register_json_codecs(conn: asyncpg.Connection) -> None:
    """Make asyncpg round-trip json/jsonb columns as Python objects.

    By default asyncpg returns json/jsonb as raw strings, so callers had to
    json.loads() on read and json.dumps() on write. Registering this codec on
    every pooled connection means jsonb columns decode to dict/list on read and
    encode back on write automatically — handlers can treat ctx.job["payload"]
    (and any jsonb column) as a plain dict. See context/decisions.md.

    Used as the pool `init` callback here and in the test pool (conftest.py) so
    tests exercise the same behaviour as production.
    """
    for type_name in ("json", "jsonb"):
        await conn.set_type_codec(
            type_name,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )

# Supabase Supavisor transaction-mode pooler (port 6543) does not support the
# named prepared statements asyncpg caches by default. Disabling the statement
# cache keeps the worker working if a transaction-mode URL is ever used. Session
# mode (5432) and direct connections are unaffected by statement_cache_size=0.
_TRANSACTION_POOLER_PORT = 6543


def _describe_target(url: str) -> tuple[str | None, int]:
    """Return (host, port) parsed from the DSN — never touches the password."""
    parts = urlsplit(url)
    return parts.hostname, (parts.port or 5432)


def _log_dns(host: str, port: int) -> None:
    """Resolve `host` and log the address families it offers.

    The whole point of this is to make IPv6-only hosts obvious: if the only
    addrinfo entries are AF_INET6, an IPv4-only platform (Render) cannot connect
    and asyncpg will fail with OSError(101) "Network is unreachable".
    """
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        log.error("DNS resolution failed for %s:%s — %s", host, port, exc)
        return

    families = {info[0] for info in infos}
    has_v4 = socket.AF_INET in families
    has_v6 = socket.AF_INET6 in families
    fam_label = ", ".join(
        label
        for present, label in ((has_v4, "IPv4"), (has_v6, "IPv6"))
        if present
    ) or "none"
    log.info("DB host %s:%s resolves to: %s", host, port, fam_label)

    if has_v6 and not has_v4:
        log.error(
            "DB host %s resolves to IPv6 ONLY. Render has no IPv6 egress, so this "
            "connection will fail with 'Network is unreachable'. Use the Supabase "
            "Session pooler URL (host aws-0-<region>.pooler.supabase.com, user "
            "postgres.<project-ref>, port 5432), which is IPv4-reachable.",
            host,
        )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        host, port = _describe_target(SUPABASE_DB_URL)
        if host is None:
            log.error("SUPABASE_DB_URL has no host component — check the env var.")
        else:
            _log_dns(host, port)

        kwargs: dict[str, object] = {"min_size": 2, "max_size": 10}
        if port == _TRANSACTION_POOLER_PORT:
            # Transaction-mode pooler: prepared-statement cache must be off.
            kwargs["statement_cache_size"] = 0
            log.info("port %s detected → disabling statement cache (transaction pooler)", port)

        _pool = await asyncpg.create_pool(
            SUPABASE_DB_URL, init=register_json_codecs, **kwargs
        )
        log.info("DB pool ready (%s:%s) — json/jsonb codecs registered", host, port)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
