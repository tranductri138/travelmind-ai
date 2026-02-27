from __future__ import annotations

from fastapi import APIRouter, Depends
from qdrant_client import AsyncQdrantClient

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
from travelmind_ai.core.embedding import EmbeddingClient
from travelmind_ai.core.llm import LLMClient
from travelmind_ai.dependencies import get_embedding_client, get_llm_client, get_qdrant_client

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
