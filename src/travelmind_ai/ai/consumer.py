from __future__ import annotations

from typing import Any

from loguru import logger

from travelmind_ai.ai.embedding_service import (
    delete_hotel_embeddings,
    delete_review_embedding,
    embed_hotel,
    embed_review,
)
from travelmind_ai.core import rabbitmq
from travelmind_ai.core.qdrant import get_client as get_qdrant
from travelmind_ai.dependencies import get_embedding_client


async def _on_hotel_event(data: dict[str, Any]) -> None:
    """Handle hotel.created / hotel.updated — re-embed the hotel."""
    logger.info("Received hotel event for %s", data.get("id"))
    await embed_hotel(data, get_embedding_client(), get_qdrant())


async def _on_review_created(data: dict[str, Any]) -> None:
    """Handle review.created — embed the new review."""
    logger.info("Received review event for %s", data.get("id"))
    await embed_review(data, get_embedding_client(), get_qdrant())


async def _on_hotel_deleted(data: dict[str, Any]) -> None:
    """Handle hotel.deleted — remove hotel embeddings from Qdrant."""
    hotel_id = data.get("id")
    if not hotel_id:
        logger.warning("hotel.deleted event missing id field")
        return
    logger.info("Received hotel.deleted for %s", hotel_id)
    await delete_hotel_embeddings(hotel_id, get_qdrant())


async def _on_review_deleted(data: dict[str, Any]) -> None:
    """Handle review.deleted — remove review embedding from Qdrant."""
    review_id = data.get("id")
    if not review_id:
        logger.warning("review.deleted event missing id field")
        return
    logger.info("Received review.deleted for %s", review_id)
    await delete_review_embedding(review_id, get_qdrant())


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
    await rabbitmq.consume(
        queue_name="ai.hotel.deleted",
        exchange_name="travelmind",
        routing_key="hotel.deleted",
        callback=_on_hotel_deleted,
    )
    await rabbitmq.consume(
        queue_name="ai.review.deleted",
        exchange_name="travelmind",
        routing_key="review.deleted",
        callback=_on_review_deleted,
    )
    logger.info("AI consumers started")
