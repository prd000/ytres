"""
SearchConfig — assembled from config.toml [search] table and env vars.

Kept separate from worker.config so it can be constructed in tests without
requiring SUPABASE_DB_URL (which worker.config raises on if missing).
"""
from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SearchConfig:
    web_provider: str
    web_fallback_provider: str
    results_per_query: int
    timeout: float
    max_retries: int
    backoff_base: float
    backoff_max: float
    extraction_timeout: float
    extraction_min_words: int
    brave_api_key: str | None
    tavily_api_key: str | None
    jina_api_key: str | None

    @classmethod
    def from_env(cls) -> "SearchConfig":
        """Load from config.toml [search] + environment variables."""
        cfg_path = Path(__file__).parent.parent.parent.parent / "config.toml"
        with open(cfg_path, "rb") as f:
            cfg = tomllib.load(f)
        s = cfg.get("search", {})
        return cls(
            web_provider=s.get("web_provider", "brave"),
            web_fallback_provider=s.get("web_fallback_provider", ""),
            results_per_query=s.get("results_per_query", 10),
            timeout=s.get("timeout", 20.0),
            max_retries=s.get("max_retries", 4),
            backoff_base=s.get("backoff_base", 0.5),
            backoff_max=s.get("backoff_max", 30.0),
            extraction_timeout=s.get("extraction_timeout", 30.0),
            extraction_min_words=s.get("extraction_min_words", 50),
            brave_api_key=os.environ.get("BRAVE_SEARCH_API_KEY"),
            tavily_api_key=os.environ.get("TAVILY_API_KEY"),
            jina_api_key=os.environ.get("JINA_API_KEY"),
        )
