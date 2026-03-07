from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from travelmind_ai.config import settings
from travelmind_ai.core import qdrant, rabbitmq
from travelmind_ai.core.cache import BasicCache, CacheLayer, SemanticCache
from travelmind_ai.core.database import async_session_factory
from travelmind_ai.core.embedding import EmbeddingClient, create_embedding_client
from travelmind_ai.core.llm import LLMClient

# Singletons initialised at startup
_llm_client: LLMClient | None = None
_embedding_client: EmbeddingClient | None = None
_cache_layer: CacheLayer | None = None


def init_clients() -> None:
    global _llm_client, _embedding_client, _cache_layer
    _llm_client = LLMClient()
    _embedding_client = create_embedding_client()

    # Basic cache is always available (in-memory)
    basic = BasicCache(
        max_size=settings.cag_basic_max_size,
        default_ttl=settings.cag_basic_ttl,
    )
    _cache_layer = CacheLayer(basic=basic, semantic=None)
    logger.info("CAG BasicCache initialized (max_size=%d, ttl=%ds)", basic._max_size, basic._default_ttl)


def init_semantic_cache() -> None:
    """Initialise the semantic cache tier (requires Qdrant + embedding client).

    Called from lifespan after Qdrant is connected.
    """
    global _cache_layer
    if _cache_layer is None or _embedding_client is None:
        return

    try:
        qdrant_client = qdrant.get_client()
        semantic = SemanticCache(
            embedding_client=_embedding_client,
            qdrant_client=qdrant_client,
            similarity_threshold=settings.cag_semantic_threshold,
            default_ttl=settings.cag_semantic_ttl,
        )
        _cache_layer = CacheLayer(basic=_cache_layer._basic, semantic=semantic)
        logger.info(
            "CAG SemanticCache initialized (threshold=%.2f, ttl=%ds)",
            settings.cag_semantic_threshold,
            settings.cag_semantic_ttl,
        )
    except RuntimeError:
        logger.warning("SemanticCache not initialized — Qdrant unavailable")


async def shutdown_clients() -> None:
    if _llm_client:
        await _llm_client.close()
    if _embedding_client:
        await _embedding_client.close()


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


def get_llm_client() -> LLMClient:
    assert _llm_client is not None
    return _llm_client


def get_embedding_client() -> EmbeddingClient:
    assert _embedding_client is not None
    return _embedding_client


def get_qdrant_client() -> AsyncQdrantClient:
    return qdrant.get_client()


def get_cache_layer() -> CacheLayer | None:
    return _cache_layer


def get_rabbitmq_channel():  # noqa: ANN201
    return rabbitmq.get_channel()
