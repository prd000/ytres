"""
OpenAI embeddings wrapper — deterministic plumbing, not traced reasoning.

Uses the raw openai SDK (not LangChain) since embeddings are not agentic
steps. Injectable client for testing.
"""
from __future__ import annotations
import logging
from typing import Any

from openai import AsyncOpenAI

from worker.llm.config import LLMConfig

log = logging.getLogger(__name__)

_BATCH_SIZE = 128


class Embedder:
    """Wraps AsyncOpenAI embeddings API with batching and dimension assertion."""

    def __init__(self, cfg: LLMConfig, client: Any | None = None) -> None:
        self._cfg = cfg
        self._client: Any = client or AsyncOpenAI(api_key=cfg.openai_api_key)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, batched at most _BATCH_SIZE per request.

        Returns a list of float vectors in the same order as the input.
        Empty input returns immediately without any API call.
        Each vector is asserted to have embedding_dimensions floats.
        """
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)

        for batch_start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[batch_start : batch_start + _BATCH_SIZE]
            response = await self._client.embeddings.create(
                model=self._cfg.embedding_model,
                input=batch,
            )
            for j, item in enumerate(response.data):
                vec = item.embedding
                assert len(vec) == self._cfg.embedding_dimensions, (
                    f"Expected {self._cfg.embedding_dimensions} dims, got {len(vec)}"
                )
                results[batch_start + j] = vec

        return results  # type: ignore[return-value]
