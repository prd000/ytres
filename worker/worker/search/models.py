from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

Tier = Literal["academic", "government", "news", "industry"]


class SearchResult(BaseModel):
    title: str
    url: str
    tier: Tier
    provider: str
    snippet: str | None = None
    raw_content: str | None = None
    published_at: str | None = None
    pdf_url: str | None = None
    metadata: dict = Field(default_factory=dict)


class ExtractedContent(BaseModel):
    url: str
    text: str
    extractor: Literal["provider", "trafilatura", "jina"]
    title: str | None = None
    word_count: int


class SearchFailure(BaseModel):
    stage: Literal["web_search", "academic_search", "extraction"]
    provider: str | None = None
    tier: Tier | None = None
    url: str | None = None
    error_type: str
    message: str
    attempts: int


class SearchResponse(BaseModel):
    results: list[SearchResult]
    failures: list[SearchFailure]
