"""
Centralized retry policy and shared httpx client factory.

Only transient HTTP errors are retried: httpx.TransportError and 429/5xx
HTTPStatusError. Non-transient errors (401, 403, 400 etc.) fail fast.
Exhausted retries raise ProviderUnavailable — callers never see raw httpx errors
from retry-wrapped calls.
"""
from __future__ import annotations
import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from .config import SearchConfig
from .errors import ProviderUnavailable


def make_client(cfg: SearchConfig) -> httpx.AsyncClient:
    """Shared httpx.AsyncClient factory — applies configured timeout."""
    return httpx.AsyncClient(timeout=cfg.timeout)


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        sc = exc.response.status_code
        return sc == 429 or sc >= 500
    return False


async def with_retry(fn, cfg: SearchConfig, provider: str):
    """Execute async callable fn with exponential-backoff retry.

    Retries on httpx.TransportError and 429/5xx status. 4xx errors (except 429)
    are not retried and propagate as httpx.HTTPStatusError. After cfg.max_retries
    exhausted attempts, raises ProviderUnavailable.
    """
    attempts = 0
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(cfg.max_retries),
            wait=wait_exponential(multiplier=cfg.backoff_base, max=cfg.backoff_max),
            retry=retry_if_exception(_is_transient),
            reraise=True,
        ):
            with attempt:
                attempts += 1
                return await fn()
    except httpx.HTTPStatusError as exc:
        if _is_transient(exc):
            raise ProviderUnavailable(provider=provider, attempts=attempts) from exc
        raise
    except httpx.TransportError as exc:
        raise ProviderUnavailable(provider=provider, attempts=attempts) from exc
