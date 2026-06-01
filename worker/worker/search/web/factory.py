from __future__ import annotations
from ..base import WebSearchProvider
from ..config import SearchConfig
from ..errors import ConfigError
from .brave import BraveProvider
from .tavily import TavilyProvider


def build_web_provider(name: str, cfg: SearchConfig) -> WebSearchProvider:
    """Instantiate the named web-search provider from config. Raises ConfigError on
    unknown name or missing API key."""
    if name == "brave":
        if not cfg.brave_api_key:
            raise ConfigError(
                "BRAVE_SEARCH_API_KEY is required for the 'brave' provider"
            )
        return BraveProvider(api_key=cfg.brave_api_key, cfg=cfg)
    if name == "tavily":
        if not cfg.tavily_api_key:
            raise ConfigError(
                "TAVILY_API_KEY is required for the 'tavily' provider"
            )
        return TavilyProvider(api_key=cfg.tavily_api_key, cfg=cfg)
    raise ConfigError(
        f"Unknown web provider: {name!r}. Expected 'brave' or 'tavily'."
    )
