# TravelMind AI — Kiến Trúc Hệ Thống

> Tài liệu giải thích chi tiết từng folder, từng thư viện, luồng dữ liệu
> và cách các thành phần kết nối với nhau. Dựa trên code thực tế tại `src/travelmind_ai/`.

---

## 1. Tổng Quan

TravelMind AI là **Python microservice** phụ trách mọi tính năng AI cho ứng dụng du lịch.
Service này **không quản lý dữ liệu nghiệp vụ** — PostgreSQL do NestJS/Prisma sở hữu, AI chỉ đọc.

```
Browser ──► NestJS Backend (port 3000) ──REST/SSE──► Python AI Service (port 8000)
                 │                                        │
                 ├── PostgreSQL ◄─────────────────────────┘ (READ-ONLY: hotels, rooms, reviews)
                 ├── RabbitMQ  ◄──────────────────────────┘ (events hai chiều)
                 └── Qdrant ◄─────────────────────────────┘ (vector storage riêng của AI)
```

**Service này làm 4 việc:**

| # | Nhiệm vụ | Module | Mô tả ngắn |
|---|----------|--------|-------------|
| 1 | Semantic Search + RAG | `ai/` | Embed text → vector, tìm kiếm bằng ý nghĩa, tạo lịch trình |
| 2 | AI Chat Agent | `chat/` | Chatbot thông minh có thể gọi tools, nhớ hội thoại |
| 3 | Web Scraping | `scraping/` | Crawl trang web + dùng LLM bóc tách dữ liệu hotel |
| 4 | Booking Analytics | `booking/` | Embed booking events cho phân tích |

---

## 2. Project Structure — Từng Folder Làm Gì

```
src/travelmind_ai/
├── main.py                 # Khởi tạo FastAPI, kết nối services, đăng ký routes
├── config.py               # Đọc .env, validate settings bằng Pydantic
├── dependencies.py         # Dependency Injection — tạo và chia sẻ singleton clients
│
├── core/                   # ═══ Tầng Infrastructure — kết nối external services ═══
│   ├── llm.py              #   LLMClient: gọi OpenAI/Ollama để chat + generate text
│   ├── embedding.py        #   EmbeddingClient: biến text → vector 1536 chiều
│   ├── qdrant.py           #   Kết nối Qdrant, tạo 4 collections khi startup
│   ├── database.py         #   SQLAlchemy ORM models (Hotel, Room, Review, RoomAvailability)
│   ├── rabbitmq.py         #   aio-pika connection, publish/consume messages
│   └── cache.py            #   CAG: BasicCache (LRU in-memory) + SemanticCache (Qdrant)
│
├── ai/                     # ═══ Nhiệm vụ 1: Semantic Search + RAG ═══
│   ├── router.py           #   4 endpoints: /ai/search, /ai/similar, /ai/rag/itinerary, /ai/sync
│   ├── search_service.py   #   Logic tìm kiếm: embed query → Qdrant → deduplicate → trả kết quả
│   ├── rag_service.py      #   RAG: retrieve hotels → ghép vào prompt → LLM generate lịch trình
│   ├── embedding_service.py #  Embed hotel/review text → upsert vào Qdrant
│   ├── consumer.py         #   RabbitMQ: lắng nghe hotel/review events → tự động embed/delete
│   ├── prompts.py          #   Prompt templates cho RAG (tiếng Việt)
│   └── schemas.py          #   Pydantic models: SearchRequest, HotelScore, RAGItineraryRequest...
│
├── chat/                   # ═══ Nhiệm vụ 2: AI Chat Agent ═══
│   ├── router.py           #   POST /ai/chat — trả SSE stream hoặc JSON
│   ├── graph.py            #   Tạo LangGraph ReAct agent + quản lý checkpoint PostgreSQL
│   ├── service.py          #   Điều phối: stateful (checkpoint) vs stateless (CAG)
│   ├── tools.py            #   4 tools agent có thể gọi (search, details, availability, popular)
│   ├── prompts.py          #   System prompt cho agent (tiếng Việt, inject ngày hiện tại)
│   └── schemas.py          #   ChatMessage, ChatRequest, ChatResponse
│
├── scraping/               # ═══ Nhiệm vụ 3: Web Scraping ═══
│   ├── router.py           #   POST /scraping/extract — rate limit 2 lần/ngày
│   ├── scraping_service.py #   Pipeline: fetch HTML → clean → LLM extract → validate
│   ├── browser.py          #   Playwright: khởi tạo headless Chromium, render JS
│   ├── llm_extractor.py    #   Gửi clean HTML cho LLM, parse JSON ra structured data
│   ├── consumer.py         #   RabbitMQ: nhận crawler.job → scrape → publish kết quả
│   └── schemas.py          #   ExtractedHotelData, ExtractedReview, ScrapeResponse
│
├── booking/                # ═══ Nhiệm vụ 4: Booking Analytics ═══
│   ├── service.py          #   Embed booking text → Qdrant collection "bookings"
│   ├── consumer.py         #   RabbitMQ: booking.created/confirmed/cancelled → embed + analytics
│   └── schemas.py          #   BookingEventData, BookingAnalyticsEvent
│
└── shared/                 # ═══ Utilities dùng chung ═══
    ├── middleware.py        #   CorrelationIDMiddleware — tracking request across services
    ├── exceptions.py       #   AppError, LLMError, ScrapingError + global error handlers
    └── text_utils.py       #   chunk_text(), build_hotel_text(), count_tokens() (tiktoken)
```

---

## 3. Dependencies — Mỗi Thư Viện Làm Gì

### Runtime

| Package | Dùng ở đâu | Làm gì |
|---------|-----------|--------|
| `fastapi` | `main.py`, `*/router.py` | Web framework — tạo REST API, Swagger docs tự động |
| `uvicorn` | CLI | ASGI server — chạy FastAPI app |
| `pydantic-settings` | `config.py` | Đọc `.env` file, validate settings, type-safe config |
| `sqlalchemy[asyncio]` | `core/database.py`, `chat/tools.py` | ORM — map Python classes → PostgreSQL tables, async queries |
| `asyncpg` | (driver cho SQLAlchemy) | PostgreSQL async driver — SQLAlchemy dùng ngầm |
| `openai` | `core/llm.py`, `core/embedding.py` | Gọi OpenAI API — chat completions + text embeddings |
| `httpx` | `core/llm.py` | HTTP client async — gọi Ollama REST API |
| `qdrant-client` | `core/qdrant.py`, search, tools | Client cho Qdrant vector DB — upsert/search/delete vectors |
| `aio-pika` | `core/rabbitmq.py`, `*/consumer.py` | RabbitMQ client async — publish/consume messages |
| `tiktoken` | `shared/text_utils.py` | Đếm tokens (tokenizer của OpenAI) — dùng khi chunking text |
| `playwright` | `scraping/browser.py` | Headless browser — render JavaScript, giả lập trình duyệt |
| `beautifulsoup4` | `scraping/scraping_service.py` | Parse HTML — bỏ script/style/nav, giữ nội dung chính |
| **`langchain-openai`** | `chat/graph.py` | **Xem mục 4 bên dưới** |
| **`langgraph`** | `chat/graph.py`, `chat/service.py` | **Xem mục 4 bên dưới** |
| **`langgraph-checkpoint-postgres`** | `chat/graph.py` | **Xem mục 4 bên dưới** |

### Dev

| Package | Làm gì |
|---------|--------|
| `ruff` | Linter + formatter cực nhanh (viết bằng Rust) |
| `pytest` + `pytest-asyncio` | Test framework + support async tests |
| `pytest-cov` | Coverage report |

---

## 4. LangChain vs LangGraph — Phân Biệt Rõ

Đây là phần hay bị nhầm nhất. Hai thư viện này **khác nhau hoàn toàn** về vai trò:

### LangChain — "Thư viện linh kiện"

LangChain cung cấp **các building blocks** riêng lẻ. Project này dùng đúng 3 thứ từ LangChain:

**1. `ChatOpenAI`** — wrapper gọi OpenAI/Ollama/Alibaba chat API

```python
# chat/graph.py
from langchain_openai import ChatOpenAI

# OpenAI (mặc định)
llm = ChatOpenAI(model="gpt-4o-mini", api_key="sk-...", streaming=True)

# Alibaba Cloud (Qwen) — dùng base_url DashScope compatible
llm = ChatOpenAI(model="qwen-plus", base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                 api_key="sk-...", streaming=True)

# Ollama (local)
llm = ChatOpenAI(model="llama3.2", base_url="http://localhost:11434/v1",
                 api_key="ollama", streaming=True)
```

Tại sao không dùng `openai` SDK trực tiếp? Vì LangGraph yêu cầu model phải là `BaseChatModel`
của LangChain để tích hợp vào agent graph. `ChatOpenAI` wrap OpenAI SDK và thêm interface
mà LangGraph cần (streaming events, tool calling format...). Cả 3 providers đều tương thích
vì Ollama và DashScope đều implement OpenAI-compatible API.

**2. `@tool` decorator** — khai báo tool cho agent

```python
# chat/tools.py
from langchain_core.tools import tool

@tool
async def search_hotels(query: str, city: str | None = None) -> str:
    """Search for hotels using natural language."""
    # ... logic tìm kiếm ...
    return "Found 5 hotels matching..."
```

Decorator `@tool` làm 2 việc:
- Parse docstring + type hints → tạo JSON schema (tên tool, mô tả, params)
- LLM đọc schema này để biết khi nào nên gọi tool nào, với params gì

**3. `HumanMessage` / `AIMessage`** — message format chuẩn

```python
# chat/service.py
from langchain_core.messages import AIMessage, HumanMessage

lc_messages = [HumanMessage(content="tìm hotel ở Đà Nẵng")]
```

LangGraph agent nhận input dạng LangChain messages, không phải dict `{"role": "user", ...}`.

**Tổng kết: LangChain trong project này = ChatOpenAI + @tool + Message types. Không dùng chains, không dùng RAG của LangChain.**

---

### LangGraph — "Bộ não điều khiển agent"

LangGraph là framework **xây dựng và chạy AI agent**. Nó quyết định:
- Agent nên trả lời luôn hay gọi tool?
- Gọi tool nào, với params gì?
- Sau khi có kết quả tool, nên gọi thêm tool hay trả lời?
- Lưu trạng thái hội thoại ở đâu?

**1. `create_react_agent()`** — tạo ReAct agent graph

```python
# chat/graph.py
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(
    model=llm,              # ChatOpenAI (LangChain)
    tools=ALL_TOOLS,        # 4 tools với @tool (LangChain)
    prompt=_build_prompt,   # callable: system prompt + trim last 20 messages
    checkpointer=checkpointer,  # AsyncPostgresSaver (lưu state)
)
```

`create_react_agent` tạo ra một **graph** (đồ thị) với vòng lặp ReAct:

```
                    ┌─────────────────────┐
                    │   LLM suy nghĩ      │
         ┌────────►│   (ChatOpenAI)       │◄────────┐
         │         └──────────┬───────────┘         │
         │                    │                      │
         │            Quyết định:                    │
         │         ┌──────┴──────┐                   │
         │     Trả lời     Gọi tool                  │
         │         │            │                    │
         │         ▼            ▼                    │
         │    END (trả     Chạy tool              Tool trả
         │    response)    (search_hotels,        kết quả
         │                  get_details...)    ────────┘
         │
    Load checkpoint                    Save checkpoint
    (nếu có conversation_id)           (tự động sau mỗi turn)
```

**Ví dụ thực tế — Agent xử lý 2 turn:**

```
Turn 1: User: "tìm hotel ở Đà Nẵng"
  → LLM đọc 4 tool schemas → quyết định gọi search_hotels(query="hotel Đà Nẵng")
  → Tool chạy: embed query → Qdrant search → PostgreSQL fetch → trả "Found 5 hotels..."
  → LLM đọc kết quả tool → format thành câu trả lời tự nhiên
  → Checkpoint lưu: [HumanMessage, ToolCall, ToolResult, AIMessage]

Turn 2: User: "cho tôi xem chi tiết hotel thứ 2"
  → Checkpoint load: agent thấy lại toàn bộ turn 1 (kể cả tool results với hotel IDs)
  → LLM biết "hotel thứ 2" là hotel nào → gọi get_hotel_details(hotel_id="...")
  → Tool trả chi tiết + rooms + reviews
  → LLM format response
  → Checkpoint cập nhật thêm turn 2
```

**2. `AsyncPostgresSaver`** — persist agent state vào PostgreSQL

```python
# chat/graph.py
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

pool = AsyncConnectionPool(conninfo="postgresql://...")
checkpointer = AsyncPostgresSaver(pool)
await checkpointer.setup()  # Tạo 4 tables + indexes (xem bên dưới)
```

Checkpoint lưu **toàn bộ state** của agent:
- Messages (user + assistant)
- Tool calls (agent quyết định gọi tool nào, params gì)
- Tool results (kết quả trả về từ tool)

Keyed by `thread_id` = `conversation_id`. Khi restart server, conversations vẫn còn.

**4 tables trong PostgreSQL:**

| Table | Vai trò | Primary Key |
|-------|---------|-------------|
| `checkpoints` | Snapshot agent state (messages, metadata) | `(thread_id, checkpoint_ns, checkpoint_id)` |
| `checkpoint_blobs` | Binary data lớn (serialized state) | `(thread_id, checkpoint_ns, channel, version)` |
| `checkpoint_writes` | Pending writes chưa commit vào checkpoint | `(thread_id, checkpoint_ns, checkpoint_id, task_id, idx)` |
| `checkpoint_migrations` | Track migration version | `(v)` |

**Lưu ý quan trọng — Tạo tables lần đầu:**

`AsyncPostgresSaver.setup()` chạy migrations bao gồm `CREATE INDEX CONCURRENTLY` — lệnh này
**không thể chạy trong transaction block**. Nếu `setup()` thất bại (log: `Checkpoint DB unavailable`),
cần tạo tables thủ công bằng cách chạy script với `autocommit=True`:

```python
# Script tạo checkpoint tables thủ công
import asyncio
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def main():
    conn = await AsyncConnection.connect(
        "postgresql://travelmind:secret@localhost:5432/travelmind", autocommit=True
    )
    pool = AsyncConnectionPool(conninfo="postgresql://travelmind:secret@localhost:5432/travelmind")
    await pool.open()
    cp = AsyncPostgresSaver(pool)
    for migration in cp.MIGRATIONS:
        try:
            await conn.execute(migration)
        except Exception:
            pass  # Skip nếu đã tồn tại
    await conn.close()
    await pool.close()
    print("Checkpoint tables created!")

asyncio.run(main())
```

Hoặc đơn giản hơn, chạy SQL trực tiếp trong PostgreSQL container (xem Section 17 — Trace Lỗi).

**Message trimming** — tránh lag khi conversation dài:

Checkpoint lưu tất cả, nhưng LLM chỉ nhận **20 messages gần nhất** (cấu hình qua
`CHECKPOINT_MESSAGES_LIMIT`). Hàm `_build_prompt(state)` trim messages trước khi gửi LLM,
đảm bảo không cắt giữa chuỗi tool call (luôn bắt đầu từ `HumanMessage`).

```
Checkpoint (PostgreSQL): 100 messages (full history)
                              ↓ _build_prompt() trim
LLM nhận:  SystemMessage + 20 messages gần nhất
```

**3. `astream_events()`** — streaming response từ agent

```python
# chat/service.py
async for event in agent.astream_events({"messages": messages}, config=config, version="v2"):
    if event["event"] == "on_chat_model_stream":
        chunk = event["data"]["chunk"]
        if chunk.content and not chunk.tool_call_chunks:  # bỏ qua tool call chunks
            yield chunk.content  # chỉ yield text chunks cho user
```

`astream_events` emit nhiều loại events (tool start, tool end, LLM stream...).
Service chỉ lọc `on_chat_model_stream` — những text chunks mà LLM đang generate cho user.
Tool call chunks bị bỏ qua (user không cần thấy JSON gọi tool).

**Tổng kết: LangGraph = agent loop (ReAct) + checkpointing (PostgreSQL) + streaming events. LangChain cung cấp linh kiện (model, tools, messages), LangGraph điều phối chúng.**

---

## 5. Tầng Core — Infrastructure (`core/`)

Folder `core/` chứa code kết nối tới **external services**. Không có business logic ở đây.

### `core/llm.py` — Gọi LLM (Chat + Text Generation)

```python
class LLMClient:
    # Dùng cho: RAG itinerary, scraping extraction (KHÔNG phải chat agent)
    # Chat agent dùng ChatOpenAI của LangChain (khác!)

    async def chat(messages, temperature, max_tokens, response_format) -> str
    async def chat_stream(messages) -> AsyncGenerator[str]
```

**3 LLM Providers** — switch bằng `LLM_PROVIDER` trong `.env`:

| Provider | `LLM_PROVIDER` | Model mặc định | API Base URL |
|----------|----------------|-----------------|--------------|
| **OpenAI** | `openai` | `gpt-4o-mini` | `https://api.openai.com/v1` (mặc định SDK) |
| **Ollama** | `ollama` | `llama3.2` | `http://localhost:11434/v1` (local) |
| **Alibaba Cloud** | `alibaba` | `qwen-plus` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |

Cả 3 providers đều dùng **OpenAI SDK** (`AsyncOpenAI`) vì Ollama và Alibaba Cloud (DashScope)
cung cấp endpoint tương thích OpenAI. Chỉ cần thay `base_url` + `api_key`:

```python
# OpenAI (mặc định)
self._client = AsyncOpenAI(api_key=settings.openai_api_key)

# Alibaba Cloud (DashScope compatible)
self._client = AsyncOpenAI(
    api_key=settings.alibaba_api_key,
    base_url=settings.alibaba_base_url,  # https://dashscope-intl.aliyuncs.com/compatible-mode/v1
)

# Ollama (local)
self._client = AsyncOpenAI(api_key="ollama", base_url=f"{settings.ollama_base_url}/v1")
```

Tại sao có 2 cách gọi LLM?

| | `LLMClient` (core/llm.py) | `ChatOpenAI` (chat/graph.py) |
|-|--------------------------|------------------------------|
| Dùng cho | RAG, scraping extraction | Chat agent (LangGraph) |
| Thư viện | `openai` SDK trực tiếp | `langchain-openai` wrapper |
| Tại sao | Đơn giản, không cần agent | LangGraph yêu cầu BaseChatModel |
| Providers | OpenAI / Ollama / Alibaba | OpenAI / Ollama / Alibaba |

### `core/embedding.py` — Text → Vector

```python
class EmbeddingClient(Protocol):
    async def embed(texts: list[str]) -> list[list[float]]  # ["hello"] → [[0.1, 0.2, ..., 0.1536]]

class OpenAIEmbeddingClient:    # gọi OpenAI embeddings API
class AlibabaEmbeddingClient:   # gọi DashScope embeddings API (OpenAI-compatible endpoint)
class OllamaEmbeddingClient:    # gọi Ollama /api/embed HTTP (riêng, không qua OpenAI SDK)
```

**Embedding models theo provider:**

| Provider | Model | Dimensions | Ghi chú |
|----------|-------|------------|---------|
| OpenAI | `text-embedding-3-small` | 1536 | Mặc định, chất lượng tốt |
| Alibaba | `text-embedding-v3` | 1024 | DashScope, chi phí thấp hơn |
| Ollama | `nomic-embed-text` | 768 | Local, miễn phí |

> **Lưu ý**: Khi switch provider, embedding dimensions có thể khác nhau. Cần chạy lại
> `POST /ai/sync` để re-embed toàn bộ data vào Qdrant với model mới. Qdrant collections
> sẽ được recreate tự động nếu dimensions thay đổi.

Mọi text trước khi lưu vào Qdrant đều đi qua `embed()` → vector N chiều.
Hai đoạn text ý nghĩa giống nhau → vectors gần nhau → tìm được bằng cosine similarity.

### `core/qdrant.py` — Vector Database

Khi startup, tạo 4 collections (nếu chưa có):

| Collection | Chứa gì | Payload kèm vector |
|-----------|---------|---------------------|
| `hotels` | Text chunks của hotel (name, description, amenities) | hotel_id, chunk_index, city, country, stars |
| `reviews` | Review text (title + comment) | review_id, hotel_id, rating |
| `bookings` | Booking context (hotel, dates, status) | booking_id, user_id, hotel_name |
| `response_cache` | Cached LLM responses (cho CAG) | query, response, created_at, ttl |

### `core/database.py` — PostgreSQL ORM (Read-Only)

SQLAlchemy async models map tới PostgreSQL tables do NestJS/Prisma sở hữu:

```
Hotel ──┬── Room ──── RoomAvailability (date, is_available, price)
        └── Review
```

AI service chỉ `SELECT`, không `INSERT/UPDATE/DELETE`.

### `core/rabbitmq.py` — Message Queue

```python
async def publish(exchange_name, routing_key, body)   # gửi event
async def consume(queue_name, exchange_name, routing_key, callback)  # lắng nghe event
```

Topic exchange `travelmind` — routing key pattern matching (vd: `hotel.*` match `hotel.created`).

### `core/cache.py` — CAG (Cache-Augmented Generation)

Giảm chi phí LLM bằng 2 tầng cache:

```
User query: "best hotels in Danang"
  │
  ▼
BasicCache (tầng 1 — in-memory LRU)
  │ normalize("best hotels in Danang") → exact match?
  │ HIT → trả response ngay (0ms, miễn phí)
  │ MISS ▼
  │
SemanticCache (tầng 2 — Qdrant vectors)
  │ embed query → tìm vector giống nhất trong response_cache collection
  │ cosine similarity ≥ 0.95? → HIT, promote lên BasicCache, trả response
  │ MISS ▼
  │
Agent chạy thật (gọi LLM + tools)
  │ → trả response → ghi vào cả 2 tầng cache
```

---

## 6. Module AI — Semantic Search + RAG (`ai/`)

### Luồng Semantic Search (`POST /ai/search`)

```
User: "khách sạn gần biển có hồ bơi"
  → EmbeddingClient.embed("khách sạn gần biển có hồ bơi") → vector [0.12, 0.34, ...]
  → Qdrant.search(collection="hotels", vector, filter={city?, stars?})
  → Trả về 20 kết quả gần nhất (cosine similarity)
  → Deduplicate by hotel_id (1 hotel có thể nhiều chunks)
  → PostgreSQL: fetch chi tiết hotels
  → Response: [{hotel_id, name, score, city, stars}, ...]
```

### Luồng RAG Itinerary (`POST /ai/rag/itinerary`)

```
User: "lịch trình 3 ngày ở Đà Nẵng"
  → embed query → Qdrant search top K hotels
  → Build context: "Hotel 1: Sunrise Beach, 4 sao, rating 4.5, amenities: pool, spa..."
  → LLM(system_prompt + context + user_request) → lịch trình day-by-day
  → Response: { itinerary: "Ngày 1: Check-in Sunrise Beach..." }
```

### Luồng Sync (`POST /ai/sync`)

```
→ SELECT tất cả active hotels từ PostgreSQL
→ Mỗi hotel: build_hotel_text() → chunk_text(500 tokens, 50 overlap) → embed → upsert Qdrant
→ SELECT tất cả reviews từ PostgreSQL
→ Mỗi review: embed → upsert Qdrant
→ Response: { synced_hotels: 50, synced_reviews: 200 }
```

Chạy 1 lần sau khi seed database, hoặc khi rebuild Qdrant.

### RabbitMQ Consumer (`ai/consumer.py`)

Lắng nghe events từ NestJS, tự động cập nhật Qdrant:

| Event | Hành động |
|-------|-----------|
| `hotel.created` | chunk text → embed → upsert Qdrant |
| `hotel.updated` | delete cũ → re-embed |
| `hotel.deleted` | delete khỏi Qdrant |
| `review.created` | embed → upsert Qdrant |
| `review.deleted` | delete khỏi Qdrant |

---

## 7. Module Chat — AI Agent (`chat/`)

### Tổng Quan

Chat module là phần phức tạp nhất. Gồm 4 file chính:

```
graph.py    → Tạo agent (LangGraph + checkpointer)
tools.py    → 4 tools agent có thể gọi
service.py  → Điều phối stateful vs stateless, streaming
router.py   → FastAPI endpoint, SSE format
```

### 4 Tools (`chat/tools.py`)

Agent có quyền gọi 4 tools, mỗi tool query data thật:

| Tool | Khi nào agent gọi | Data source | Trả về |
|------|-------------------|-------------|--------|
| `search_hotels` | User tìm hotel ("resort gần biển") | Qdrant → PostgreSQL | Top 5 hotels + relevance score |
| `get_hotel_details` | User muốn xem chi tiết ("cho xem hotel thứ 2") | PostgreSQL | Hotel + rooms + 5 reviews gần nhất |
| `check_room_availability` | User nói ngày cụ thể ("2-5 tháng 3") | PostgreSQL (RoomAvailability) | Rooms trống + tổng giá |
| `get_popular_hotels` | User hỏi "top", "best", "nổi tiếng" | PostgreSQL (sort rating) | Top N hotels theo rating |

Mỗi tool là async function trả về **string** (không phải JSON). LLM đọc string này rồi format
lại thành câu trả lời tự nhiên cho user.

### Hai Chế Độ (`chat/service.py`)

**Stateful** — khi NestJS gửi `conversation_id`:
```
→ LangGraph load checkpoint (toàn bộ messages + tool results cũ)
→ Chỉ thêm message mới vào
→ Agent xử lý → stream response
→ Checkpoint tự lưu state mới
→ KHÔNG dùng CAG (response phụ thuộc context, cache vô nghĩa)
```

**Stateless** — không có `conversation_id`:
```
→ Check CAG cache trước (BasicCache → SemanticCache)
→ HIT: trả cached response ngay (không tốn LLM)
→ MISS: chạy agent với ephemeral thread_id → stream → cache response
```

### Luồng End-to-End

```
Browser (Socket.io)
  │ emit('sendMessage', { message, conversationId })
  ▼
NestJS Chat Gateway (JWT auth)
  │ Save user message → PostgreSQL (ChatMessage)
  │ POST http://ai:8000/ai/chat (HTTP SSE)
  │   body: { messages: [{role:"user", content}], conversation_id, stream: true }
  │   ← CHỈ gửi message mới nhất (không gửi history)
  ▼
AI Service
  │ Stateful: checkpoint load history → agent xử lý → stream chunks
  │ SSE format: data: {"chunk": "The best"}\n\n ... data: [DONE]\n\n
  ▼
NestJS Chat Gateway
  │ Parse SSE chunks → emit('messageChunk') về browser
  │ Accumulate full response → save ChatMessage(role=ASSISTANT) → PostgreSQL
  ▼
Browser hiển thị real-time
```

---

## 8. Module Scraping (`scraping/`)

### Pipeline

```
URL → Playwright (headless Chromium, render JS, wait networkidle + 3s)
   → Raw HTML
   → BeautifulSoup (bỏ script, style, nav, footer, header, svg, collapse whitespace)
   → Clean text (~vài KB)
   → LLM extraction (temperature=0.1, prompt yêu cầu trả JSON)
   → Pydantic validation (ExtractedHotelData)
   → Response: { hotel: {...}, reviews: [...], raw_text_length }
```

### Tại sao dùng LLM thay CSS selectors?

CSS selectors (`div.hotel-card > h2`) dễ break khi website đổi layout.
LLM đọc hiểu **ngữ nghĩa** của text → robust hơn, 1 extractor dùng cho nhiều website.

### Rate Limiting

Demo mode giới hạn **2 scrapes/ngày** (in-memory counter, reset mỗi ngày).

---

## 9. Module Booking (`booking/`)

Chỉ có consumer, không có endpoint. Lắng nghe booking events từ NestJS:

| Event | Hành động |
|-------|-----------|
| `booking.created` | Build text → embed → upsert Qdrant "bookings" + publish `booking.analytics` |
| `booking.confirmed` | Re-embed + publish analytics |
| `booking.cancelled` | Delete embedding + publish analytics |

---

## 10. Shared (`shared/`)

| File | Làm gì |
|------|--------|
| `middleware.py` | Gắn `X-Correlation-ID` vào mọi request/response — tracking across services |
| `exceptions.py` | Error types: `LLMError` (502), `ScrapingError` (502), `EmbeddingError` (502) + global handlers |
| `text_utils.py` | `chunk_text(max_tokens=500, overlap=50)` — chia text dài thành chunks cho embedding |
| | `build_hotel_text(hotel)` — format hotel thành searchable text |
| | `count_tokens(text)` — đếm tokens bằng tiktoken (tokenizer OpenAI) |

---

## 11. Luồng Khởi Động (`main.py`)

```
lifespan() startup:
  1. init_clients()          → tạo LLMClient, EmbeddingClient, BasicCache
  2. RabbitMQ.connect()      → nếu lỗi: log warning, tiếp tục
  3. setup_checkpointer()    → tạo psycopg pool + AsyncPostgresSaver + tạo tables; nếu lỗi: log warning
  4. Qdrant.connect()        → nếu lỗi: log warning, tiếp tục
  5. init_semantic_cache()   → SemanticCache (chỉ nếu Qdrant OK)
  6. start_*_consumers()     → chỉ nếu cả RabbitMQ + Qdrant OK

lifespan() shutdown:
  1. shutdown_checkpointer() → đóng psycopg pool
  2. shutdown_clients()      → đóng LLM + embedding clients
  3. RabbitMQ.disconnect()
  4. Qdrant.disconnect()
```

**Nguyên tắc**: Server luôn khởi động thành công. Thiếu RabbitMQ → consumers tắt.
Thiếu Qdrant → search tắt. Thiếu PostgreSQL checkpoint → chat không nhớ history qua restart.

---

## 12. Dependency Injection (`dependencies.py`)

FastAPI `Depends()` inject clients vào route handlers:

| Dependency | Loại | Mô tả |
|-----------|------|-------|
| `get_llm_client()` | Singleton | OpenAI/Ollama/Alibaba LLM — dùng cho RAG, scraping |
| `get_embedding_client()` | Singleton | Text → vector — dùng cho embed, search |
| `get_cache_layer()` | Singleton | BasicCache + SemanticCache — dùng cho stateless chat |
| `get_db_session()` | Per-request | SQLAlchemy AsyncSession — PostgreSQL read-only |
| `get_qdrant_client()` | Per-request | Qdrant client |
| `get_rabbitmq_channel()` | Per-request | RabbitMQ channel |

---

## 13. Cấu Hình (`config.py`)

Pydantic Settings, load từ `.env`:

| Nhóm | Field | Mặc định | Ghi chú |
|------|-------|----------|---------|
| App | `app_env` | `development` | development / production / test |
| App | `log_level` | `info` | Đổi `debug` để xem chi tiết |
| LLM | `llm_provider` | `openai` | `openai`, `ollama`, hoặc `alibaba` |
| OpenAI | `openai_api_key` | — | Lấy từ platform.openai.com |
| OpenAI | `openai_model` | `gpt-4o-mini` | Model cho chat + extraction |
| OpenAI | `openai_embedding_model` | `text-embedding-3-small` | 1536 dimensions |
| Ollama | `ollama_base_url` | `http://localhost:11434` | Ollama server URL |
| Ollama | `ollama_model` | `llama3.2` | Local LLM miễn phí |
| Ollama | `ollama_embedding_model` | `nomic-embed-text` | Local embeddings |
| Alibaba | `alibaba_api_key` | — | Lấy từ DashScope Console |
| Alibaba | `alibaba_base_url` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | International endpoint |
| Alibaba | `alibaba_model` | `qwen-plus` | Qwen models: `qwen-turbo`, `qwen-plus`, `qwen-max` |
| Alibaba | `alibaba_embedding_model` | `text-embedding-v3` | DashScope embedding |
| DB | `database_url` | `postgresql+asyncpg://...` | PostgreSQL NestJS backend |
| DB | `checkpoint_database_url` | *(derived)* | Tự derive từ database_url, bỏ `+asyncpg` |
| Checkpoint | `checkpoint_messages_limit` | `20` | Chỉ gửi N messages gần nhất cho LLM |
| Qdrant | `qdrant_url` | `http://localhost:6333` | |
| RabbitMQ | `rabbitmq_url` | `amqp://guest:guest@localhost:5672/` | |
| CAG | `cag_basic_max_size` | `1000` | Max entries trong BasicCache |
| CAG | `cag_semantic_threshold` | `0.95` | Cosine similarity threshold |
| Scraping | `scraping_max_requests_per_day` | `2` | Rate limit demo mode |

---

## 14. RabbitMQ Events — Tổng Hợp

Exchange: `travelmind` (topic)

**AI service lắng nghe:**

| Routing Key | Queue | Module | Hành động |
|-------------|-------|--------|-----------|
| `hotel.created` | ai.hotel.created | ai/consumer.py | embed hotel → Qdrant |
| `hotel.updated` | ai.hotel.updated | ai/consumer.py | re-embed hotel |
| `hotel.deleted` | ai.hotel.deleted | ai/consumer.py | delete từ Qdrant |
| `review.created` | ai.review.created | ai/consumer.py | embed review → Qdrant |
| `review.deleted` | ai.review.deleted | ai/consumer.py | delete từ Qdrant |
| `booking.created` | ai.booking.created | booking/consumer.py | embed + publish analytics |
| `booking.confirmed` | ai.booking.confirmed | booking/consumer.py | re-embed + analytics |
| `booking.cancelled` | ai.booking.cancelled | booking/consumer.py | delete + analytics |
| `crawler.job` | ai.crawler.job | scraping/consumer.py | scrape URL |

**AI service publish:**

| Routing Key | Nội dung |
|-------------|---------|
| `crawler.completed` | Extracted hotel + review data |
| `booking.analytics` | Booking event (action, metadata) |

---

## 15. Tests (`tests/`)

- Framework: `pytest` + `pytest-asyncio`
- Tất cả external services được mock (không cần infrastructure thật)
- Chạy: `uv run pytest -v`

---

## 16. Chạy Project (Local với uv)

### Yêu Cầu

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — cài nhanh: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Docker — chạy infrastructure (PostgreSQL, RabbitMQ, Qdrant)

### Quick Start

```bash
# 1. Cài dependencies (tạo .venv tự động)
uv sync

# 2. Tạo file .env
cp .env.example .env
# → Chọn LLM provider và điền API key tương ứng (xem bên dưới)

# 3. Khởi động infrastructure (từ backend project)
cd ../backend && docker compose up -d postgres rabbitmq qdrant
cd ../ai

# 4. Chạy dev server
uv run uvicorn travelmind_ai.main:app --reload --port 8000

# 5. Sync data lần đầu (sau khi backend đã seed)
curl -X POST http://localhost:8000/ai/sync
```

Server sẵn sàng:

| URL | Mô tả |
|-----|-------|
| `http://localhost:8000` | API root |
| `http://localhost:8000/docs` | Swagger UI — test API trực tiếp |
| `http://localhost:8000/redoc` | ReDoc |
| `http://localhost:8000/health` | Health check (trạng thái RabbitMQ, Qdrant) |

### Cấu Hình `.env`

| Biến | Bắt buộc | Mặc định | Ghi chú |
|------|---------|----------|---------|
| `LLM_PROVIDER` | Không | `openai` | `openai`, `ollama`, hoặc `alibaba` |
| `OPENAI_API_KEY` | Có (nếu `openai`) | — | Lấy từ platform.openai.com |
| `ALIBABA_API_KEY` | Có (nếu `alibaba`) | — | Lấy từ DashScope Console |
| `ALIBABA_BASE_URL` | Không | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | Dùng `dashscope.aliyuncs.com` nếu China region |
| `DATABASE_URL` | Có | `postgresql+asyncpg://travelmind:secret@localhost:5432/travelmind` | Phải trùng với PostgreSQL của NestJS backend |
| `RABBITMQ_URL` | Không | `amqp://guest:guest@localhost:5672/` | |
| `QDRANT_URL` | Không | `http://localhost:6333` | |
| `LOG_LEVEL` | Không | `info` | Đổi sang `debug` để xem chi tiết |

**Lưu ý**: Server vẫn khởi động được khi thiếu RabbitMQ hoặc Qdrant — các tính năng phụ thuộc sẽ bị tắt và log warning.

### Infrastructure

Infrastructure chạy từ `backend/docker-compose.yml`:

```bash
# Khởi động
cd ../backend && docker compose up -d postgres rabbitmq qdrant

# Kiểm tra
cd ../backend && docker compose ps
```

| Service | Port | UI |
|---------|------|-----|
| PostgreSQL | `5432` | — |
| RabbitMQ | `5672` | `http://localhost:15672` (guest/guest) |
| Qdrant | `6333` | `http://localhost:6333/dashboard` |

### Sync Data (PostgreSQL → Qdrant)

Sau khi backend seed data xong, cần sync embeddings vào Qdrant:

```bash
# Cách 1: Từ backend project
cd ../backend && npx tsx prisma/sync-ai.ts

# Cách 2: Gọi API trực tiếp
curl -X POST http://localhost:8000/ai/sync
```

Chỉ cần chạy 1 lần sau khi seed, hoặc khi muốn rebuild Qdrant từ scratch.

### Chọn LLM Provider

Project hỗ trợ **3 LLM providers**, switch bằng `LLM_PROVIDER` trong `.env`:

#### Option 1: OpenAI (mặc định)

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-xxx     # Lấy từ platform.openai.com
OPENAI_MODEL=gpt-4o-mini       # Hoặc gpt-4o, gpt-4-turbo
```

#### Option 2: Alibaba Cloud — Qwen (DashScope)

```bash
LLM_PROVIDER=alibaba
ALIBABA_API_KEY=sk-xxx                    # Lấy từ DashScope Console
ALIBABA_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1  # International
# ALIBABA_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1    # China region
ALIBABA_MODEL=qwen-plus                  # Hoặc qwen-turbo (rẻ), qwen-max (mạnh nhất)
ALIBABA_EMBEDDING_MODEL=text-embedding-v3
```

**Lấy API key:** Vào [DashScope Console](https://dashscope.console.aliyun.com/apiKey) → tạo API key.
Lưu ý dùng đúng endpoint (intl vs china) khớp với region tạo key.

**Models Qwen:**

| Model | Tốc độ | Chất lượng | Chi phí | Dùng khi |
|-------|--------|------------|---------|----------|
| `qwen-turbo` | Nhanh nhất | Tốt | Thấp | Chat đơn giản, scraping |
| `qwen-plus` | Nhanh | Rất tốt | Trung bình | **Khuyên dùng** — cân bằng |
| `qwen-max` | Chậm hơn | Tốt nhất | Cao | RAG phức tạp, extraction khó |

#### Option 3: Ollama (Miễn Phí, Chạy Local)

```bash
# Cài Ollama (https://ollama.com) rồi pull models
ollama pull llama3.2
ollama pull nomic-embed-text

# Sửa .env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
```

#### So sánh 3 providers

| | OpenAI | Alibaba (Qwen) | Ollama |
|--|--------|----------------|--------|
| **Chi phí** | Trả phí | Trả phí (rẻ hơn) | Miễn phí |
| **Tốc độ** | Nhanh | Nhanh | Phụ thuộc GPU |
| **Tool calling** | Tốt nhất | Rất tốt | Hạn chế |
| **Tiếng Việt** | Tốt | Rất tốt | Khá |
| **Offline** | Không | Không | Có |
| **Cần GPU** | Không | Không | Nên có |

> **Khi switch provider**: Restart AI service. Nếu embedding model thay đổi dimensions,
> cần chạy `POST /ai/sync` để re-embed data vào Qdrant.

### Commands Thường Dùng

```bash
# Dev server (auto-reload khi sửa code)
uv run uvicorn travelmind_ai.main:app --reload --port 8000

# Tests (mock, không cần infrastructure)
uv run pytest -v
uv run pytest --cov          # kèm coverage

# Lint + auto-fix
uv run ruff check src/ --fix

# Cài Playwright browser (cần cho scraping)
uv run playwright install chromium

# Thêm dependency mới
uv add <package-name>
```

---

## 17. Trace Lỗi

### Kiểm Tra Nhanh

```bash
# 1. Health check
curl http://localhost:8000/health
# {"status":"ok","rabbitmq":"connected","qdrant":"connected"}

# 2. Xem log — set LOG_LEVEL=debug trong .env để verbose hơn

# 3. Trạng thái containers (chạy từ backend/)
cd ../backend && docker compose ps
cd ../backend && docker compose logs rabbitmq
cd ../backend && docker compose logs qdrant
```

### Bảng Lỗi Thường Gặp

| Triệu Chứng | Nguyên Nhân | Cách Fix |
|-------------|------------|---------|
| `RabbitMQ unavailable` (startup log) | RabbitMQ chưa chạy | `cd ../backend && docker compose up -d rabbitmq` |
| `Qdrant unavailable` (startup log) | Qdrant chưa chạy | `cd ../backend && docker compose up -d qdrant` |
| `Checkpoint DB unavailable` (startup log) | PostgreSQL chưa chạy hoặc tables chưa tạo | Xem **Lỗi Checkpoint** bên dưới |
| HTTP 502 `LLM request failed` | API key sai hoặc LLM provider chưa chạy | Xem **Lỗi LLM** bên dưới |
| HTTP 502 `Scraping failed` | Playwright timeout hoặc LLM parse lỗi | URL không hợp lệ hoặc trang chặn bot |
| `asyncpg` connection error | PostgreSQL sai URL | Kiểm tra `DATABASE_URL` |
| Agent không gọi tool | System prompt sai | Kiểm tra `chat/prompts.py` |
| Chat không nhớ lịch sử | Không gửi `conversation_id` | Đảm bảo NestJS gửi cùng conversation_id |

### Lỗi Checkpoint (LangGraph)

**Triệu chứng**: Chat trả 500, log hiện `UndefinedTable: relation "checkpoints" does not exist`

**Nguyên nhân**: `AsyncPostgresSaver.setup()` thất bại vì `CREATE INDEX CONCURRENTLY` không chạy được
trong transaction block. Tables checkpoint chưa được tạo.

**Cách fix — Tạo tables thủ công bằng SQL:**

```bash
# Chạy trong PostgreSQL container
docker exec $(docker ps --filter "name=postgres" -q | head -1) psql -U travelmind -d travelmind -c "
CREATE TABLE IF NOT EXISTS checkpoint_migrations (v INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL, parent_checkpoint_id TEXT,
    type TEXT, checkpoint JSONB NOT NULL, metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL, version TEXT NOT NULL, type TEXT NOT NULL, blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);
CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL, task_id TEXT NOT NULL, idx INTEGER NOT NULL,
    channel TEXT NOT NULL, type TEXT, blob BYTEA NOT NULL, task_path TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
"
```

Sau đó restart AI service. Hoặc dùng Python script (xem Section 4.2).

**Kiểm tra tables đã tồn tại:**

```bash
docker exec $(docker ps --filter "name=postgres" -q | head -1) \
  psql -U travelmind -d travelmind -c "\dt checkpoint*"
```

### Lỗi LLM

**OpenAI:**
```
AuthenticationError → OPENAI_API_KEY sai hoặc hết hạn
RateLimitError      → Vượt quota, thử lại sau
```

**Alibaba Cloud (Qwen):**
```
AuthenticationError (401) → ALIBABA_API_KEY sai hoặc chưa activate
    → Kiểm tra key tại: https://dashscope.console.aliyun.com/apiKey
    → Đảm bảo base_url đúng region (intl vs china):
      - Key từ alibabacloud.com → dùng dashscope-intl.aliyuncs.com
      - Key từ aliyun.com       → dùng dashscope.aliyuncs.com
```

**Test API key nhanh:**
```bash
# OpenAI
curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"

# Alibaba Cloud
curl https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions \
  -H "Authorization: Bearer $ALIBABA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-plus","messages":[{"role":"user","content":"hello"}],"max_tokens":10}'
```

**Ollama:**
```bash
ollama list               # phải thấy llama3.2 và nomic-embed-text
ollama pull llama3.2      # nếu thiếu
ollama pull nomic-embed-text
```

### Debug Qdrant

```bash
curl http://localhost:6333/collections              # xem tất cả collections
curl http://localhost:6333/collections/hotels        # xem collection cụ thể
# Hoặc dùng Dashboard: http://localhost:6333/dashboard
```

### Reset Hoàn Toàn

```bash
# Xóa toàn bộ data (volumes)
cd ../backend && docker compose down -v

# Khởi động lại sạch
cd ../backend && docker compose up -d
```
