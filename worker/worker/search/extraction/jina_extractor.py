from __future__ import annotations
import httpx
from ..base import ContentExtractor
from ..config import SearchConfig
from ..models import ExtractedContent, SearchFailure
from ..errors import ExtractionFailed, ProviderUnavailable
from ..retry import make_client, with_retry


class JinaExtractor(ContentExtractor):
    """Async Jina Reader fallback extractor (https://r.jina.ai/{url})."""
    name = "jina"
    _BASE_URL = "https://r.jina.ai/"

    def __init__(self, cfg: SearchConfig) -> None:
        self._cfg = cfg
        self._client = make_client(cfg)

    async def extract(self, url: str) -> ExtractedContent:
        async def _do() -> str:
            headers: dict[str, str] = {"Accept": "text/plain"}
            if self._cfg.jina_api_key:
                headers["Authorization"] = f"Bearer {self._cfg.jina_api_key}"
            resp = await self._client.get(self._BASE_URL + url, headers=headers)
            resp.raise_for_status()
            return resp.text.strip()

        try:
            text = await with_retry(_do, self._cfg, self.name)
        except ProviderUnavailable as exc:
            raise ExtractionFailed(url, failures=[
                SearchFailure(
                    stage="extraction",
                    provider=self.name,
                    tier=None,
                    url=url,
                    error_type="ProviderUnavailable",
                    message=str(exc),
                    attempts=exc.attempts,
                )
            ]) from exc
        except httpx.HTTPStatusError as exc:
            raise ExtractionFailed(url, failures=[
                SearchFailure(
                    stage="extraction",
                    provider=self.name,
                    tier=None,
                    url=url,
                    error_type=f"HTTPStatusError({exc.response.status_code})",
                    message=str(exc),
                    attempts=1,
                )
            ]) from exc

        if not text:
            raise ExtractionFailed(url, failures=[
                SearchFailure(
                    stage="extraction",
                    provider=self.name,
                    tier=None,
                    url=url,
                    error_type="EmptyContent",
                    message="Jina returned empty content",
                    attempts=1,
                )
            ])

        return ExtractedContent(
            url=url,
            text=text,
            extractor="jina",
            word_count=len(text.split()),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
