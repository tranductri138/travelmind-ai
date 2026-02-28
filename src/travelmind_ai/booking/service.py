from __future__ import annotations

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from travelmind_ai.config import settings
from travelmind_ai.core.embedding import EmbeddingClient

logger = logging.getLogger(__name__)


def build_booking_text(
    hotel_name: str | None,
    hotel_city: str | None,
    hotel_country: str | None,
    check_in: str,
    check_out: str,
    guests: int,
    total_price: float,
    currency: str,
    status: str,
) -> str:
    """Build a searchable text representation for a booking."""
    parts: list[str] = []
    if hotel_name:
        parts.append(f"Hotel: {hotel_name}")
    location_parts = [p for p in [hotel_city, hotel_country] if p]
    if location_parts:
        parts.append(f"Location: {', '.join(location_parts)}")
    parts.append(f"Check-in: {check_in}, Check-out: {check_out}")
    parts.append(f"Guests: {guests}")
    parts.append(f"Price: {total_price} {currency}")
    parts.append(f"Status: {status}")
    return " | ".join(parts)


async def embed_booking(
    booking_data: dict,
    embedding_client: EmbeddingClient,
    qdrant_client: AsyncQdrantClient,
) -> None:
    """Generate embedding for a booking and upsert into Qdrant."""
    text = build_booking_text(
        hotel_name=booking_data.get("hotel_name"),
        hotel_city=booking_data.get("hotel_city"),
        hotel_country=booking_data.get("hotel_country"),
        check_in=booking_data["check_in"],
        check_out=booking_data["check_out"],
        guests=booking_data["guests"],
        total_price=booking_data["total_price"],
        currency=booking_data.get("currency", "USD"),
        status=booking_data.get("status", "PENDING"),
    )

    vectors = await embedding_client.embed([text])

    point = PointStruct(
        id=booking_data["id"],
        vector=vectors[0],
        payload={
            "booking_id": booking_data["id"],
            "user_id": booking_data["user_id"],
            "room_id": booking_data["room_id"],
            "hotel_name": booking_data.get("hotel_name"),
            "hotel_city": booking_data.get("hotel_city"),
            "status": booking_data.get("status", "PENDING"),
            "text": text,
        },
    )

    await qdrant_client.upsert(
        collection_name=settings.qdrant_collection_bookings,
        points=[point],
    )
    logger.info("Embedded booking %s", booking_data["id"])


async def delete_booking_embedding(
    booking_id: str,
    qdrant_client: AsyncQdrantClient,
) -> None:
    """Delete the embedding for a booking from Qdrant."""
    await qdrant_client.delete(
        collection_name=settings.qdrant_collection_bookings,
        points_selector=Filter(
            must=[FieldCondition(key="booking_id", match=MatchValue(value=booking_id))]
        ),
    )
    logger.info("Deleted embedding for booking %s", booking_id)
