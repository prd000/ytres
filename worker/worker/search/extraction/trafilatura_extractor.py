from __future__ import annotations
import asyncio
import trafilatura
from ..base import ContentExtractor
from ..models import ExtractedContent, SearchFailure
from ..errors import ExtractionFailed


class TrafilaturaExtractor(ContentExtractor):
    """Sync trafilatura library wrapped via asyncio.to_thread."""
    name = "trafilatura"

    async def extract(self, url: str) -> ExtractedContent:
        def _sync() -> tuple[str | None, str | None]:
            html = trafilatura.fetch_url(url)
            if not html:
                return None, None
            text = trafilatura.extract(html)
            meta = trafilatura.extract_metadata(html)
            title = meta.title if (meta and hasattr(meta, "title")) else None
            return text, title

        text, title = await asyncio.to_thread(_sync)

        if not text:
            raise ExtractionFailed(url, failures=[
                SearchFailure(
                    stage="extraction",
                    provider=self.name,
                    tier=None,
                    url=url,
                    error_type="EmptyContent",
                    message="trafilatura returned empty content",
                    attempts=1,
                )
            ])

        return ExtractedContent(
            url=url,
            text=text,
            extractor="trafilatura",
            title=title,
            word_count=len(text.split()),
        )
