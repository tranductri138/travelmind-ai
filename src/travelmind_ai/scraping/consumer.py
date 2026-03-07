from __future__ import annotations

from typing import Any

from loguru import logger

from travelmind_ai.core import rabbitmq
from travelmind_ai.dependencies import get_llm_client
from travelmind_ai.scraping.schemas import ScrapeRequest
from travelmind_ai.scraping.scraping_service import scrape_hotel


async def _on_scraping_job(data: dict[str, Any]) -> None:
    """Handle crawler.job — crawl URL and publish result."""
    url = data.get("url")
    if not url:
        logger.warning("Scraping job missing url field")
        return

    logger.info("Processing scraping job for %s", url)
    request = ScrapeRequest(url=url, extract_reviews=data.get("extract_reviews", False))
    result = await scrape_hotel(request, get_llm_client())

    await rabbitmq.publish(
        exchange_name="travelmind",
        routing_key="crawler.completed",
        body={
            "url": result.url,
            "hotel": result.hotel.model_dump(),
            "reviews": [r.model_dump() for r in result.reviews],
            "job_id": data.get("job_id"),
        },
    )
    logger.info("Scraping completed for %s", url)


async def start_scraping_consumers() -> None:
    await rabbitmq.consume(
        queue_name="ai.crawler.job",
        exchange_name="travelmind",
        routing_key="crawler.job",
        callback=_on_scraping_job,
    )
    logger.info("Scraping consumers started")
