"""Contract tests for Phase 3 search models. No network, no DB."""
import pytest
from pydantic import ValidationError

from worker.search.models import (
    ExtractedContent,
    SearchFailure,
    SearchResponse,
    SearchResult,
)


def test_search_result_required_fields():
    r = SearchResult(title="Test", url="https://example.com", tier="academic", provider="ss")
    assert r.tier == "academic"
    assert r.provider == "ss"


def test_search_result_defaults():
    r = SearchResult(title="T", url="u", tier="news", provider="brave")
    assert r.snippet is None
    assert r.raw_content is None
    assert r.pdf_url is None
    assert r.published_at is None
    assert r.metadata == {}


def test_invalid_tier_raises():
    with pytest.raises(ValidationError):
        SearchResult(title="T", url="u", tier="invalid_tier", provider="x")


def test_search_result_with_raw_content():
    r = SearchResult(
        title="T", url="u", tier="industry", provider="tavily",
        raw_content="some extracted body text here",
    )
    assert r.raw_content == "some extracted body text here"


def test_search_failure_json_round_trip():
    f = SearchFailure(
        stage="web_search",
        provider="brave",
        tier="news",
        error_type="ProviderUnavailable",
        message="brave unavailable after 4 attempts",
        attempts=4,
    )
    f2 = SearchFailure.model_validate_json(f.model_dump_json())
    assert f2.attempts == 4
    assert f2.provider == "brave"
    assert f2.tier == "news"


def test_search_failure_nullable_fields():
    f = SearchFailure(
        stage="extraction",
        provider=None,
        tier=None,
        url="https://example.com",
        error_type="EmptyContent",
        message="no text",
        attempts=1,
    )
    assert f.provider is None
    assert f.tier is None


def test_search_response_partial_results():
    r = SearchResponse(
        results=[SearchResult(title="A", url="u", tier="academic", provider="ss")],
        failures=[
            SearchFailure(
                stage="web_search", provider="brave", tier="news",
                error_type="ProviderUnavailable", message="down", attempts=4,
            )
        ],
    )
    assert len(r.results) == 1
    assert len(r.failures) == 1


def test_search_response_empty():
    r = SearchResponse(results=[], failures=[])
    assert r.results == []
    assert r.failures == []


def test_extracted_content_fields():
    c = ExtractedContent(
        url="https://example.com",
        text="hello world and more words here",
        extractor="trafilatura",
        title="Hello",
        word_count=6,
    )
    assert c.extractor == "trafilatura"
    assert c.word_count == 6
    assert c.title == "Hello"


def test_extracted_content_optional_title():
    c = ExtractedContent(url="u", text="text", extractor="jina", word_count=1)
    assert c.title is None


def test_invalid_extractor_raises():
    with pytest.raises(ValidationError):
        ExtractedContent(url="u", text="t", extractor="unknown", word_count=1)
