from __future__ import annotations
from abc import ABC, abstractmethod
from .models import ExtractedContent, SearchResult, Tier


class WebSearchProvider(ABC):
    name: str

    @abstractmethod
    async def search(self, query: str, *, count: int, tier: Tier) -> list[SearchResult]: ...

    async def aclose(self) -> None:
        pass


class ContentExtractor(ABC):
    name: str

    @abstractmethod
    async def extract(self, url: str) -> ExtractedContent: ...
