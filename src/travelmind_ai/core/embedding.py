from __future__ import annotations

import logging
from typing import Protocol

from openai import AsyncOpenAI

from travelmind_ai.config import settings
from travelmind_ai.core.llm import OllamaEmbeddingClient

logger = logging.getLogger(__name__)


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def close(self) -> None: ...


class OpenAIEmbeddingClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]

    async def close(self) -> None:
        await self._client.close()


class AlibabaEmbeddingClient:
    """Alibaba Cloud DashScope embedding client (OpenAI-compatible endpoint)."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.alibaba_api_key,
            base_url=settings.alibaba_base_url,
        )
        self._model = settings.alibaba_embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]

    async def close(self) -> None:
        await self._client.close()


def create_embedding_client() -> EmbeddingClient:
    if settings.llm_provider == "openai":
        return OpenAIEmbeddingClient()
    if settings.llm_provider == "alibaba":
        return AlibabaEmbeddingClient()
    return OllamaEmbeddingClient()
