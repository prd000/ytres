from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import SearchFailure


class SearchError(Exception):
    """Base error for all search failures. Carries structured failure info."""
    def __init__(self, message: str = "", failures: list["SearchFailure"] | None = None):
        super().__init__(message)
        self.failures: list["SearchFailure"] = failures or []


class ProviderUnavailable(SearchError):
    """All retry attempts exhausted for a provider."""
    def __init__(self, provider: str, attempts: int, message: str = ""):
        msg = message or f"{provider} unavailable after {attempts} attempts"
        super().__init__(msg)
        self.provider = provider
        self.attempts = attempts


class ExtractionFailed(SearchError):
    """Full extraction chain (provider → trafilatura → jina) exhausted."""
    def __init__(self, url: str, failures: list["SearchFailure"] | None = None):
        super().__init__(f"Extraction failed for {url}", failures=failures)
        self.url = url


class ConfigError(SearchError):
    """Invalid or missing configuration (e.g. missing API key)."""
