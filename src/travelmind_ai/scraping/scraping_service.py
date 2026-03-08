from __future__ import annotations

from bs4 import BeautifulSoup
from loguru import logger

from travelmind_ai.core.llm import LLMClient
from travelmind_ai.scraping.browser import fetch_page_html
from travelmind_ai.scraping.llm_extractor import extract_hotel_data, extract_reviews
from travelmind_ai.scraping.schemas import ScrapeRequest, ScrapeResponse


def clean_html(html: str) -> str:
    """Strip scripts/styles/nav and return readable text."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


async def scrape_hotel(request: ScrapeRequest, llm_client: LLMClient) -> ScrapeResponse:
    """Full scraping pipeline: fetch → clean → LLM extract."""
    url = str(request.url)
    logger.info(f"Scraping {url}")

    html = await fetch_page_html(url)
    cleaned = clean_html(html)

    hotel = await extract_hotel_data(cleaned, llm_client)
    reviews = []
    if request.extract_reviews:
        reviews = await extract_reviews(cleaned, llm_client)

    return ScrapeResponse(
        url=url,
        hotel=hotel,
        reviews=reviews,
        raw_text_length=len(cleaned),
    )
