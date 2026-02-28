from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from travelmind_ai.config import settings
from travelmind_ai.core.llm import LLMClient
from travelmind_ai.dependencies import get_llm_client
from travelmind_ai.scraping.schemas import ScrapeRequest, ScrapeResponse
from travelmind_ai.scraping.scraping_service import scrape_hotel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scraping", tags=["Scraping"])

# In-memory tracker for demo mode (resets daily)
_scrape_requests: dict[str, list[datetime]] = {}


def _check_scrape_limit(url: str) -> None:
    """Check if scraping limit is exceeded for demo mode."""
    if not settings.scraping_enabled:
        raise HTTPException(status_code=403, detail="Scraping is disabled")

    today = datetime.utcnow().date()
    key = str(today)

    # Clean up old requests
    if key in _scrape_requests:
        cutoff = datetime.utcnow() - timedelta(days=1)
        _scrape_requests[key] = [t for t in _scrape_requests[key] if t > cutoff]

    # Check limit
    requests_today = len(_scrape_requests.get(key, []))
    if requests_today >= settings.scraping_max_requests_per_day:
        raise HTTPException(
            status_code=429,
            detail=f"Daily scraping limit ({settings.scraping_max_requests_per_day}) exceeded. "
            "Try again tomorrow.",
        )

    # Record this request
    if key not in _scrape_requests:
        _scrape_requests[key] = []
    _scrape_requests[key].append(datetime.utcnow())
    logger.info(
        "Scrape request %d/%d for today",
        len(_scrape_requests[key]),
        settings.scraping_max_requests_per_day,
    )


@router.post(
    "/extract",
    response_model=ScrapeResponse,
    summary="Scrape & extract hotel data",
    description=(
        "Navigate to the given URL with a headless browser (Playwright), "
        "clean the HTML with BeautifulSoup, then use the LLM to extract "
        "structured hotel info (and optionally reviews). "
        f"DEMO MODE: Limited to {settings.scraping_max_requests_per_day} requests per day."
    ),
)
async def extract_hotel(
    request: ScrapeRequest,
    llm_client: LLMClient = Depends(get_llm_client),
) -> ScrapeResponse:
    _check_scrape_limit(str(request.url))
    return await scrape_hotel(request, llm_client)
