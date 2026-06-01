from __future__ import annotations
from ..config import SearchConfig
from ..models import ExtractedContent, SearchResult
from ..errors import ExtractionFailed
from .trafilatura_extractor import TrafilaturaExtractor
from .jina_extractor import JinaExtractor


class ExtractionChain:
    """Provider-aware extraction chain: raw_content short-circuit → trafilatura → Jina.

    Decision 2: if SearchResult.raw_content is present and long enough
    (>= extraction_min_words), skip the network chain entirely.
    """

    def __init__(self, cfg: SearchConfig) -> None:
        self._cfg = cfg
        self._traf = TrafilaturaExtractor()
        self._jina = JinaExtractor(cfg)

    async def extract(self, result: SearchResult) -> ExtractedContent:
        if result.raw_content:
            word_count = len(result.raw_content.split())
            if word_count >= self._cfg.extraction_min_words:
                return ExtractedContent(
                    url=result.url,
                    text=result.raw_content,
                    extractor="provider",
                    word_count=word_count,
                )

        failures = []

        try:
            return await self._traf.extract(result.url)
        except ExtractionFailed as exc:
            failures.extend(exc.failures)

        try:
            return await self._jina.extract(result.url)
        except ExtractionFailed as exc:
            failures.extend(exc.failures)

        raise ExtractionFailed(result.url, failures=failures)

    async def aclose(self) -> None:
        await self._jina.aclose()
