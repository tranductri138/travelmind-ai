from __future__ import annotations

from collections.abc import AsyncGenerator

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from travelmind_ai.core import qdrant, rabbitmq
from travelmind_ai.core.database import async_session_factory
from travelmind_ai.core.embedding import EmbeddingClient, create_embedding_client
from travelmind_ai.core.llm import LLMClient

# Singletons initialised at startup
_llm_client: LLMClient | None = None
_embedding_client: EmbeddingClient | None = None


def init_clients() -> None:
    global _llm_client, _embedding_client
    _llm_client = LLMClient()
    _embedding_client = create_embedding_client()


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


def get_rabbitmq_channel():  # noqa: ANN201
    return rabbitmq.get_channel()
