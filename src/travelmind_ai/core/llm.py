from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import AsyncOpenAI

from travelmind_ai.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM interface supporting OpenAI and Ollama."""

    def __init__(self) -> None:
        if settings.llm_provider == "openai":
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
            self._model = settings.openai_model
        else:
            self._client = AsyncOpenAI(
                api_key="ollama",
                base_url=f"{settings.ollama_base_url}/v1",
            )
            self._model = settings.ollama_model

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        response = await self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return content or ""

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str]:
        """Stream chat completions, yielding content chunks."""
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for event in stream:
            delta = event.choices[0].delta
            if delta.content:
                yield delta.content

    async def close(self) -> None:
        await self._client.close()


class OllamaEmbeddingClient:
    """Direct Ollama embedding client for dev (Ollama /api/embed)."""

    def __init__(self) -> None:
        self._base_url = settings.ollama_base_url
        self._model = settings.ollama_embedding_model
        self._http = httpx.AsyncClient(timeout=60)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            resp = await self._http.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": text},
            )
            resp.raise_for_status()
            data = resp.json()
            results.append(data["embeddings"][0])
        return results

    async def close(self) -> None:
        await self._http.aclose()
