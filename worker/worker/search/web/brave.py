from __future__ import annotations
from ..base import WebSearchProvider
from ..config import SearchConfig
from ..models import SearchResult, Tier
from ..retry import make_client, with_retry


class BraveProvider(WebSearchProvider):
    name = "brave"
    _BASE_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str, cfg: SearchConfig) -> None:
        self._api_key = api_key
        self._cfg = cfg
        self._client = make_client(cfg)

    async def search(self, query: str, *, count: int, tier: Tier) -> list[SearchResult]:
        async def _do():
            resp = await self._client.get(
                self._BASE_URL,
                params={"q": query, "count": count},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self._api_key,
                },
            )
            resp.raise_for_status()
            return self._parse(resp.json(), tier)

        return await with_retry(_do, self._cfg, self.name)

    def _parse(self, data: dict, tier: Tier) -> list[SearchResult]:
        results = []
        for r in data.get("web", {}).get("results", []):
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                tier=tier,
                provider=self.name,
                snippet=r.get("description"),
                published_at=r.get("age"),
            ))
        return results

    async def aclose(self) -> None:
        await self._client.aclose()
