"""Web provider tests — all mocked via respx, no real network."""
import httpx
import pytest
import respx

from worker.search.config import SearchConfig
from worker.search.errors import ConfigError, ProviderUnavailable
from worker.search.web.brave import BraveProvider
from worker.search.web.factory import build_web_provider
from worker.search.web.tavily import TavilyProvider


@pytest.fixture
def base_cfg():
    return dict(
        web_provider="brave",
        web_fallback_provider="",
        results_per_query=10,
        timeout=5.0,
        max_retries=4,
        backoff_base=0.001,
        backoff_max=0.01,
        extraction_timeout=5.0,
        extraction_min_words=50,
    )


@pytest.fixture
def brave_cfg(base_cfg):
    return SearchConfig(**base_cfg, brave_api_key="brave-key", tavily_api_key=None, jina_api_key=None)


@pytest.fixture
def tavily_cfg(base_cfg):
    return SearchConfig(**base_cfg, brave_api_key=None, tavily_api_key="tav-key", jina_api_key=None)


@pytest.fixture
def no_key_cfg(base_cfg):
    return SearchConfig(**base_cfg, brave_api_key=None, tavily_api_key=None, jina_api_key=None)


# ── BraveProvider ──────────────────────────────────────────────────────────────

_BRAVE_RESPONSE = {
    "web": {
        "results": [
            {
                "title": "First Result",
                "url": "https://first.example.com",
                "description": "A snippet about the topic.",
                "age": "2024-01-15",
            },
            {
                "title": "Second Result",
                "url": "https://second.example.com",
                "description": None,
            },
        ]
    }
}


@respx.mock
async def test_brave_search_returns_results(brave_cfg):
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(200, json=_BRAVE_RESPONSE)
    )
    provider = BraveProvider(api_key=brave_cfg.brave_api_key, cfg=brave_cfg)
    results = await provider.search("test query", count=5, tier="news")

    assert len(results) == 2
    assert results[0].title == "First Result"
    assert results[0].provider == "brave"
    assert results[0].tier == "news"
    assert results[0].snippet == "A snippet about the topic."
    assert results[0].raw_content is None


@respx.mock
async def test_brave_sets_correct_tier(brave_cfg):
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(200, json=_BRAVE_RESPONSE)
    )
    provider = BraveProvider(api_key=brave_cfg.brave_api_key, cfg=brave_cfg)
    results = await provider.search("q", count=3, tier="government")
    for r in results:
        assert r.tier == "government"


@respx.mock
async def test_brave_empty_results(brave_cfg):
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(200, json={"web": {"results": []}})
    )
    provider = BraveProvider(api_key=brave_cfg.brave_api_key, cfg=brave_cfg)
    results = await provider.search("q", count=5, tier="news")
    assert results == []


@respx.mock
async def test_brave_propagates_provider_unavailable_on_503(brave_cfg):
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(503)
    )
    provider = BraveProvider(api_key=brave_cfg.brave_api_key, cfg=brave_cfg)
    with pytest.raises(ProviderUnavailable):
        await provider.search("q", count=5, tier="news")


# ── TavilyProvider ─────────────────────────────────────────────────────────────

_TAVILY_RESPONSE = {
    "results": [
        {
            "title": "Tavily Article",
            "url": "https://tavily-article.com",
            "content": "A short snippet.",
            "raw_content": "Full article body text here with many words.",
            "published_date": "2024-02-10",
        },
        {
            "title": "No Raw Content",
            "url": "https://no-raw.com",
            "content": "Snippet only.",
            "raw_content": None,
        },
    ]
}


@respx.mock
async def test_tavily_sets_raw_content(tavily_cfg):
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(200, json=_TAVILY_RESPONSE)
    )
    provider = TavilyProvider(api_key=tavily_cfg.tavily_api_key, cfg=tavily_cfg)
    results = await provider.search("query", count=5, tier="industry")

    assert results[0].raw_content == "Full article body text here with many words."
    assert results[0].provider == "tavily"
    assert results[0].tier == "industry"
    assert results[1].raw_content is None


@respx.mock
async def test_tavily_propagates_provider_unavailable_on_5xx(tavily_cfg):
    respx.post("https://api.tavily.com/search").mock(return_value=httpx.Response(500))
    provider = TavilyProvider(api_key=tavily_cfg.tavily_api_key, cfg=tavily_cfg)
    with pytest.raises(ProviderUnavailable):
        await provider.search("q", count=5, tier="news")


# ── build_web_provider factory ─────────────────────────────────────────────────

def test_build_brave_returns_brave_provider(brave_cfg):
    p = build_web_provider("brave", brave_cfg)
    assert isinstance(p, BraveProvider)


def test_build_tavily_returns_tavily_provider(tavily_cfg):
    p = build_web_provider("tavily", tavily_cfg)
    assert isinstance(p, TavilyProvider)


def test_unknown_provider_raises_config_error(brave_cfg):
    with pytest.raises(ConfigError, match="Unknown web provider"):
        build_web_provider("bing", brave_cfg)


def test_missing_brave_key_raises_config_error(no_key_cfg):
    with pytest.raises(ConfigError, match="BRAVE_SEARCH_API_KEY"):
        build_web_provider("brave", no_key_cfg)


def test_missing_tavily_key_raises_config_error(no_key_cfg):
    with pytest.raises(ConfigError, match="TAVILY_API_KEY"):
        build_web_provider("tavily", no_key_cfg)
