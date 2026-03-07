from __future__ import annotations

from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from travelmind_ai.config import settings
from travelmind_ai.core.embedding import EmbeddingClient
from travelmind_ai.shared.text_utils import build_hotel_text, chunk_text


async def embed_hotel(
    hotel_data: dict,
    embedding_client: EmbeddingClient,
    qdrant_client: AsyncQdrantClient,
) -> None:
    """Generate embedding for a hotel and upsert into Qdrant."""
    text = build_hotel_text(
        name=hotel_data["name"],
        city=hotel_data["city"],
        country=hotel_data["country"],
        description=hotel_data.get("description"),
        amenities=hotel_data.get("amenities", []),
        stars=hotel_data.get("stars", 0),
        rating=hotel_data.get("rating", 0),
    )

    chunks = chunk_text(text, max_tokens=500)
    vectors = await embedding_client.embed(chunks)

    points = [
        PointStruct(
            id=f"{hotel_data['id']}_{i}" if i > 0 else hotel_data["id"],
            vector=vector,
            payload={
                "hotel_id": hotel_data["id"],
                "chunk_index": i,
                "text": chunk,
                "city": hotel_data["city"],
                "country": hotel_data["country"],
                "stars": hotel_data.get("stars", 0),
            },
        )
        for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
    ]

    await qdrant_client.upsert(
        collection_name=settings.qdrant_collection_hotels,
        points=points,
    )
    logger.info("Embedded hotel %s (%d chunks)", hotel_data["id"], len(chunks))


async def embed_review(
    review_data: dict,
    embedding_client: EmbeddingClient,
    qdrant_client: AsyncQdrantClient,
) -> None:
    """Generate embedding for a review and upsert into Qdrant."""
    text_parts = []
    if review_data.get("title"):
        text_parts.append(review_data["title"])
    if review_data.get("comment"):
        text_parts.append(review_data["comment"])

    if not text_parts:
        return

    text = " — ".join(text_parts)
    vectors = await embedding_client.embed([text])

    point = PointStruct(
        id=review_data["id"],
        vector=vectors[0],
        payload={
            "review_id": review_data["id"],
            "hotel_id": review_data["hotel_id"],
            "rating": review_data.get("rating", 0),
            "text": text,
        },
    )

    await qdrant_client.upsert(
        collection_name=settings.qdrant_collection_reviews,
        points=[point],
    )
    logger.info("Embedded review %s", review_data["id"])


async def delete_hotel_embeddings(
    hotel_id: str,
    qdrant_client: AsyncQdrantClient,
) -> None:
    """Delete all embedding chunks for a hotel from Qdrant."""
    await qdrant_client.delete(
        collection_name=settings.qdrant_collection_hotels,
        points_selector=Filter(
            must=[FieldCondition(key="hotel_id", match=MatchValue(value=hotel_id))]
        ),
    )
    logger.info("Deleted embeddings for hotel %s", hotel_id)


async def delete_review_embedding(
    review_id: str,
    qdrant_client: AsyncQdrantClient,
) -> None:
    """Delete the embedding for a review from Qdrant."""
    await qdrant_client.delete(
        collection_name=settings.qdrant_collection_reviews,
        points_selector=Filter(
            must=[FieldCondition(key="review_id", match=MatchValue(value=review_id))]
        ),
    )
    logger.info("Deleted embedding for review %s", review_id)
