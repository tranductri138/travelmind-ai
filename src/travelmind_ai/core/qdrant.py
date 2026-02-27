from __future__ import annotations

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from travelmind_ai.config import settings

logger = logging.getLogger(__name__)

_client: AsyncQdrantClient | None = None


async def connect() -> AsyncQdrantClient:
    global _client
    _client = AsyncQdrantClient(url=settings.qdrant_url)
    await _ensure_collections()
    logger.info("Qdrant connected at %s", settings.qdrant_url)
    return _client


async def disconnect() -> None:
    global _client
    if _client:
        await _client.close()
        _client = None
    logger.info("Qdrant disconnected")


def get_client() -> AsyncQdrantClient:
    if _client is None:
        raise RuntimeError("Qdrant client not initialized — call connect() first")
    return _client


async def _ensure_collections() -> None:
    assert _client is not None
    for name in [settings.qdrant_collection_hotels, settings.qdrant_collection_reviews]:
        if not await _client.collection_exists(name):
            await _client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=settings.embedding_dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection: %s", name)
