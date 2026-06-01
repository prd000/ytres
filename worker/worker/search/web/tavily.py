from __future__ import annotations
from ..base import WebSearchProvider
from ..config import SearchConfig
from ..models import SearchResult, Tier
from ..retry import make_client, with_retry


class TavilyProvider(WebSearchProvider):
    name = "tavily"
    _BASE_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str, cfg: SearchConfig) -> None:
        self._api_key = api_key
        self._cfg = cfg
        self._client = make_client(cfg)

    async def search(self, query: str, *, count: int, tier: Tier) -> list[SearchResult]:
        async def _do():
            resp = await self._client.post(
                self._BASE_URL,
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": count,
                    "include_raw_content": True,
                },
            )
            resp.raise_for_status()
            return self._parse(resp.json(), tier)

        return await with_retry(_do, self._cfg, self.name)

    def _parse(self, data: dict, tier: Tier) -> list[SearchResult]:
        results = []
        for r in data.get("results", []):
            raw = r.get("raw_content") or None
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                tier=tier,
                provider=self.name,
                snippet=r.get("content"),
                raw_content=raw,
                published_at=r.get("published_date"),
            ))
        return results

    async def aclose(self) -> None:
        await self._client.aclose()
