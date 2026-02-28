from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from travelmind_ai.ai.embedding_service import delete_hotel_embeddings, delete_review_embedding


@pytest.mark.asyncio
async def test_delete_hotel_embeddings(mock_qdrant_client: AsyncMock):
    await delete_hotel_embeddings("hotel-123", mock_qdrant_client)

    mock_qdrant_client.delete.assert_called_once()
    call_kwargs = mock_qdrant_client.delete.call_args
    assert call_kwargs.kwargs["collection_name"] == "hotels"


@pytest.mark.asyncio
async def test_delete_review_embedding(mock_qdrant_client: AsyncMock):
    await delete_review_embedding("review-456", mock_qdrant_client)

    mock_qdrant_client.delete.assert_called_once()
    call_kwargs = mock_qdrant_client.delete.call_args
    assert call_kwargs.kwargs["collection_name"] == "reviews"
