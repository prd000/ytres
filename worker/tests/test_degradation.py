"""Graceful degradation tests — partial failures and all-down scenarios."""
import pytest

from worker.search.config import SearchConfig
from worker.search.errors import ProviderUnavailable, SearchError
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


def _result(title, tier):
    return SearchResult(title=title, url=f"https://{title}.com", tier=tier, provider="mock")


class _OkWeb:
    name = "ok_web"

    async def search(self, query, *, count, tier):
        return [_result("web-ok", tier)]

    async def aclose(self):
        pass


class _OkAcademic:
    name = "ok_academic"

    async def search(self, query, *, count):
        return [_result("academic-ok", "academic")]

    async def aclose(self):
        pass


class _FailingWeb:
    name = "failing_web"

    async def search(self, query, *, count, tier):
        raise ProviderUnavailable("failing_web", attempts=4, message="web is down")

    async def aclose(self):
        pass


class _FailingAcademic:
    name = "failing_academic"

    async def search(self, query, *, count):
        raise ProviderUnavailable("failing_academic", attempts=4, message="ss is down")

    async def aclose(self):
        pass


async def test_web_down_academic_ok_returns_partial(cfg):
    """Web unavailable + academic OK → SearchResponse with results + one failure."""
    router = SearchRouter(
        web_provider=_FailingWeb(),
        academic_client=_OkAcademic(),
        cfg=cfg,
    )
    response = await router.search("q", ["academic", "news"])

    assert len(response.results) == 1
    assert response.results[0].tier == "academic"
    assert len(response.failures) == 1
    assert response.failures[0].stage == "web_search"
    assert response.failures[0].provider == "failing_web"
    assert response.failures[0].attempts == 4


async def test_academic_down_web_ok_returns_partial(cfg):
    """Academic unavailable + web OK → SearchResponse with results + one failure."""
    router = SearchRouter(
        web_provider=_OkWeb(),
        academic_client=_FailingAcademic(),
        cfg=cfg,
    )
    response = await router.search("q", ["academic", "news"])

    assert len(response.results) == 1
    assert response.failures[0].stage == "academic_search"
    assert response.failures[0].provider == "failing_academic"


async def test_all_down_raises_search_error(cfg):
    """Both providers down → raises SearchError (not a partial response)."""
    router = SearchRouter(
        web_provider=_FailingWeb(),
        academic_client=_FailingAcademic(),
        cfg=cfg,
    )
    with pytest.raises(SearchError) as exc_info:
        await router.search("q", ["academic", "news"])

    assert len(exc_info.value.failures) == 2
    stages = {f.stage for f in exc_info.value.failures}
    assert "web_search" in stages
    assert "academic_search" in stages


async def test_single_web_down_raises_search_error(cfg):
    """Only web tiers requested + web down → raises SearchError."""
    router = SearchRouter(
        web_provider=_FailingWeb(),
        academic_client=_OkAcademic(),
        cfg=cfg,
    )
    with pytest.raises(SearchError):
        await router.search("q", ["news"])


async def test_single_academic_down_raises_search_error(cfg):
    """Only academic requested + academic down → raises SearchError."""
    router = SearchRouter(
        web_provider=_OkWeb(),
        academic_client=_FailingAcademic(),
        cfg=cfg,
    )
    with pytest.raises(SearchError):
        await router.search("q", ["academic"])


async def test_partial_failure_carries_provider_info(cfg):
    """Failure struct includes provider name and attempts from ProviderUnavailable."""
    router = SearchRouter(
        web_provider=_FailingWeb(),
        academic_client=_OkAcademic(),
        cfg=cfg,
    )
    response = await router.search("q", ["academic", "industry"])

    failure = response.failures[0]
    assert failure.provider == "failing_web"
    assert failure.attempts == 4
    assert failure.error_type == "ProviderUnavailable"
