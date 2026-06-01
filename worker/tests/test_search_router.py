"""Router routing and tier-fanout tests — uses lightweight mock providers."""
import pytest

from worker.search.config import SearchConfig
from worker.search.errors import ProviderUnavailable
from worker.search.models import SearchResult
from worker.search.router import SearchRouter


@pytest.fixture
def cfg():
    return SearchConfig(
        web_provider="brave",
        web_fallback_provider="",
        results_per_query=5,
        timeout=5.0,
        max_retries=4,
        backoff_base=0.001,
        backoff_max=0.01,
        extraction_timeout=5.0,
        extraction_min_words=50,
        brave_api_key="k",
        tavily_api_key=None,
        jina_api_key=None,
    )


def _result(title, tier, provider="mock"):
    return SearchResult(title=title, url=f"https://{title}.com", tier=tier, provider=provider)


class _MockWeb:
    name = "mock_web"
    called_with: list = []

    async def search(self, query, *, count, tier):
        self.called_with.append((query, tier))
        return [_result("web-result", tier, provider=self.name)]

    async def aclose(self):
        pass


class _MockAcademic:
    name = "mock_academic"
    called_with: list = []

    async def search(self, query, *, count):
        self.called_with.append(query)
        return [_result("academic-result", "academic", provider=self.name)]

    async def aclose(self):
        pass


class _FailingWeb:
    name = "failing_web"

    async def search(self, query, *, count, tier):
        raise ProviderUnavailable("failing_web", attempts=4)

    async def aclose(self):
        pass


class _FailingAcademic:
    name = "failing_academic"

    async def search(self, query, *, count):
        raise ProviderUnavailable("failing_academic", attempts=4)

    async def aclose(self):
        pass


async def test_academic_only_calls_only_academic(cfg):
    web = _MockWeb()
    web.called_with = []
    academic = _MockAcademic()
    academic.called_with = []

    router = SearchRouter(web_provider=web, academic_client=academic, cfg=cfg)
    response = await router.search("quantum gravity", ["academic"])

    assert len(academic.called_with) == 1
    assert len(web.called_with) == 0
    assert len(response.results) == 1
    assert response.results[0].tier == "academic"
    assert response.failures == []


async def test_web_only_tiers_call_only_web(cfg):
    web = _MockWeb()
    web.called_with = []
    academic = _MockAcademic()
    academic.called_with = []

    router = SearchRouter(web_provider=web, academic_client=academic, cfg=cfg)
    response = await router.search("climate policy", ["news"])

    assert len(web.called_with) == 1
    assert len(academic.called_with) == 0
    assert response.results[0].provider == "mock_web"
    assert response.failures == []


async def test_mixed_tiers_fan_out_to_both(cfg):
    web = _MockWeb()
    web.called_with = []
    academic = _MockAcademic()
    academic.called_with = []

    router = SearchRouter(web_provider=web, academic_client=academic, cfg=cfg)
    response = await router.search("climate science", ["academic", "news"])

    assert len(web.called_with) == 1
    assert len(academic.called_with) == 1
    assert len(response.results) == 2

    tiers = {r.tier for r in response.results}
    assert "academic" in tiers
    assert "news" in tiers


async def test_duplicate_tiers_deduplicated(cfg):
    """Duplicate tiers in the input should result in a single call per backend."""
    web = _MockWeb()
    web.called_with = []
    academic = _MockAcademic()
    academic.called_with = []

    router = SearchRouter(web_provider=web, academic_client=academic, cfg=cfg)
    response = await router.search("q", ["news", "news", "industry"])

    # Both "news" and "industry" map to web → single web call
    assert len(web.called_with) == 1


async def test_multiple_web_tiers_single_web_call(cfg):
    """government + news + industry → one web call (v1 behavior)."""
    web = _MockWeb()
    web.called_with = []
    academic = _MockAcademic()
    academic.called_with = []

    router = SearchRouter(web_provider=web, academic_client=academic, cfg=cfg)
    await router.search("q", ["government", "news", "industry"])

    assert len(web.called_with) == 1


async def test_empty_tiers_returns_empty(cfg):
    web = _MockWeb()
    academic = _MockAcademic()
    router = SearchRouter(web_provider=web, academic_client=academic, cfg=cfg)
    response = await router.search("q", [])
    assert response.results == []
    assert response.failures == []


async def test_result_provider_tagged_correctly(cfg):
    web = _MockWeb()
    web.called_with = []
    academic = _MockAcademic()
    academic.called_with = []

    router = SearchRouter(web_provider=web, academic_client=academic, cfg=cfg)
    response = await router.search("q", ["academic", "industry"])

    providers = {r.provider for r in response.results}
    assert "mock_web" in providers
    assert "mock_academic" in providers
