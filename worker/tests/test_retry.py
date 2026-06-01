"""Retry policy tests — all mocked via respx, no real network."""
import httpx
import pytest
import respx

from worker.search.config import SearchConfig
from worker.search.errors import ProviderUnavailable
from worker.search.retry import make_client, with_retry


@pytest.fixture
def cfg():
    return SearchConfig(
        web_provider="brave",
        web_fallback_provider="",
        results_per_query=10,
        timeout=5.0,
        max_retries=4,
        backoff_base=0.001,
        backoff_max=0.01,
        extraction_timeout=5.0,
        extraction_min_words=50,
        brave_api_key="test-key",
        tavily_api_key=None,
        jina_api_key=None,
    )


@respx.mock
async def test_succeeds_after_two_failures(cfg):
    url = "https://example.com/api"
    _responses = iter([
        httpx.Response(500),
        httpx.Response(500),
        httpx.Response(200, json={"ok": True}),
    ])
    route = respx.get(url).mock(side_effect=lambda req: next(_responses))

    client = make_client(cfg)

    async def _fn():
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()

    result = await with_retry(_fn, cfg, "test_provider")
    assert result == {"ok": True}
    assert route.call_count == 3


@respx.mock
async def test_retries_on_429(cfg):
    url = "https://example.com/api"
    _responses = iter([
        httpx.Response(429),
        httpx.Response(200, json={"retried": True}),
    ])
    route = respx.get(url).mock(side_effect=lambda req: next(_responses))

    client = make_client(cfg)

    async def _fn():
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()

    result = await with_retry(_fn, cfg, "test_provider")
    assert result == {"retried": True}
    assert route.call_count == 2


@respx.mock
async def test_no_retry_on_401(cfg):
    url = "https://example.com/api"
    route = respx.get(url).mock(return_value=httpx.Response(401))

    client = make_client(cfg)

    async def _fn():
        resp = await client.get(url)
        resp.raise_for_status()

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await with_retry(_fn, cfg, "test_provider")

    assert exc_info.value.response.status_code == 401
    assert route.call_count == 1  # no retry on 4xx


@respx.mock
async def test_all_503_raises_provider_unavailable(cfg):
    url = "https://example.com/api"
    respx.get(url).mock(return_value=httpx.Response(503))

    client = make_client(cfg)

    async def _fn():
        resp = await client.get(url)
        resp.raise_for_status()

    with pytest.raises(ProviderUnavailable) as exc_info:
        await with_retry(_fn, cfg, "test_provider")

    assert exc_info.value.attempts == cfg.max_retries
    assert "test_provider" in str(exc_info.value)


@respx.mock
async def test_transport_error_raises_provider_unavailable(cfg):
    url = "https://example.com/api"
    respx.get(url).mock(side_effect=httpx.ConnectError("connection refused"))

    client = make_client(cfg)

    async def _fn():
        await client.get(url)

    with pytest.raises(ProviderUnavailable) as exc_info:
        await with_retry(_fn, cfg, "test_provider")

    assert exc_info.value.attempts == cfg.max_retries


def test_make_client_returns_async_client(cfg):
    client = make_client(cfg)
    assert isinstance(client, httpx.AsyncClient)
