from __future__ import annotations

import json
import logging

from travelmind_ai.core.llm import LLMClient
from travelmind_ai.scraping.schemas import ExtractedHotelData, ExtractedReview
from travelmind_ai.shared.exceptions import ScrapingError

logger = logging.getLogger(__name__)

EXTRACT_HOTEL_PROMPT = """\
You are a data extraction assistant. Given the following cleaned text from a hotel \
webpage, extract structured hotel information. Return ONLY valid JSON matching this schema:

{{
  "name": "string or null",
  "description": "string or null",
  "address": "string or null",
  "city": "string or null",
  "country": "string or null",
  "stars": "integer 0-5 or null",
  "amenities": ["list of strings"],
  "images": ["list of image URLs"],
  "contact_email": "string or null",
  "contact_phone": "string or null",
  "price_range": "string or null"
}}

Webpage text:
{text}
"""

EXTRACT_REVIEWS_PROMPT = """\
You are a data extraction assistant. Given the following cleaned text from a hotel \
webpage, extract all guest reviews. Return ONLY a valid JSON array:

[
  {{
    "author": "string or null",
    "rating": "integer 1-5 or null",
    "title": "string or null",
    "comment": "string or null"
  }}
]

Webpage text:
{text}
"""


async def extract_hotel_data(text: str, llm_client: LLMClient) -> ExtractedHotelData:
    prompt = EXTRACT_HOTEL_PROMPT.format(text=text[:8000])
    try:
        result = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2048,
        )
        data = json.loads(result)
        return ExtractedHotelData.model_validate(data)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to extract hotel data: %s", e)
        raise ScrapingError(f"LLM extraction failed: {e}") from e


async def extract_reviews(text: str, llm_client: LLMClient) -> list[ExtractedReview]:
    prompt = EXTRACT_REVIEWS_PROMPT.format(text=text[:8000])
    try:
        result = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=4096,
        )
        data = json.loads(result)
        return [ExtractedReview.model_validate(item) for item in data]
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to extract reviews: %s", e)
        return []
