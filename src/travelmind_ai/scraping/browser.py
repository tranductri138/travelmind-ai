from __future__ import annotations

import logging

from playwright.async_api import Browser, async_playwright

logger = logging.getLogger(__name__)

_playwright = None
_browser: Browser | None = None


async def get_browser() -> Browser:
    global _playwright, _browser
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
        logger.info("Playwright browser launched")
    return _browser


async def close_browser() -> None:
    global _playwright, _browser
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    logger.info("Playwright browser closed")


async def fetch_page_html(url: str, *, wait_ms: int = 3000) -> str:
    """Navigate to URL and return the full page HTML after JS rendering."""
    browser = await get_browser()
    page = await browser.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(wait_ms)
        return await page.content()
    finally:
        await page.close()
