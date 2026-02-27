from __future__ import annotations

from fastapi import APIRouter, Depends

from travelmind_ai.core.llm import LLMClient
from travelmind_ai.dependencies import get_llm_client
from travelmind_ai.scraping.schemas import ScrapeRequest, ScrapeResponse
from travelmind_ai.scraping.scraping_service import scrape_hotel

router = APIRouter(prefix="/scraping", tags=["Scraping"])


@router.post(
    "/extract",
    response_model=ScrapeResponse,
    summary="Scrape & extract hotel data",
    description=(
        "Navigate to the given URL with a headless browser (Playwright), "
        "clean the HTML with BeautifulSoup, then use the LLM to extract "
        "structured hotel info (and optionally reviews)."
    ),
)
async def extract_hotel(
    request: ScrapeRequest,
    llm_client: LLMClient = Depends(get_llm_client),
) -> ScrapeResponse:
    return await scrape_hotel(request, llm_client)
