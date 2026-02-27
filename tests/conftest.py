from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    client = AsyncMock()
    client.chat.return_value = "Mocked LLM response"
    client.close.return_value = None
    return client


@pytest.fixture
def mock_embedding_client() -> AsyncMock:
    client = AsyncMock()
    client.embed.return_value = [[0.1] * 1536]
    client.close.return_value = None
    return client


@pytest.fixture
def mock_qdrant_client() -> AsyncMock:
    client = AsyncMock()
    client.upsert.return_value = None
    client.search.return_value = []
    client.close.return_value = None
    return client


@pytest.fixture
def sample_hotel_data() -> dict:
    return {
        "id": "hotel-123",
        "name": "Grand Palace Hotel",
        "slug": "grand-palace-hotel",
        "description": "A luxury 5-star hotel in the heart of Paris",
        "address": "1 Rue de Rivoli",
        "city": "Paris",
        "country": "France",
        "stars": 5,
        "rating": 4.8,
        "amenities": ["Pool", "Spa", "Restaurant", "WiFi"],
        "images": [],
    }


@pytest.fixture
def sample_review_data() -> dict:
    return {
        "id": "review-456",
        "user_id": "user-789",
        "hotel_id": "hotel-123",
        "rating": 5,
        "title": "Amazing stay",
        "comment": "Beautiful hotel with excellent service and great location.",
    }
