"""Cache-Augmented Generation (CAG) layer.

Two tiers:
1. **BasicCache** — in-memory LRU with TTL. Exact-match on normalised query string.
   "What is Langchain?" == "what is langchain?" → cache hit, zero cost.

2. **SemanticCache** — Qdrant vector similarity. Finds queries with the *same meaning*
   even if worded differently (cosine ≥ threshold).
   "What is Langchain?" ≈ "Explain me about Langchain?" → cache hit, one embed call.

CacheLayer combines both: basic first (free), then semantic (one embed call),
then LLM only on full miss.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections import OrderedDict

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

from travelmind_ai.core.embedding import EmbeddingClient

logger = logging.getLogger(__name__)

CACHE_COLLECTION = "response_cache"


# ---------------------------------------------------------------------------
# Basic Cache — in-memory exact match
# ---------------------------------------------------------------------------

class BasicCache:
    """In-memory LRU cache with TTL. O(1) lookup on normalised query strings."""

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600) -> None:
        self._store: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl

    @staticmethod
    def _normalize(key: str) -> str:
        """Lowercase, collapse whitespace, strip punctuation at edges."""
        key = key.strip().lower()
        key = re.sub(r"\s+", " ", key)
        return key

    def get(self, key: str) -> str | None:
        normalized = self._normalize(key)
        entry = self._store.get(normalized)
        if entry is None:
            return None
        response, expires_at = entry
        if time.time() > expires_at:
            del self._store[normalized]
            return None
        # Move to end (most recently used)
        self._store.move_to_end(normalized)
        return response

    def set(self, key: str, response: str, ttl: int | None = None) -> None:
        normalized = self._normalize(key)
        expires_at = time.time() + (ttl or self._default_ttl)
        self._store[normalized] = (response, expires_at)
        self._store.move_to_end(normalized)
        # Evict LRU entries if over capacity
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def invalidate(self, key: str) -> None:
        normalized = self._normalize(key)
        self._store.pop(normalized, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Semantic Cache — Qdrant vector similarity
# ---------------------------------------------------------------------------

class SemanticCache:
    """Vector-similarity cache backed by Qdrant.

    Stores (query_embedding, response) pairs. On lookup, embeds the new query
    and searches for the nearest cached query. If cosine similarity ≥ threshold,
    returns the cached response.
    """

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        qdrant_client: AsyncQdrantClient,
        similarity_threshold: float = 0.95,
        default_ttl: int = 3600,
    ) -> None:
        self._embedding = embedding_client
        self._qdrant = qdrant_client
        self._threshold = similarity_threshold
        self._default_ttl = default_ttl

    async def get(self, query: str) -> str | None:
        """Look up a semantically similar cached response."""
        try:
            vectors = await self._embedding.embed([query])
            results_response = await self._qdrant.query_points(
                collection_name=CACHE_COLLECTION,
                query=vectors[0],
                limit=1,
            )
        except Exception:
            logger.debug("Semantic cache lookup failed", exc_info=True)
            return None

        if not results_response.points:
            return None

        best = results_response.points[0]
        if best.score < self._threshold:
            return None

        # Check TTL
        payload = best.payload or {}
        created_at = payload.get("created_at", 0)
        ttl = payload.get("ttl", self._default_ttl)
        if time.time() - created_at > ttl:
            # Expired — remove stale entry
            try:
                await self._qdrant.delete(
                    collection_name=CACHE_COLLECTION,
                    points_selector=[best.id],
                )
            except Exception:
                pass
            return None

        logger.info(
            "Semantic cache HIT (score=%.3f, query='%s')",
            best.score,
            payload.get("query", "")[:60],
        )
        return payload.get("response")

    async def set(self, query: str, response: str, ttl: int | None = None) -> None:
        """Cache a query-response pair as a vector in Qdrant."""
        try:
            vectors = await self._embedding.embed([query])
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, query.strip().lower()))

            await self._qdrant.upsert(
                collection_name=CACHE_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vectors[0],
                        payload={
                            "query": query[:500],
                            "response": response,
                            "created_at": time.time(),
                            "ttl": ttl or self._default_ttl,
                        },
                    )
                ],
            )
        except Exception:
            logger.debug("Semantic cache write failed", exc_info=True)


# ---------------------------------------------------------------------------
# Combined Cache Layer
# ---------------------------------------------------------------------------

class CacheLayer:
    """Two-tier cache: BasicCache (free) → SemanticCache (1 embed call) → LLM.

    Usage::

        cached = await cache.get(query)
        if cached:
            return cached          # HIT — no LLM cost

        response = await run_llm(query)
        await cache.set(query, response)  # MISS — cache for next time
    """

    def __init__(
        self,
        basic: BasicCache,
        semantic: SemanticCache | None = None,
    ) -> None:
        self._basic = basic
        self._semantic = semantic

    async def get(self, query: str) -> tuple[str | None, str]:
        """Check cache. Returns (response_or_None, cache_status).

        cache_status is one of: "basic_hit", "semantic_hit", "miss"
        """
        # Tier 1: Exact match (free, O(1))
        cached = self._basic.get(query)
        if cached is not None:
            logger.info("BasicCache HIT: '%s'", query[:60])
            return cached, "basic_hit"

        # Tier 2: Semantic match (1 embedding call)
        if self._semantic is not None:
            cached = await self._semantic.get(query)
            if cached is not None:
                # Promote to basic cache for future exact matches
                self._basic.set(query, cached)
                return cached, "semantic_hit"

        return None, "miss"

    async def set(self, query: str, response: str, ttl: int | None = None) -> None:
        """Write to both cache tiers."""
        self._basic.set(query, response, ttl=ttl)
        if self._semantic is not None:
            await self._semantic.set(query, response, ttl=ttl)

    def invalidate_basic(self, query: str) -> None:
        """Remove an exact-match entry from basic cache."""
        self._basic.invalidate(query)

    def clear_basic(self) -> None:
        """Clear the entire basic cache."""
        self._basic.clear()

    @property
    def basic_size(self) -> int:
        return self._basic.size
