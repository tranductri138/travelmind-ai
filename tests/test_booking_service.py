from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from travelmind_ai.booking.service import (
    build_booking_text,
    delete_booking_embedding,
    embed_booking,
)


@pytest.mark.asyncio
async def test_embed_booking(
    sample_booking_data: dict,
    mock_embedding_client: AsyncMock,
    mock_qdrant_client: AsyncMock,
):
    await embed_booking(sample_booking_data, mock_embedding_client, mock_qdrant_client)

    mock_embedding_client.embed.assert_called_once()
    mock_qdrant_client.upsert.assert_called_once()

    call_kwargs = mock_qdrant_client.upsert.call_args
    assert call_kwargs.kwargs["collection_name"] == "bookings"


@pytest.mark.asyncio
async def test_delete_booking_embedding(mock_qdrant_client: AsyncMock):
    await delete_booking_embedding("booking-001", mock_qdrant_client)

    mock_qdrant_client.delete.assert_called_once()
    call_kwargs = mock_qdrant_client.delete.call_args
    assert call_kwargs.kwargs["collection_name"] == "bookings"


def test_build_booking_text():
    text = build_booking_text(
        hotel_name="Grand Palace Hotel",
        hotel_city="Paris",
        hotel_country="France",
        check_in="2026-03-15",
        check_out="2026-03-20",
        guests=2,
        total_price=750.00,
        currency="USD",
        status="CONFIRMED",
    )
    assert "Grand Palace Hotel" in text
    assert "Paris" in text
    assert "CONFIRMED" in text
    assert "750.0" in text


def test_build_booking_text_minimal():
    text = build_booking_text(
        hotel_name=None,
        hotel_city=None,
        hotel_country=None,
        check_in="2026-03-15",
        check_out="2026-03-20",
        guests=1,
        total_price=100.00,
        currency="EUR",
        status="PENDING",
    )
    assert "Hotel:" not in text
    assert "Location:" not in text
    assert "2026-03-15" in text
    assert "PENDING" in text
    assert "100.0" in text
