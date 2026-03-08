from __future__ import annotations

from typing import Any

from loguru import logger

from travelmind_ai.booking.service import delete_booking_embedding, embed_booking
from travelmind_ai.core import rabbitmq
from travelmind_ai.core.qdrant import get_client as get_qdrant
from travelmind_ai.dependencies import get_embedding_client


async def _publish_analytics(data: dict[str, Any], action: str) -> None:
    """Publish a booking analytics event."""
    await rabbitmq.publish(
        exchange_name="travelmind",
        routing_key="booking.analytics",
        body={
            "booking_id": data["id"],
            "action": action,
            "user_id": data["user_id"],
            "room_id": data["room_id"],
            "check_in": data["check_in"],
            "check_out": data["check_out"],
            "guests": data["guests"],
            "total_price": data["total_price"],
            "currency": data.get("currency", "USD"),
            "status": data.get("status", "PENDING"),
            "hotel_name": data.get("hotel_name"),
            "hotel_city": data.get("hotel_city"),
            "hotel_country": data.get("hotel_country"),
        },
    )


async def _on_booking_created(data: dict[str, Any]) -> None:
    """Handle booking.created — embed booking and publish analytics."""
    logger.info(f"Received booking.created for {data.get('id')}")
    await embed_booking(data, get_embedding_client(), get_qdrant())
    await _publish_analytics(data, action="created")


async def _on_booking_confirmed(data: dict[str, Any]) -> None:
    """Handle booking.confirmed — re-embed with updated status and publish analytics."""
    logger.info(f"Received booking.confirmed for {data.get('id')}")
    data["status"] = "CONFIRMED"
    await embed_booking(data, get_embedding_client(), get_qdrant())
    await _publish_analytics(data, action="confirmed")


async def _on_booking_cancelled(data: dict[str, Any]) -> None:
    """Handle booking.cancelled — delete from Qdrant and publish analytics."""
    booking_id = data.get("id")
    if not booking_id:
        logger.warning("booking.cancelled event missing id field")
        return
    logger.info(f"Received booking.cancelled for {booking_id}")
    await delete_booking_embedding(booking_id, get_qdrant())
    data["status"] = "CANCELLED"
    await _publish_analytics(data, action="cancelled")


async def start_booking_consumers() -> None:
    await rabbitmq.consume(
        queue_name="ai.booking.created",
        exchange_name="travelmind",
        routing_key="booking.created",
        callback=_on_booking_created,
    )
    await rabbitmq.consume(
        queue_name="ai.booking.confirmed",
        exchange_name="travelmind",
        routing_key="booking.confirmed",
        callback=_on_booking_confirmed,
    )
    await rabbitmq.consume(
        queue_name="ai.booking.cancelled",
        exchange_name="travelmind",
        routing_key="booking.cancelled",
        callback=_on_booking_cancelled,
    )
    logger.info("Booking consumers started")
