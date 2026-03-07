from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

from travelmind_ai.ai.schemas import HotelScore, SearchRequest, SearchResponse
from travelmind_ai.config import settings
from travelmind_ai.core.embedding import EmbeddingClient


async def semantic_search(
    request: SearchRequest,
    embedding_client: EmbeddingClient,
    qdrant_client: AsyncQdrantClient,
) -> SearchResponse:
    """Embed the query and search Qdrant for matching hotels."""
    vectors = await embedding_client.embed([request.query])
    query_vector = vectors[0]

    # Build optional filters
    conditions = []
    if request.city:
        conditions.append(FieldCondition(key="city", match=MatchValue(value=request.city)))
    if request.country:
        conditions.append(FieldCondition(key="country", match=MatchValue(value=request.country)))
    if request.min_stars is not None:
        conditions.append(FieldCondition(key="stars", range=Range(gte=request.min_stars)))

    query_filter = Filter(must=conditions) if conditions else None

    results_response = await qdrant_client.query_points(
        collection_name=settings.qdrant_collection_hotels,
        query=query_vector,
        query_filter=query_filter,
        limit=request.limit * 2,  # fetch extra to deduplicate chunks
    )

    # Deduplicate by hotel_id, keeping best score
    seen: dict[str, float] = {}
    for hit in results_response.points:
        hotel_id = hit.payload["hotel_id"]  # type: ignore[index]
        if hotel_id not in seen or hit.score > seen[hotel_id]:
            seen[hotel_id] = hit.score

    results = sorted(
        [HotelScore(hotel_id=hid, score=score) for hid, score in seen.items()],
        key=lambda x: x.score,
        reverse=True,
    )[: request.limit]

    return SearchResponse(results=results, query=request.query)


async def find_similar(
    hotel_id: str,
    limit: int,
    qdrant_client: AsyncQdrantClient,
) -> list[HotelScore]:
    """Find hotels similar to the given hotel_id using its existing vector."""
    results = await qdrant_client.query_points(
        collection_name=settings.qdrant_collection_hotels,
        query=hotel_id,
        limit=limit + 5,
    )

    seen: dict[str, float] = {}
    for point in results.points:
        pid = point.payload["hotel_id"]  # type: ignore[index]
        if pid == hotel_id:
            continue
        if pid not in seen or point.score > seen[pid]:
            seen[pid] = point.score

    return sorted(
        [HotelScore(hotel_id=hid, score=score) for hid, score in seen.items()],
        key=lambda x: x.score,
        reverse=True,
    )[:limit]
