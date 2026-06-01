from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING

from .config import SearchConfig
from .errors import ProviderUnavailable, SearchError
from .models import SearchFailure, SearchResponse, SearchResult, Tier

if TYPE_CHECKING:
    from .academic.semantic_scholar import SemanticScholarClient
    from .base import WebSearchProvider

# Maps each tier to which backend handles it.
TIER_ROUTING: dict[str, str] = {
    "academic":    "academic",
    "government":  "web",
    "news":        "web",
    "industry":    "web",
    "social_media": "web",
}


class SearchRouter:
    """Fan-out router: academic → Semantic Scholar, web tiers → web provider.

    v1: single web call (first web tier) regardless of how many web tiers are
    requested. Partial failures (one backend down) are captured in SearchResponse.failures
    rather than raising, allowing callers to consume partial results. All backends down
    → raises SearchError.
    """

    def __init__(
        self,
        web_provider: "WebSearchProvider",
        academic_client: "SemanticScholarClient",
        cfg: SearchConfig,
    ) -> None:
        self._web = web_provider
        self._academic = academic_client
        self._cfg = cfg

    async def search(
        self,
        query: str,
        tiers: list[Tier],
        *,
        count: int | None = None,
    ) -> SearchResponse:
        count = count or self._cfg.results_per_query

        # De-duplicate tiers, preserve order.
        seen: set[str] = set()
        unique_tiers: list[Tier] = []
        for t in tiers:
            if t not in seen:
                seen.add(t)
                unique_tiers.append(t)

        needs_academic = "academic" in unique_tiers
        web_tiers = [t for t in unique_tiers if TIER_ROUTING.get(t) == "web"]

        # Build concurrent coroutines.
        coros = []
        labels: list[str] = []
        if needs_academic:
            coros.append(self._academic.search(query, count=count))
            labels.append("academic")
        if web_tiers:
            # v1: single call tagged with first web tier
            coros.append(self._web.search(query, count=count, tier=web_tiers[0]))
            labels.append("web")

        if not coros:
            return SearchResponse(results=[], failures=[])

        gathered = await asyncio.gather(*coros, return_exceptions=True)

        all_results: list[SearchResult] = []
        all_failures: list[SearchFailure] = []

        for label, outcome in zip(labels, gathered):
            if isinstance(outcome, Exception):
                exc = outcome
                provider = exc.provider if isinstance(exc, ProviderUnavailable) else None
                attempts = exc.attempts if isinstance(exc, ProviderUnavailable) else 1
                stage = "academic_search" if label == "academic" else "web_search"
                tier_tag: Tier | None = (
                    "academic" if label == "academic"
                    else (web_tiers[0] if web_tiers else None)
                )
                all_failures.append(SearchFailure(
                    stage=stage,
                    provider=provider,
                    tier=tier_tag,
                    error_type=type(exc).__name__,
                    message=str(exc),
                    attempts=attempts,
                ))
            else:
                all_results.extend(outcome)  # type: ignore[arg-type]

        # All backends failed → raise so callers know no results are available.
        if all(isinstance(o, Exception) for o in gathered):
            raise SearchError("All search providers failed", failures=all_failures)

        return SearchResponse(results=all_results, failures=all_failures)

    async def aclose(self) -> None:
        await self._web.aclose()
        await self._academic.aclose()
