from __future__ import annotations
from ..config import SearchConfig
from ..models import SearchResult
from ..retry import make_client, with_retry


class SemanticScholarClient:
    """Keyless Semantic Scholar Graph API client — metadata + abstract + open-access PDF URL."""
    name = "semantic_scholar"
    _BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    _FIELDS = "title,url,abstract,openAccessPdf,publicationDate"

    def __init__(self, cfg: SearchConfig) -> None:
        self._cfg = cfg
        self._client = make_client(cfg)

    async def search(self, query: str, *, count: int) -> list[SearchResult]:
        async def _do():
            resp = await self._client.get(
                self._BASE_URL,
                params={"query": query, "limit": count, "fields": self._FIELDS},
            )
            resp.raise_for_status()
            return self._parse(resp.json())

        return await with_retry(_do, self._cfg, self.name)

    def _parse(self, data: dict) -> list[SearchResult]:
        results = []
        for p in data.get("data", []):
            pdf_url: str | None = None
            oap = p.get("openAccessPdf")
            if isinstance(oap, dict):
                pdf_url = oap.get("url")
            paper_id = p.get("paperId", "")
            results.append(SearchResult(
                title=p.get("title", ""),
                url=(
                    p.get("url")
                    or f"https://www.semanticscholar.org/paper/{paper_id}"
                ),
                tier="academic",
                provider=self.name,
                snippet=p.get("abstract"),
                published_at=p.get("publicationDate"),
                pdf_url=pdf_url,
                metadata={"paper_id": paper_id},
            ))
        return results

    async def aclose(self) -> None:
        await self._client.aclose()
