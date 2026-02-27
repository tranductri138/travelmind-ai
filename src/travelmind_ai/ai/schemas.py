from __future__ import annotations

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Semantic hotel search query."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"query": "luxury beach resort with spa", "city": "Bali", "limit": 5}
            ]
        }
    }

    query: str = Field(
        ..., min_length=1, max_length=500, description="Natural language search query"
    )
    city: str | None = Field(None, description="Filter by city name")
    country: str | None = Field(None, description="Filter by country name")
    min_stars: int | None = Field(None, ge=0, le=5, description="Minimum star rating")
    limit: int = Field(10, ge=1, le=50, description="Max results to return")


class HotelScore(BaseModel):
    hotel_id: str = Field(..., description="UUID of the matched hotel")
    score: float = Field(..., description="Cosine similarity score (0-1)")


class SearchResponse(BaseModel):
    results: list[HotelScore]
    query: str


class SimilarRequest(BaseModel):
    """Find hotels similar to a given hotel."""

    limit: int = Field(5, ge=1, le=20, description="Max similar hotels to return")


class RAGItineraryRequest(BaseModel):
    """Request a RAG-generated travel itinerary."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "destination": "Paris",
                    "days": 3,
                    "interests": ["museums", "food", "architecture"],
                    "budget": "mid-range",
                }
            ]
        }
    }

    destination: str = Field(
        ..., min_length=1, description="Travel destination city/region"
    )
    days: int = Field(..., ge=1, le=30, description="Number of trip days")
    interests: list[str] = Field(
        default_factory=list, description="Traveler interests"
    )
    budget: str | None = Field(
        None, description="Budget level: budget, mid-range, luxury"
    )


class RAGItineraryResponse(BaseModel):
    destination: str
    days: int
    itinerary: str = Field(
        ..., description="Markdown-formatted day-by-day itinerary"
    )
    hotel_suggestions: list[HotelScore]
