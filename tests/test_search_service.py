from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from travelmind_ai.ai.schemas import SearchRequest
from travelmind_ai.ai.search_service import semantic_search


def _make_hit(hotel_id: str, score: float) -> MagicMock:
    hit = MagicMock()
    hit.payload = {"hotel_id": hotel_id, "text": "some text", "city": "Paris", "country": "France", "stars": 4}
    hit.score = score
    return hit


@pytest.mark.asyncio
async def test_semantic_search_basic(mock_embedding_client: AsyncMock, mock_qdrant_client: AsyncMock):
    mock_qdrant_client.search.return_value = [
        _make_hit("hotel-1", 0.95),
        _make_hit("hotel-2", 0.85),
        _make_hit("hotel-1", 0.90),  # duplicate chunk
    ]

    request = SearchRequest(query="luxury hotel in Paris")
    response = await semantic_search(request, mock_embedding_client, mock_qdrant_client)

    assert len(response.results) == 2
    assert response.results[0].hotel_id == "hotel-1"
    assert response.results[0].score == 0.95
    assert response.results[1].hotel_id == "hotel-2"


@pytest.mark.asyncio
async def test_semantic_search_empty(mock_embedding_client: AsyncMock, mock_qdrant_client: AsyncMock):
    mock_qdrant_client.search.return_value = []

    request = SearchRequest(query="nonexistent place")
    response = await semantic_search(request, mock_embedding_client, mock_qdrant_client)

    assert len(response.results) == 0


@pytest.mark.asyncio
async def test_semantic_search_with_filters(mock_embedding_client: AsyncMock, mock_qdrant_client: AsyncMock):
    mock_qdrant_client.search.return_value = [_make_hit("hotel-1", 0.9)]

    request = SearchRequest(query="beach resort", city="Bali", min_stars=4, limit=5)
    response = await semantic_search(request, mock_embedding_client, mock_qdrant_client)

    # Verify filter was passed
    call_kwargs = mock_qdrant_client.search.call_args.kwargs
    assert call_kwargs["query_filter"] is not None
    assert len(response.results) == 1
