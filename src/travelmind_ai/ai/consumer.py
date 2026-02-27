from __future__ import annotations

import logging
from typing import Any

from travelmind_ai.ai.embedding_service import embed_hotel, embed_review
from travelmind_ai.core import rabbitmq
from travelmind_ai.core.qdrant import get_client as get_qdrant
from travelmind_ai.dependencies import get_embedding_client

logger = logging.getLogger(__name__)


async def _on_hotel_event(data: dict[str, Any]) -> None:
    """Handle hotel.created / hotel.updated — re-embed the hotel."""
    logger.info("Received hotel event for %s", data.get("id"))
    await embed_hotel(data, get_embedding_client(), get_qdrant())


async def _on_review_created(data: dict[str, Any]) -> None:
    """Handle review.created — embed the new review."""
    logger.info("Received review event for %s", data.get("id"))
    await embed_review(data, get_embedding_client(), get_qdrant())


async def start_ai_consumers() -> None:
    await rabbitmq.consume(
        queue_name="ai.hotel.created",
        exchange_name="travelmind",
        routing_key="hotel.created",
        callback=_on_hotel_event,
    )
    await rabbitmq.consume(
        queue_name="ai.hotel.updated",
        exchange_name="travelmind",
        routing_key="hotel.updated",
        callback=_on_hotel_event,
    )
    await rabbitmq.consume(
        queue_name="ai.review.created",
        exchange_name="travelmind",
        routing_key="review.created",
        callback=_on_review_created,
    )
    logger.info("AI consumers started")
