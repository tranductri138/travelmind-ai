# TravelMind AI — Kiến Trúc Hệ Thống

> Tài liệu này mô tả kiến trúc, luồng dữ liệu và trách nhiệm của từng module.
> Dựa trên code thực tế tại `src/travelmind_ai/`.

---

## 1. Tổng Quan

TravelMind AI là **Python microservice** độc lập, cung cấp các tính năng AI cho ứng dụng du lịch.
**Không** quản lý dữ liệu nghiệp vụ — chỉ đọc từ PostgreSQL (do NestJS/Prisma sở hữu).

```
NestJS Backend ──REST──► FastAPI (port 8000)
               ◄─REST──
               ──RabbitMQ events──► AI consumers → Qdrant embeddings
```

**Vai trò chính:**
- Tạo và lưu vector embeddings (hotels, reviews, bookings) vào Qdrant
- Semantic search và RAG itinerary qua REST API
- AI chat agent (LangGraph ReAct) với tool calling
- Web scraping có LLM extraction

---

## 2. Luồng Khởi Động (`main.py`)

```
lifespan() startup:
  1. init_clients()          → tạo LLMClient, EmbeddingClient, BasicCache
  2. RabbitMQ.connect()      → nếu lỗi: log warning, tiếp tục
  3. Qdrant.connect()        → nếu lỗi: log warning, tiếp tục
  4. init_semantic_cache()   → chỉ chạy nếu Qdrant kết nối được
  5. start_*_consumers()     → chỉ chạy nếu cả RabbitMQ + Qdrant đều kết nối được
```

**Nguyên tắc**: Server luôn khởi động thành công, dù không có RabbitMQ hoặc Qdrant.

---

## 3. Cấu Hình (`config.py`)

Pydantic Settings, load từ `.env`:

| Nhóm | Key quan trọng | Giá trị mặc định |
|------|---------------|-----------------|
| LLM | `llm_provider` | `openai` |
| OpenAI | `openai_llm_model` | `gpt-4o-mini` |
| OpenAI | `openai_embedding_model` | `text-embedding-3-small` |
| Ollama | `ollama_llm_model` | `llama3.2` |
| Ollama | `ollama_embedding_model` | `nomic-embed-text` |
| Embedding | `embedding_dimension` | `1536` |
| CAG | `cag_basic_max_size` | `1000` |
| CAG | `cag_basic_ttl` | `3600` |
| CAG | `cag_semantic_threshold` | `0.95` |
| CAG | `cag_semantic_ttl` | `3600` |
| Qdrant collections | hotels, reviews, bookings, response_cache | — |

---

## 4. Dependency Injection (`dependencies.py`)

FastAPI Depends, quản lý singleton toàn cục:

| Dependency | Singleton | Mô tả |
|-----------|-----------|-------|
| `get_llm_client()` | `_llm_client` | OpenAI/Ollama LLM wrapper |
| `get_embedding_client()` | `_embedding_client` | Embedding model wrapper |
| `get_cache_layer()` | `_cache_layer` | BasicCache + SemanticCache |
| `get_db_session()` | — | AsyncSession PostgreSQL (per request) |
| `get_qdrant_client()` | — | AsyncQdrantClient (per request) |
| `get_rabbitmq_channel()` | — | RabbitMQ channel (per request) |

**Lifecycle:**
- `init_clients()` → gọi khi startup, tạo LLM + embedding + BasicCache
- `init_semantic_cache()` → gọi sau khi Qdrant kết nối, thêm SemanticCache vào CacheLayer
- `shutdown_clients()` → gọi khi shutdown, đóng kết nối

---

## 5. Module AI — Semantic Search & RAG (`ai/`)

### Endpoints

| Method | Path | Mô tả |
|--------|------|-------|
| POST | `/ai/search` | Semantic search hotels |
| POST | `/ai/similar/{hotel_id}` | Tìm hotels tương tự |
| POST | `/ai/rag/itinerary` | Tạo lịch trình du lịch bằng RAG |
| POST | `/ai/sync` | Force sync PostgreSQL → Qdrant (re-embed tất cả hotels + reviews) |

### Luồng Semantic Search

```
Request (query, city?, country?, stars?)
  → EmbeddingClient.embed(query)           # text → vector 1536d
  → Qdrant.search(collection="hotels", ...)  # vector similarity search
  → Deduplicate by hotel_id (keep best score)
  → PostgreSQL: fetch hotel details
  → Response: list[HotelScore]
```

### Luồng RAG Itinerary

```
Request (destination, days, preferences)
  → embed query
  → Qdrant.search("hotels") → top K hotels
  → Format context (hotel names, amenities, ratings)
  → LLM(prompt + context) → day-by-day itinerary text
  → Response: RAGItineraryResponse
```

### Luồng Sync (`POST /ai/sync`)

```
POST /ai/sync
  → Query tất cả active hotels từ PostgreSQL
  → Với mỗi hotel: embed_hotel() → chunk text → embed → upsert Qdrant "hotels"
  → Query tất cả reviews từ PostgreSQL
  → Với mỗi review: embed_review() → embed → upsert Qdrant "reviews"
  → Response: { synced_hotels, total_hotels, synced_reviews, total_reviews }
```

**Khi nào dùng:**
- Sau khi migrate + seed database lần đầu (`npx tsx prisma/sync-ai.ts`)
- Rebuild Qdrant từ scratch
- Recovery sau khi mất data vector DB

### Tích Hợp Với NestJS Backend

**Search proxy**: NestJS backend proxy semantic search request sang AI:
```
Frontend: POST /api/search/semantic { query, city?, min_stars? }
  → NestJS SearchService.semanticSearch()
    → POST http://ai:8000/ai/search (proxy nguyên request)
  → AI embed query → Qdrant search → deduplicate → trả kết quả
  → NestJS trả kết quả về Frontend
```

**Sync script**: Backend có `prisma/sync-ai.ts` gọi `POST /ai/sync` sau khi seed data.

### Consumer (`ai/consumer.py`)

| Event | Queue | Hành động |
|-------|-------|-----------|
| `hotel.created` | ai.hotel.created | chunk text → embed → upsert Qdrant `hotels` |
| `hotel.updated` | ai.hotel.updated | delete cũ → re-embed |
| `hotel.deleted` | ai.hotel.deleted | delete khỏi Qdrant |
| `review.created` | ai.review.created | embed → upsert Qdrant `reviews` |
| `review.deleted` | ai.review.deleted | delete khỏi Qdrant |

**Chunking**: 500 tokens, 50 overlap — áp dụng cho mô tả hotel dài.

---

## 6. Module Booking (`booking/`)

### Consumer (`booking/consumer.py`)

| Event | Queue | Hành động |
|-------|-------|-----------|
| `booking.created` | ai.booking.created | embed booking → Qdrant `bookings` + publish `booking.analytics` |
| `booking.confirmed` | ai.booking.confirmed | update status → re-embed + analytics |
| `booking.cancelled` | ai.booking.cancelled | delete embedding + analytics (action=cancelled) |

**Analytics payload** (published to `booking.analytics`):
```json
{
  "booking_id", "action", "user_id", "room_id",
  "check_in", "check_out", "guests", "total_price",
  "hotel_id", "hotel_name", "status"
}
```

---

## 7. Module Chat — LangGraph ReAct Agent (`chat/`)

### Endpoint

```
POST /ai/chat
Body: { messages: [...], conversation_id?: string, stream?: bool }
```

- `stream=true` → SSE (`text/event-stream`), yield `{"chunk": "..."}`, kết thúc `[DONE]`
- `stream=false` → JSON `{"content": "..."}`

### Luồng End-to-End (Browser → NestJS → AI → Response)

```
Browser (Socket.io)
  │
  │ emit('sendMessage', { message: "find hotels in Danang", conversationId? })
  ▼
NestJS Chat Gateway (WebSocket, namespace /chat)
  │ JWT auth trong handleConnection()
  │ emit typing: true
  │
  │ chatService.handleMessage(userId, conversationId, message, onChunk)
  │   1. Get or create ChatConversation (Prisma)
  │   2. Save user message → ChatMessage(role=USER)
  │   3. Call AI service: POST http://ai:8000/ai/chat (HTTP SSE)
  │      body: { messages: [{role:"user", content: message}],
  │              conversation_id: conversationId, stream: true }
  │      ← CHỈ gửi message mới nhất (không gửi history)
  │      ← LangGraph checkpoint tự quản lý full state
  │
  ▼
AI Service (FastAPI, POST /ai/chat)
  │
  │ Stateful mode (có conversation_id):
  │   config = {"configurable": {"thread_id": conversation_id}}
  │   MemorySaver load checkpoint → khôi phục lịch sử + tool results
  │   Agent xử lý → gọi tools nếu cần → stream response
  │   MemorySaver tự lưu checkpoint mới sau response
  │
  │ Stateless mode (không có conversation_id):
  │   CacheLayer.get(query) → BasicCache → SemanticCache → miss
  │   Nếu hit: return cached response (không gọi LLM)
  │   Nếu miss: agent.ainvoke() → CacheLayer.set()
  │
  │ Streaming SSE:
  │   data: {"chunk": "The best"}\n\n
  │   data: {"chunk": " hotels"}\n\n
  │   ...
  │   data: [DONE]\n\n
  │
  ▼
NestJS Chat Gateway
  │ Parse SSE: mỗi chunk → client.emit('messageChunk', {conversationId, chunk})
  │ Accumulate full response
  │ Save assistant message → ChatMessage(role=ASSISTANT)
  │ emit typing: false
  │ emit messageComplete { conversationId, content }
  ▼
Browser hiển thị response real-time
```

**Quan trọng:**
- NestJS → AI là **HTTP SSE** (không phải WebSocket)
- NestJS chỉ gửi **1 message mới nhất**, AI tự nhớ history qua LangGraph checkpoint
- Error handling: nếu AI lỗi → NestJS trả fallback message, vẫn save vào DB

### Agent Setup (`chat/graph.py`)

```python
agent = create_react_agent(
    model=ChatOpenAI(temperature=0.7, max_tokens=2048, streaming=True),
    tools=ALL_TOOLS,
    prompt=system_prompt,
    checkpointer=MemorySaver(),   # in-memory, keyed by thread_id
)
```

### 4 Tools (`chat/tools.py`)

| Tool | Input | Data source | Output |
|------|-------|-------------|--------|
| `search_hotels` | query, city?, min_stars? | Qdrant → PostgreSQL | top 5 hotels với score |
| `get_hotel_details` | hotel_id | PostgreSQL (hotel + rooms + 5 reviews) | formatted string |
| `check_room_availability` | hotel_id, check_in, check_out, guests? | RoomAvailability table | available rooms + total cost |
| `get_popular_hotels` | city?, limit? | PostgreSQL (sorted by rating, review_count) | top N hotels |

### Hai Chế Độ Hoạt Động (`chat/service.py`)

**Stateful** (`conversation_id` được cung cấp):
- Thread config: `{"configurable": {"thread_id": conversation_id}}`
- MemorySaver lưu toàn bộ lịch sử hội thoại + tool results
- Mỗi request đều gọi LLM (không dùng CAG)

**Stateless** (không có `conversation_id`):
- Không dùng checkpoint — mỗi request độc lập
- Dùng CAG: check cache trước, nếu hit → trả về ngay, nếu miss → gọi LLM → lưu cache

```
Stateless request:
  → CacheLayer.get(last_user_message)
      BasicCache hit?  → return immediately (no LLM call)
      SemanticCache hit? → return, promote to BasicCache
      miss → agent.ainvoke() → CacheLayer.set(response)
```

---

## 8. CAG — Cache-Augmented Generation (`core/cache.py`)

### Kiến Trúc 2 Tầng

```
CacheLayer
├── BasicCache   (tầng 1 — in-memory LRU)
│   ├── max_size: 1000 entries
│   ├── TTL: 3600s
│   ├── key: normalize(query) → lowercase, strip punctuation, collapse whitespace
│   └── O(1) get/set
│
└── SemanticCache (tầng 2 — Qdrant vectors)
    ├── collection: response_cache
    ├── threshold: 0.95 cosine similarity
    ├── TTL: 3600s (stored in payload, checked on retrieval)
    ├── point_id: UUID5(normalize(query)) — deterministic
    └── fallback: BasicCache nếu Qdrant lỗi
```

### Luồng `CacheLayer.get(query)`

```
1. BasicCache.get(normalize(query))  → hit? return ("basic_hit", response)
2. SemanticCache.get(query)          → embed query → Qdrant search
     score ≥ 0.95 + TTL valid?      → promote to BasicCache → return ("semantic_hit", response)
3. return ("miss", None)
```

### Luồng `CacheLayer.set(query, response)`

```
1. BasicCache.set(normalize(query), response)
2. SemanticCache.set(query, response) → embed → upsert Qdrant point
```

---

## 9. Module Scraping (`scraping/`)

### Endpoint

```
POST /scraping/extract
Body: { url: string, extract_reviews?: bool }
Response: { url, hotel: ExtractedHotelData, reviews: ExtractedReview[], raw_text_length }
```

### Luồng

```
URL → Playwright.render()           # headless browser, full JS render, networkidle + 3s wait
    → BeautifulSoup.clean()         # strip scripts, style, nav, footer, header, svg
    → LLM(clean_text + prompt)      # extract structured hotel data (temperature=0.1)
    → nếu extract_reviews: LLM extract reviews
    → Response: { hotel, reviews[], raw_text_length }
```

### 2 Cách Gọi — HTTP Direct vs RabbitMQ

**1. HTTP Direct Call (chính, từ NestJS backend):**
```
NestJS Admin: POST /api/crawler/trigger { url }
  → CrawlerService tạo CrawlJob(PENDING)
  → Background: POST http://ai:8000/scraping/extract { url, extract_reviews }
  → AI scrape (~10-30s) → trả kết quả
  → NestJS tạo Hotel từ kết quả → link hotelId vào CrawlJob → COMPLETED
  → emit hotel.created → EventBridge → RabbitMQ → AI embed vào Qdrant
```

**2. RabbitMQ Consumer (vẫn hoạt động, dùng cho async jobs):**
```
Event: crawler.job → scrape URL → publish crawler.completed
                      (with extracted hotel + review data)
```

**Lưu ý:** NestJS backend **chủ yếu dùng HTTP direct call** (cách 1) vì đơn giản hơn và không cần consumer infrastructure. RabbitMQ consumer vẫn tồn tại cho trường hợp async.

---

## 10. Shared (`shared/`)

- **Middleware**: CorrelationID — gắn `X-Correlation-ID` header vào mọi request/response
- **Exceptions**: Custom exception handlers toàn cục (trả JSON errors chuẩn)
- **text_utils**: chunking text theo token count (tiktoken), dùng trong embedding pipeline

---

## 11. RabbitMQ Events — Tổng Hợp

Exchange: `travelmind` (topic)

**Consumed (từ NestJS):**

| Routing Key | Queue | Handler module |
|-------------|-------|---------------|
| `hotel.created` | ai.hotel.created | ai/consumer.py |
| `hotel.updated` | ai.hotel.updated | ai/consumer.py |
| `hotel.deleted` | ai.hotel.deleted | ai/consumer.py |
| `review.created` | ai.review.created | ai/consumer.py |
| `review.deleted` | ai.review.deleted | ai/consumer.py |
| `booking.created` | ai.booking.created | booking/consumer.py |
| `booking.confirmed` | ai.booking.confirmed | booking/consumer.py |
| `booking.cancelled` | ai.booking.cancelled | booking/consumer.py |
| `crawler.job` | ai.crawler.job | scraping/consumer.py (ít dùng — NestJS chủ yếu gọi HTTP trực tiếp) |

**Published (bởi AI service):**

| Routing Key | Nội dung |
|-------------|---------|
| `crawler.completed` | Extracted hotel + review data (chỉ khi nhận qua RabbitMQ) |
| `booking.analytics` | Booking event with action + metadata |

---

## 12. Qdrant Collections

| Collection | Nội dung | Vector |
|-----------|---------|--------|
| `hotels` | Hotel text chunks (name, description, amenities) | 1536d |
| `reviews` | Review text (title + comment) | 1536d |
| `bookings` | Booking context (hotel, dates, status) | 1536d |
| `response_cache` | Cached LLM responses cho CAG | 1536d |

**Payload chuẩn của hotel point:**
```json
{
  "hotel_id": "uuid",
  "chunk_index": 0,
  "text": "chunk text",
  "city": "Hanoi",
  "country": "Vietnam",
  "stars": 4
}
```

---

## 13. Tests (`tests/`)

- Framework: `pytest` + `pytest-asyncio`
- Tất cả external services được mock (không cần Qdrant/RabbitMQ/PostgreSQL thật)
- Chạy: `uv run pytest -v` (17 tests)

---

## 14. Chạy Project

### Yêu Cầu

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Docker + Docker Compose

### Bước 1 — Cài Dependencies

```bash
uv sync          # tạo .venv + cài tất cả dependencies
```

### Bước 2 — Cấu Hình `.env`

```bash
cp .env.example .env
```

Chỉnh sửa `.env`:

| Biến | Bắt buộc | Ghi chú |
|------|---------|---------|
| `OPENAI_API_KEY` | Có (nếu dùng OpenAI) | Lấy từ platform.openai.com |
| `DATABASE_URL` | Có | PostgreSQL của NestJS backend |
| `LLM_PROVIDER` | Không | `openai` (mặc định) hoặc `ollama` |
| `RABBITMQ_URL` | Không | Mặc định: `amqp://guest:guest@localhost:5672/` |
| `QDRANT_URL` | Không | Mặc định: `http://localhost:6333` |

### Bước 3 — Khởi Động Infrastructure

```bash
docker compose up -d
```

Khởi động:
- **RabbitMQ**: `localhost:5672` — Management UI: `http://localhost:15672` (guest/guest)
- **Qdrant**: `localhost:6333` — Dashboard: `http://localhost:6333/dashboard`

Kiểm tra đã chạy:
```bash
docker compose ps      # cả 2 service phải ở trạng thái healthy
```

### Bước 4 — Chạy Server

```bash
uv run uvicorn travelmind_ai.main:app --reload --port 8000
```

Server sẵn sàng tại:
- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health: `http://localhost:8000/health`

### Bước 5 — Sync Data Từ PostgreSQL → Qdrant

```bash
# Từ backend project (sau khi seed xong):
cd ../backend && npx tsx prisma/sync-ai.ts

# Hoặc gọi trực tiếp API:
curl -X POST http://localhost:8000/ai/sync
```

Endpoint `/ai/sync` đọc tất cả hotels + reviews từ PostgreSQL, embed và upsert vào Qdrant.
Chỉ cần chạy 1 lần sau khi seed, hoặc khi muốn rebuild Qdrant.

### Dùng Ollama Thay OpenAI (Local Dev)

```bash
# Cài và khởi động Ollama (https://ollama.com)
ollama pull llama3.2
ollama pull nomic-embed-text

# Trong .env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
```

### Chạy Tests (Không Cần Infrastructure)

```bash
uv run pytest -v           # chạy 17 tests (tất cả mock)
uv run pytest --cov        # kèm coverage report
```

### Lint

```bash
uv run ruff check src/ --fix
```

---

## 15. Trace Lỗi

### Kiểm Tra Nhanh

```bash
# 1. Health check — trạng thái kết nối live
curl http://localhost:8000/health
# {"status":"ok","rabbitmq":"connected","qdrant":"connected"}

# 2. Xem log server
# Log level mặc định: info. Để verbose hơn, set LOG_LEVEL=debug trong .env

# 3. Trạng thái containers
docker compose ps
docker compose logs rabbitmq
docker compose logs qdrant
```

### Bảng Lỗi Thường Gặp

| Triệu Chứng | Nguyên Nhân | Cách Fix |
|-------------|------------|---------|
| `RabbitMQ unavailable — consumers disabled` (log lúc startup) | RabbitMQ chưa chạy | `docker compose up -d rabbitmq` |
| `Qdrant unavailable — vector search disabled` (log lúc startup) | Qdrant chưa chạy | `docker compose up -d qdrant` |
| `/health` trả về `"rabbitmq": "disconnected"` | RabbitMQ down hoặc sai URL | Kiểm tra `RABBITMQ_URL` trong `.env` |
| `/health` trả về `"qdrant": "disconnected"` | Qdrant down hoặc sai URL | Kiểm tra `QDRANT_URL` trong `.env` |
| HTTP 502 `LLM request failed` | LLM call thất bại | Xem chi tiết bên dưới |
| HTTP 502 `Embedding generation failed` | Embedding call thất bại | Xem chi tiết bên dưới |
| HTTP 502 `Scraping failed` | Playwright timeout hoặc LLM parse lỗi | URL không hợp lệ hoặc trang chặn bot |
| Consumers không start (không thấy log `consumers started`) | Một trong hai: RabbitMQ hoặc Qdrant không kết nối được | Kiểm tra `/health` |
| `asyncpg` connection error | PostgreSQL sai URL hoặc chưa chạy | Kiểm tra `DATABASE_URL` trong `.env` |
| `pydantic_settings` error lúc startup | Thiếu biến `.env` bắt buộc | Đối chiếu với `.env.example` |

### Lỗi LLM (HTTP 502)

**Nếu dùng OpenAI:**
```
AuthenticationError → OPENAI_API_KEY sai hoặc hết hạn
RateLimitError      → Vượt quota, thử lại sau
```

**Nếu dùng Ollama:**
```bash
# Kiểm tra Ollama đang chạy
ollama list         # phải thấy llama3.2 và nomic-embed-text

# Nếu thiếu model
ollama pull llama3.2
ollama pull nomic-embed-text

# Kiểm tra OLLAMA_BASE_URL trong .env
# Mặc định: http://localhost:11434
```

### Lỗi Scraping (HTTP 502)

```
ScrapingError: LLM extraction failed → LLM không parse được JSON từ HTML
  → Thử với URL đơn giản hơn, hoặc trang hotel cụ thể
  → Kiểm tra trang không yêu cầu login/CAPTCHA

Playwright timeout (30s) → Trang load quá chậm hoặc bị block
  → Thử lại, hoặc dùng URL khác
```

### Lỗi Chat / Agent

```
Agent không gọi tool → Kiểm tra system prompt trong chat/prompts.py
Stateful chat không nhớ lịch sử → Đảm bảo gửi cùng conversation_id
CAG luôn miss → SemanticCache chưa init (Qdrant disconnected) → check /health
```

### Trace Theo X-Correlation-ID

Mọi request đều có header `X-Correlation-ID` (tự tạo nếu không gửi):

```bash
# Gửi request với correlation ID tự đặt
curl -H "X-Correlation-ID: my-debug-id-123" http://localhost:8000/ai/search ...

# Tìm trong log
# [INFO] ... correlation_id=my-debug-id-123 ...
```

### Debug Qdrant Collections

```bash
# Xem collections và số lượng points
curl http://localhost:6333/collections

# Xem collection cụ thể
curl http://localhost:6333/collections/hotels
```

### Reset Hoàn Toàn (Xóa Dữ Liệu)

```bash
# Xóa toàn bộ data Qdrant + RabbitMQ (volumes)
docker compose down -v

# Khởi động lại sạch
docker compose up -d
```
