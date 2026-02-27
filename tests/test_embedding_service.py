from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from travelmind_ai.ai.embedding_service import embed_hotel, embed_review


@pytest.mark.asyncio
async def test_embed_hotel(sample_hotel_data: dict, mock_embedding_client: AsyncMock, mock_qdrant_client: AsyncMock):
    await embed_hotel(sample_hotel_data, mock_embedding_client, mock_qdrant_client)

    mock_embedding_client.embed.assert_called_once()
    mock_qdrant_client.upsert.assert_called_once()

    call_kwargs = mock_qdrant_client.upsert.call_args
    assert call_kwargs.kwargs["collection_name"] == "hotels"


@pytest.mark.asyncio
async def test_embed_review(sample_review_data: dict, mock_embedding_client: AsyncMock, mock_qdrant_client: AsyncMock):
    await embed_review(sample_review_data, mock_embedding_client, mock_qdrant_client)

    mock_embedding_client.embed.assert_called_once()
    mock_qdrant_client.upsert.assert_called_once()

    call_kwargs = mock_qdrant_client.upsert.call_args
    assert call_kwargs.kwargs["collection_name"] == "reviews"


@pytest.mark.asyncio
async def test_embed_review_empty_skips(mock_embedding_client: AsyncMock, mock_qdrant_client: AsyncMock):
    review = {"id": "r1", "hotel_id": "h1", "rating": 3, "title": None, "comment": None}
    await embed_review(review, mock_embedding_client, mock_qdrant_client)

    mock_embedding_client.embed.assert_not_called()
    mock_qdrant_client.upsert.assert_not_called()
