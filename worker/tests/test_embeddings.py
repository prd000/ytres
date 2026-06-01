"""
Unit tests for worker.storage.embeddings — fake AsyncOpenAI client, no real API calls.
"""
from __future__ import annotations
import math
import pytest
from unittest.mock import AsyncMock, MagicMock

from worker.storage.embeddings import Embedder, _BATCH_SIZE
from worker.llm.config import LLMConfig


DIMS = 1536


@pytest.fixture
def cfg() -> LLMConfig:
    return LLMConfig(
        base_url="https://api.deepseek.com/v1",
        coordinator_model="deepseek-v4-pro",
        worker_model="deepseek-v4-pro",
        classifier_model="deepseek-v4-flash",
        temperature=0.2,
        timeout=120.0,
        max_retries=3,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=DIMS,
        deepseek_api_key=None,
        openai_api_key=None,
    )


def _make_client(n_texts_per_call: int | None = None) -> tuple[MagicMock, list[int]]:
    """Return (fake_client, call_sizes) where call_sizes tracks input lengths per call."""
    call_sizes: list[int] = []

    async def fake_create(**kwargs):
        batch = kwargs["input"]
        call_sizes.append(len(batch))
        data = [MagicMock(embedding=[0.1] * DIMS) for _ in batch]
        return MagicMock(data=data)

    client = MagicMock()
    client.embeddings.create = AsyncMock(side_effect=fake_create)
    return client, call_sizes


async def test_embed_returns_correct_dimensions(cfg):
    client, _ = _make_client()
    embedder = Embedder(cfg, client=client)
    results = await embedder.embed_texts(["hello", "world"])
    assert len(results) == 2
    assert all(len(v) == DIMS for v in results)


async def test_embed_preserves_order(cfg):
    sentinel_vecs = [[float(i)] * DIMS for i in range(5)]
    idx = 0

    async def fake_create(**kwargs):
        nonlocal idx
        batch = kwargs["input"]
        data = []
        for _ in batch:
            data.append(MagicMock(embedding=sentinel_vecs[idx]))
            idx += 1
        return MagicMock(data=data)

    client = MagicMock()
    client.embeddings.create = AsyncMock(side_effect=fake_create)
    embedder = Embedder(cfg, client=client)
    results = await embedder.embed_texts([f"text {i}" for i in range(5)])

    assert len(results) == 5
    for i, vec in enumerate(results):
        assert vec[0] == float(i)


async def test_embed_empty_list_makes_no_api_call(cfg):
    client, call_sizes = _make_client()
    embedder = Embedder(cfg, client=client)
    results = await embedder.embed_texts([])
    assert results == []
    assert call_sizes == []


async def test_batching_300_texts(cfg):
    client, call_sizes = _make_client()
    embedder = Embedder(cfg, client=client)
    results = await embedder.embed_texts(["text"] * 300)

    expected_calls = math.ceil(300 / _BATCH_SIZE)
    assert len(call_sizes) == expected_calls
    assert sum(call_sizes) == 300
    assert len(results) == 300


async def test_single_text(cfg):
    client, call_sizes = _make_client()
    embedder = Embedder(cfg, client=client)
    results = await embedder.embed_texts(["single"])
    assert len(results) == 1
    assert len(results[0]) == DIMS
    assert call_sizes == [1]
