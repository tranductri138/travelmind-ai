# Context: Scraping — Playwright + BeautifulSoup + LLM

> Load khi làm việc với: scraping/, web scraping, LLM extraction, crawler events.

## Endpoint

```
POST /scraping/extract
```

**Request / Response:**
```python
class ScrapeRequest(BaseModel):
    url: HttpUrl                   # URL trang hotel cần scrape
    extract_reviews: bool = False  # có extract reviews không

class ScrapeResponse(BaseModel):
    url: str
    hotel: ExtractedHotelData
    reviews: list[ExtractedReview]  # rỗng nếu extract_reviews=False
    raw_text_length: int            # độ dài text sau khi clean HTML

class ExtractedHotelData(BaseModel):
    name: str | None = None
    description: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    stars: int | None = None       # 0–5
    amenities: list[str] = []
    images: list[str] = []
    contact_email: str | None = None
    contact_phone: str | None = None
    price_range: str | None = None

class ExtractedReview(BaseModel):
    author: str | None = None
    rating: int | None = None      # 1–5
    title: str | None = None
    comment: str | None = None
```

## Pipeline (`scraping_service.py`)

```
URL
  → fetch_page_html(url)           # Playwright: goto → wait networkidle → wait 3000ms → page.content()
  → clean_html(html)               # BS4: strip script/style/nav/footer/header/noscript/svg → plain text
  → extract_hotel_data(text, llm)  # LLM → JSON → ExtractedHotelData
  → extract_reviews(text, llm)     # chỉ chạy nếu extract_reviews=True → list[ExtractedReview]
  → ScrapeResponse
```

### `clean_html()` (`scraping_service.py:15`)
```python
soup = BeautifulSoup(html, "html.parser")
for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
    tag.decompose()
text = soup.get_text(separator="\n", strip=True)
lines = [line.strip() for line in text.splitlines() if line.strip()]
return "\n".join(lines)
```

## Browser (`browser.py`)

Singleton Playwright — khởi tạo lần đầu gọi `get_browser()`:

```python
_playwright = None
_browser: Browser | None = None  # chromium headless

async def fetch_page_html(url: str, *, wait_ms: int = 3000) -> str:
    browser = await get_browser()
    page = await browser.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(wait_ms)   # chờ thêm JS dynamic content
        return await page.content()
    finally:
        await page.close()                      # đóng page, giữ browser

async def close_browser() -> None: ...         # gọi trong lifespan shutdown
```

**Lưu ý**: `wait_until="networkidle"` + `wait_ms=3000` — đợi JS render xong trước khi lấy HTML.

## LLM Extraction (`llm_extractor.py`)

Hai hàm độc lập, dùng `llm_client.chat()` với `temperature=0.1`:

| Hàm | Input | max_tokens | Output | Fallback |
|-----|-------|-----------|--------|---------|
| `extract_hotel_data(text, llm)` | `text[:8000]` | 2048 | `ExtractedHotelData` | raise `ScrapingError` |
| `extract_reviews(text, llm)` | `text[:8000]` | 4096 | `list[ExtractedReview]` | return `[]` (silent) |

**Prompt cấu trúc**: yêu cầu LLM trả về **ONLY valid JSON** khớp schema định sẵn → parse bằng `json.loads()` → `model_validate()`.

```python
# Ví dụ flow extract
result = await llm_client.chat(
    messages=[{"role": "user", "content": prompt.format(text=text[:8000])}],
    temperature=0.1,
    max_tokens=2048,
)
data = json.loads(result)
return ExtractedHotelData.model_validate(data)
```

## RabbitMQ Consumer (`consumer.py`)

```
Event: crawler.job  (queue: ai.crawler.job)
Payload: { url: string, extract_reviews?: bool, job_id?: string }

  → ScrapeRequest(url=url, extract_reviews=...)
  → scrape_hotel(request, get_llm_client())
  → publish crawler.completed:
    {
      url: str,
      hotel: ExtractedHotelData.model_dump(),
      reviews: [ExtractedReview.model_dump(), ...],
      job_id: str | None
    }
```

```python
async def start_scraping_consumers() -> None:
    await rabbitmq.consume(
        queue_name="ai.crawler.job",
        exchange_name="travelmind",
        routing_key="crawler.job",
        callback=_on_scraping_job,
    )
```

## Dependency

```python
# router.py inject LLMClient
async def extract_hotel(
    request: ScrapeRequest,
    llm_client: LLMClient = Depends(get_llm_client),
) -> ScrapeResponse:
    return await scrape_hotel(request, llm_client)
```

## Error Handling

| Lỗi | Nơi xảy ra | Hành vi |
|-----|-----------|---------|
| Playwright timeout (>30s) | `fetch_page_html` | raise exception → HTTP 500 |
| LLM JSON parse lỗi (hotel) | `extract_hotel_data` | raise `ScrapingError` |
| LLM JSON parse lỗi (reviews) | `extract_reviews` | log error, return `[]` |
| RabbitMQ job thiếu `url` | `_on_scraping_job` | log warning, return (bỏ qua job) |
