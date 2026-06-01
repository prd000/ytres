"""
worker.search — Phase 3 search infrastructure.

Public API:
    build_router(cfg)  → SearchRouter  (fan-out: web + academic)
    SearchRouter       — .search(query, tiers, *, count) → SearchResponse
    SearchConfig       — frozen dataclass; SearchConfig.from_env() loads from config.toml + env
    models             — SearchResult, ExtractedContent, SearchFailure, SearchResponse, Tier
    errors             — SearchError, ProviderUnavailable, ExtractionFailed, ConfigError
"""
from .config import SearchConfig
from .errors import ConfigError, ExtractionFailed, ProviderUnavailable, SearchError
from .models import (
    ExtractedContent,
    SearchFailure,
    SearchResponse,
    SearchResult,
    Tier,
)
from .router import SearchRouter
from .web.factory import build_web_provider
from .academic.semantic_scholar import SemanticScholarClient


def build_router(cfg: SearchConfig) -> SearchRouter:
    """Assemble a fully-wired SearchRouter from a SearchConfig."""
    web = build_web_provider(cfg.web_provider, cfg)
    academic = SemanticScholarClient(cfg)
    return SearchRouter(web_provider=web, academic_client=academic, cfg=cfg)


__all__ = [
    "SearchConfig",
    "SearchResult",
    "ExtractedContent",
    "SearchFailure",
    "SearchResponse",
    "Tier",
    "SearchError",
    "ProviderUnavailable",
    "ExtractionFailed",
    "ConfigError",
    "SearchRouter",
    "build_router",
]
