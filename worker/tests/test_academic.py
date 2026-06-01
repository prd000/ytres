"""Semantic Scholar client tests — all mocked via respx, no real network."""
import httpx
import pytest
import respx

from worker.search.academic.semantic_scholar import SemanticScholarClient
from worker.search.config import SearchConfig
from worker.search.errors import ProviderUnavailable


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


_SS_RESPONSE = {
    "data": [
        {
            "paperId": "abc123",
            "title": "Attention Is All You Need",
            "url": "https://www.semanticscholar.org/paper/abc123",
            "abstract": "The dominant sequence transduction models...",
            "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762"},
            "publicationDate": "2017-06-12",
        },
        {
            "paperId": "def456",
            "title": "No PDF Paper",
            "url": None,
            "abstract": None,
            "openAccessPdf": None,
            "publicationDate": None,
        },
    ]
}


@respx.mock
async def test_semantic_scholar_returns_results(cfg):
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json=_SS_RESPONSE)
    )
    client = SemanticScholarClient(cfg)
    results = await client.search("transformer attention", count=10)

    assert len(results) == 2
    assert results[0].title == "Attention Is All You Need"
    assert results[0].tier == "academic"
    assert results[0].provider == "semantic_scholar"
    assert results[0].pdf_url == "https://arxiv.org/pdf/1706.03762"
    assert results[0].snippet == "The dominant sequence transduction models..."
    assert results[0].metadata["paper_id"] == "abc123"


@respx.mock
async def test_semantic_scholar_no_pdf(cfg):
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json=_SS_RESPONSE)
    )
    client = SemanticScholarClient(cfg)
    results = await client.search("q", count=5)

    assert results[1].pdf_url is None
    assert "def456" in results[1].url


@respx.mock
async def test_semantic_scholar_fallback_url(cfg):
    """When paper.url is None, fall back to SS URL from paperId."""
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json=_SS_RESPONSE)
    )
    client = SemanticScholarClient(cfg)
    results = await client.search("q", count=5)

    assert "semanticscholar.org/paper/def456" in results[1].url


@respx.mock
async def test_semantic_scholar_empty_response(cfg):
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    client = SemanticScholarClient(cfg)
    results = await client.search("nothing", count=5)
    assert results == []


@respx.mock
async def test_semantic_scholar_503_raises_provider_unavailable(cfg):
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(503)
    )
    client = SemanticScholarClient(cfg)
    with pytest.raises(ProviderUnavailable) as exc_info:
        await client.search("q", count=5)
    assert exc_info.value.provider == "semantic_scholar"
