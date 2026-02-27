from __future__ import annotations

import logging

from qdrant_client import AsyncQdrantClient

from travelmind_ai.ai.prompts import RAG_ITINERARY_SYSTEM, RAG_ITINERARY_USER
from travelmind_ai.ai.schemas import HotelScore, RAGItineraryRequest, RAGItineraryResponse
from travelmind_ai.config import settings
from travelmind_ai.core.embedding import EmbeddingClient
from travelmind_ai.core.llm import LLMClient

logger = logging.getLogger(__name__)


async def generate_itinerary(
    request: RAGItineraryRequest,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
    qdrant_client: AsyncQdrantClient,
) -> RAGItineraryResponse:
    """RAG pipeline: retrieve relevant hotels → augment prompt → LLM generate itinerary."""
    # 1. Embed destination + interests to find relevant hotels
    search_text = f"Hotels in {request.destination}"
    if request.interests:
        search_text += f" for {', '.join(request.interests)}"

    vectors = await embedding_client.embed([search_text])
    hits = await qdrant_client.search(
        collection_name=settings.qdrant_collection_hotels,
        query_vector=vectors[0],
        limit=10,
    )

    # Deduplicate and build context
    seen: dict[str, tuple[float, str]] = {}
    for hit in hits:
        hid = hit.payload["hotel_id"]  # type: ignore[index]
        text = hit.payload["text"]  # type: ignore[index]
        if hid not in seen or hit.score > seen[hid][0]:
            seen[hid] = (hit.score, text)

    hotel_context = "\n\n".join(
        f"- {text} (relevance: {score:.2f})" for score, text in seen.values()
    )
    hotel_suggestions = [
        HotelScore(hotel_id=hid, score=score) for hid, (score, _) in seen.items()
    ]

    # 2. Build prompt
    interests_section = (
        f"Interests: {', '.join(request.interests)}" if request.interests else ""
    )
    budget_section = f"Budget level: {request.budget}" if request.budget else ""

    user_prompt = RAG_ITINERARY_USER.format(
        days=request.days,
        destination=request.destination,
        interests_section=interests_section,
        budget_section=budget_section,
        hotel_context=hotel_context or "No hotel data available for this destination yet.",
    )

    # 3. Generate
    itinerary = await llm_client.chat(
        messages=[
            {"role": "system", "content": RAG_ITINERARY_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=4096,
    )

    return RAGItineraryResponse(
        destination=request.destination,
        days=request.days,
        itinerary=itinerary,
        hotel_suggestions=sorted(hotel_suggestions, key=lambda x: x.score, reverse=True)[:5],
    )
