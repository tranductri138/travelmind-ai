from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class ScrapeRequest(BaseModel):
    """Request to scrape and extract hotel data from a URL."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://www.booking.com/hotel/vn/example.html",
                    "extract_reviews": True,
                }
            ]
        }
    }

    url: HttpUrl = Field(..., description="Hotel page URL to scrape")
    extract_reviews: bool = Field(
        False, description="Also extract guest reviews"
    )


class ExtractedHotelData(BaseModel):
    name: str | None = None
    description: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    stars: int | None = Field(None, ge=0, le=5)
    amenities: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    contact_email: str | None = None
    contact_phone: str | None = None
    price_range: str | None = None


class ExtractedReview(BaseModel):
    author: str | None = None
    rating: int | None = Field(None, ge=1, le=5)
    title: str | None = None
    comment: str | None = None


class ScrapeResponse(BaseModel):
    url: str
    hotel: ExtractedHotelData
    reviews: list[ExtractedReview] = Field(default_factory=list)
    raw_text_length: int = 0
