"""Extraction chain tests.

trafilatura (sync) is monkeypatched at the module level.
Jina (async HTTP) is mocked via respx.
"""
import httpx
import pytest
import respx

from worker.search.config import SearchConfig
from worker.search.errors import ExtractionFailed
from worker.search.extraction.chain import ExtractionChain
from worker.search.extraction.jina_extractor import JinaExtractor
from worker.search.extraction.trafilatura_extractor import TrafilaturaExtractor
from worker.search.models import SearchResult


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
        brave_api_key=None,
        tavily_api_key=None,
        jina_api_key=None,
    )


def _make_result(url="https://example.com", raw_content=None):
    return SearchResult(
        title="Article", url=url, tier="news", provider="brave",
        raw_content=raw_content,
    )


# ── ExtractionChain: raw_content short-circuit ─────────────────────────────────

async def test_raw_content_above_min_words_short_circuits(cfg):
    """Raw content with enough words skips all network calls."""
    raw = "word " * 60  # 60 words, above extraction_min_words=50
    result = _make_result(raw_content=raw)
    chain = ExtractionChain(cfg)

    content = await chain.extract(result)

    assert content.extractor == "provider"
    assert content.word_count == 60
    assert content.text == raw


async def test_raw_content_below_min_words_falls_through(cfg, monkeypatch):
    """Raw content below threshold → tries trafilatura next."""
    short_raw = "too short"  # < 50 words
    result = _make_result(raw_content=short_raw)

    monkeypatch.setattr("trafilatura.fetch_url", lambda url: "<html>body</html>")
    monkeypatch.setattr("trafilatura.extract", lambda html: "extracted text content here with enough words")
    monkeypatch.setattr("trafilatura.extract_metadata", lambda html: None)

    chain = ExtractionChain(cfg)
    content = await chain.extract(result)

    assert content.extractor == "trafilatura"


async def test_no_raw_content_tries_trafilatura(cfg, monkeypatch):
    """No raw_content → falls through to trafilatura."""
    result = _make_result(raw_content=None)

    monkeypatch.setattr("trafilatura.fetch_url", lambda url: "<html>page</html>")
    monkeypatch.setattr("trafilatura.extract", lambda html: "some extracted body text")
    monkeypatch.setattr("trafilatura.extract_metadata", lambda html: None)

    chain = ExtractionChain(cfg)
    content = await chain.extract(result)

    assert content.extractor == "trafilatura"
    assert "extracted" in content.text


# ── TrafilaturaExtractor ────────────────────────────────────────────────────────

async def test_trafilatura_success(cfg, monkeypatch):
    monkeypatch.setattr("trafilatura.fetch_url", lambda url: "<html>body</html>")
    monkeypatch.setattr("trafilatura.extract", lambda html: "clean extracted text here")
    monkeypatch.setattr("trafilatura.extract_metadata", lambda html: None)

    extractor = TrafilaturaExtractor()
    content = await extractor.extract("https://example.com")

    assert content.extractor == "trafilatura"
    assert content.text == "clean extracted text here"
    assert content.word_count == 4


async def test_trafilatura_fetch_returns_none_raises(cfg, monkeypatch):
    monkeypatch.setattr("trafilatura.fetch_url", lambda url: None)

    extractor = TrafilaturaExtractor()
    with pytest.raises(ExtractionFailed) as exc_info:
        await extractor.extract("https://example.com")

    assert exc_info.value.url == "https://example.com"
    assert len(exc_info.value.failures) == 1
    assert exc_info.value.failures[0].provider == "trafilatura"


async def test_trafilatura_extract_returns_none_raises(cfg, monkeypatch):
    monkeypatch.setattr("trafilatura.fetch_url", lambda url: "<html>body</html>")
    monkeypatch.setattr("trafilatura.extract", lambda html: None)
    monkeypatch.setattr("trafilatura.extract_metadata", lambda html: None)

    extractor = TrafilaturaExtractor()
    with pytest.raises(ExtractionFailed):
        await extractor.extract("https://example.com")


# ── JinaExtractor ──────────────────────────────────────────────────────────────

@respx.mock
async def test_jina_success(cfg):
    url = "https://example.com/article"
    respx.get(f"https://r.jina.ai/{url}").mock(
        return_value=httpx.Response(200, text="Jina extracted content here")
    )
    extractor = JinaExtractor(cfg)
    content = await extractor.extract(url)

    assert content.extractor == "jina"
    assert content.text == "Jina extracted content here"


@respx.mock
async def test_jina_adds_auth_header_when_key_present():
    cfg = SearchConfig(
        web_provider="brave", web_fallback_provider="", results_per_query=10,
        timeout=5.0, max_retries=4, backoff_base=0.001, backoff_max=0.01,
        extraction_timeout=5.0, extraction_min_words=50,
        brave_api_key=None, tavily_api_key=None, jina_api_key="my-jina-key",
    )
    url = "https://example.com"
    route = respx.get(f"https://r.jina.ai/{url}").mock(
        return_value=httpx.Response(200, text="content here for testing")
    )
    extractor = JinaExtractor(cfg)
    await extractor.extract(url)

    assert route.called
    assert route.calls[0].request.headers.get("authorization") == "Bearer my-jina-key"


@respx.mock
async def test_jina_503_raises_extraction_failed(cfg):
    url = "https://example.com"
    respx.get(f"https://r.jina.ai/{url}").mock(return_value=httpx.Response(503))
    extractor = JinaExtractor(cfg)

    with pytest.raises(ExtractionFailed) as exc_info:
        await extractor.extract(url)

    assert exc_info.value.url == url
    assert len(exc_info.value.failures) == 1


# ── ExtractionChain: fallback & full failure ────────────────────────────────────

@respx.mock
async def test_chain_falls_back_to_jina_when_trafilatura_fails(cfg, monkeypatch):
    monkeypatch.setattr("trafilatura.fetch_url", lambda url: None)

    url = "https://example.com"
    respx.get(f"https://r.jina.ai/{url}").mock(
        return_value=httpx.Response(200, text="Jina content fallback here now")
    )
    chain = ExtractionChain(cfg)
    content = await chain.extract(_make_result(url=url))

    assert content.extractor == "jina"


@respx.mock
async def test_chain_raises_when_both_extractors_fail(cfg, monkeypatch):
    monkeypatch.setattr("trafilatura.fetch_url", lambda url: None)

    url = "https://example.com"
    respx.get(f"https://r.jina.ai/{url}").mock(return_value=httpx.Response(503))

    chain = ExtractionChain(cfg)
    with pytest.raises(ExtractionFailed) as exc_info:
        await chain.extract(_make_result(url=url))

    assert len(exc_info.value.failures) >= 2
