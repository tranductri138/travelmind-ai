from __future__ import annotations

import json

from loguru import logger

from travelmind_ai.core.llm import LLMClient
from travelmind_ai.scraping.schemas import ExtractedHotelData, ExtractedReview
from travelmind_ai.shared.exceptions import ScrapingError

EXTRACT_HOTEL_PROMPT = """\
Bạn là trợ lý trích xuất dữ liệu. Dựa trên đoạn văn bản đã được làm sạch từ trang web \
khách sạn dưới đây, hãy trích xuất thông tin khách sạn có cấu trúc. Chỉ trả về JSON hợp lệ \
theo schema sau:

{{
  "name": "chuỗi hoặc null",
  "description": "chuỗi hoặc null",
  "address": "chuỗi hoặc null",
  "city": "chuỗi hoặc null",
  "country": "chuỗi hoặc null",
  "stars": "số nguyên 0-5 hoặc null",
  "amenities": ["danh sách chuỗi"],
  "images": ["danh sách URL hình ảnh"],
  "contact_email": "chuỗi hoặc null",
  "contact_phone": "chuỗi hoặc null",
  "price_range": "chuỗi hoặc null"
}}

Văn bản trang web:
{text}
"""

EXTRACT_REVIEWS_PROMPT = """\
Bạn là trợ lý trích xuất dữ liệu. Dựa trên đoạn văn bản đã được làm sạch từ trang web \
khách sạn dưới đây, hãy trích xuất tất cả đánh giá của khách. Chỉ trả về mảng JSON hợp lệ:

[
  {{
    "author": "chuỗi hoặc null",
    "rating": "số nguyên 1-5 hoặc null",
    "title": "chuỗi hoặc null",
    "comment": "chuỗi hoặc null"
  }}
]

Văn bản trang web:
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
