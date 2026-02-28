from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from travelmind_ai.ai.embedding_service import embed_hotel, embed_review
from travelmind_ai.ai.rag_service import generate_itinerary
from travelmind_ai.ai.schemas import (
    HotelScore,
    RAGItineraryRequest,
    RAGItineraryResponse,
    SearchRequest,
    SearchResponse,
    SimilarRequest,
)
from travelmind_ai.ai.search_service import find_similar, semantic_search
from travelmind_ai.core.database import Hotel, Review
from travelmind_ai.core.embedding import EmbeddingClient
from travelmind_ai.core.llm import LLMClient
from travelmind_ai.dependencies import get_db_session, get_embedding_client, get_llm_client, get_qdrant_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Semantic hotel search",
    description=(
        "Embed the query with the configured LLM provider, "
        "then search Qdrant for the most similar hotels. "
        "Supports optional city/country/stars filters."
    ),
)
async def search_hotels(
    request: SearchRequest,
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant_client),
) -> SearchResponse:
    return await semantic_search(request, embedding_client, qdrant_client)


@router.post(
    "/similar/{hotel_id}",
    response_model=list[HotelScore],
    summary="Find similar hotels",
    description=(
        "Given a hotel ID that already has a vector in Qdrant, "
        "find the most similar hotels by cosine distance."
    ),
)
async def similar_hotels(
    hotel_id: str,
    request: SimilarRequest = SimilarRequest(),
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant_client),
) -> list[HotelScore]:
    return await find_similar(hotel_id, request.limit, qdrant_client)


@router.post(
    "/rag/itinerary",
    response_model=RAGItineraryResponse,
    summary="Generate travel itinerary (RAG)",
    description=(
        "Retrieval-Augmented Generation: find relevant hotels via "
        "vector search, then ask the LLM to produce a day-by-day "
        "travel itinerary with hotel recommendations."
    ),
)
async def rag_itinerary(
    request: RAGItineraryRequest,
    llm_client: LLMClient = Depends(get_llm_client),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant_client),
) -> RAGItineraryResponse:
    return await generate_itinerary(request, llm_client, embedding_client, qdrant_client)


@router.post(
    "/sync",
    summary="Sync PostgreSQL data to Qdrant",
    description="Read all hotels and reviews from PostgreSQL and embed them into Qdrant.",
)
async def sync_to_qdrant(
    db: AsyncSession = Depends(get_db_session),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant_client),
) -> dict:
    # Sync hotels
    result = await db.execute(select(Hotel).where(Hotel.is_active == True))  # noqa: E712
    hotels = result.scalars().all()
    hotel_count = 0
    for hotel in hotels:
        try:
            await embed_hotel(
                {
                    "id": hotel.id,
                    "name": hotel.name,
                    "city": hotel.city,
                    "country": hotel.country,
                    "description": hotel.description,
                    "amenities": hotel.amenities or [],
                    "stars": hotel.stars,
                    "rating": float(hotel.rating),
                },
                embedding_client,
                qdrant_client,
            )
            hotel_count += 1
        except Exception as e:
            logger.error("Failed to embed hotel %s: %s", hotel.id, e)

    # Sync reviews
    result = await db.execute(select(Review))
    reviews = result.scalars().all()
    review_count = 0
    for review in reviews:
        try:
            await embed_review(
                {
                    "id": review.id,
                    "hotel_id": review.hotel_id,
                    "title": review.title,
                    "comment": review.comment,
                    "rating": review.rating,
                },
                embedding_client,
                qdrant_client,
            )
            review_count += 1
        except Exception as e:
            logger.error("Failed to embed review %s: %s", review.id, e)

    return {
        "synced_hotels": hotel_count,
        "synced_reviews": review_count,
        "total_hotels": len(hotels),
        "total_reviews": len(reviews),
    }
