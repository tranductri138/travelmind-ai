# TravelMind AI Service

Python microservice xử lý AI/LLM và Web Scraping cho nền tảng TravelMind.

---

## Vai trò trong hệ thống

Service này là **worker chuyên biệt**, chỉ đảm nhận 3 việc mà Python làm tốt hơn Node.js:

1. **AI/LLM** — Text Embeddings, Vector Search, RAG
2. **AI Chat Agent** — LangGraph ReAct agent with function calling, checkpointing, CAG
3. **Web Scraping** — Thu thập dữ liệu + bóc tách bằng AI

Mọi thứ khác (Auth, CRUD, Booking, Payment...) thuộc về [NestJS Backend](../backend). Service này không có UI, không public API — chỉ NestJS gọi vào qua REST internal và RabbitMQ.

```
Client ──► NestJS Backend (port 3000) ──► Python AI Service (port 8000)
                │                                │
                └──────── PostgreSQL ◄────────────┘ (READ hotels/reviews)
                └──────── RabbitMQ  ◄─────────────┘
                                                 │
                                          Qdrant ◄┘ (vector storage riêng)
```

---

## Tech Stack

| | Technology | Lý do chọn |
|-|-----------|-----------|
| Language | Python 3.12 | Hệ sinh thái AI/ML tốt nhất |
| Package Manager | **uv** (Astral) | Nhanh 10-100x so với pip, lockfile deterministic |
| Framework | FastAPI | Async, auto docs, Pydantic native |
| LLM | OpenAI GPT-4o (prod) / Ollama (dev) | Ollama chạy local free khi dev |
| Embeddings | OpenAI text-embedding-3-small | 1536 dims, rẻ ($0.02/1M tokens) |
| Vector DB | **Qdrant** | Viết bằng Rust, HNSW native, filtering mạnh, Docker 1 lệnh, tách biệt vector khỏi PostgreSQL |
| Queue | RabbitMQ (aio-pika) | Dùng chung broker với NestJS |
| Scraping | Playwright + BeautifulSoup4 | Playwright render JS, BS4 parse |
| AI Extraction | LLM-based parsing | Robust hơn CSS selectors |
| Agent Framework | LangGraph (ReAct agent) | Function calling, checkpointing built-in |
| LangChain | langchain-openai | Chat model integration for LangGraph |
| Caching | CAG (BasicCache + SemanticCache) | LRU in-memory + Qdrant vector similarity |
| Linting | Ruff | Cùng team Astral, cực nhanh |

---

## Project Structure

```
travelmind-ai/
├── pyproject.toml              # uv config + dependencies
├── uv.lock                     # Lockfile — commit vào git
├── .python-version             # 3.12
├── Dockerfile
├── Dockerfile.dev
├── .env.example
│
├── src/travelmind_ai/
│   ├── main.py                 # FastAPI app
│   ├── config.py               # Pydantic Settings
│   ├── dependencies.py         # DI: db session, llm client
│   │
│   ├── core/                   # Kết nối infrastructure
│   │   ├── database.py         # SQLAlchemy async (READ hotels/reviews từ PG của NestJS)
│   │   ├── rabbitmq.py         # aio-pika connection
│   │   ├── qdrant.py           # Qdrant client connection
│   │   ├── llm.py              # LLM abstraction (OpenAI / Ollama)
│   │   ├── embedding.py        # Embedding client abstraction
│   │   └── cache.py            # CAG: BasicCache (LRU) + SemanticCache (Qdrant)
│   │
│   ├── ai/                     # ── Nhiệm vụ 1: AI/LLM ──
│   │   ├── router.py           # Endpoints: /ai/search, /ai/rag/*
│   │   ├── embedding_service.py    # Text → vector → Qdrant collection
│   │   ├── search_service.py       # Cosine similarity search
│   │   ├── rag_service.py          # Retrieve → Augment → Generate
│   │   ├── prompts.py              # Prompt templates
│   │   ├── schemas.py
│   │   └── consumer.py             # RabbitMQ: hotel.created/updated/deleted, review.created/deleted → Qdrant
│   │
│   ├── chat/                  # ── Nhiệm vụ 3: AI Chat Agent ──
│   │   ├── router.py          # POST /ai/chat (SSE streaming)
│   │   ├── graph.py           # LangGraph ReAct agent + AsyncPostgresSaver
│   │   ├── tools.py           # 4 tools: search_hotels, get_hotel_details, check_room_availability, get_popular_hotels
│   │   ├── service.py         # Stateful (checkpoint) + Stateless (CAG) modes
│   │   ├── prompts.py         # Agent system prompt
│   │   └── schemas.py         # ChatRequest, ChatResponse
│   │
│   ├── scraping/               # ── Nhiệm vụ 2: Web Scraping ──
│   │   ├── router.py           # Endpoints: /scraping/extract
│   │   ├── scraping_service.py     # Orchestrate: fetch → extract → return
│   │   ├── browser.py              # Playwright lifecycle
│   │   ├── llm_extractor.py        # HTML → LLM → structured JSON
│   │   ├── schemas.py
│   │   └── consumer.py             # RabbitMQ: crawler.job → crawl
│   │
│   └── shared/
│       ├── middleware.py        # Correlation ID
│       ├── exceptions.py
│       └── text_utils.py       # Chunking, token counting
│
└── tests/
```

---

## Nhiệm vụ 1: AI/LLM

### Text Embeddings + Qdrant

Chuyển text thành vectors 1536 chiều (OpenAI text-embedding-3-small), lưu vào **Qdrant** — vector database chuyên dụng viết bằng Rust. Hai đoạn text ý nghĩa giống nhau → vectors gần nhau → tìm kiếm bằng cosine similarity.

**Tại sao Qdrant thay vì pgvector:**

| | pgvector | Qdrant |
|-|----------|--------|
| Bản chất | Extension PostgreSQL | Vector DB chuyên dụng (Rust) |
| Performance | Tốt ở quy mô nhỏ, chậm dần khi scale | HNSW native, SIMD acceleration, nhanh ổn định |
| Filtering | SQL WHERE (join với bảng khác) | **Payload filtering tích hợp** — filter + vector search cùng lúc, không cần JOIN |
| Scaling | Vertical only (scale PG) | Horizontal sharding + replication built-in |
| Quantization | Không có | Scalar, Binary, Product quantization — giảm RAM 4-8x |
| Multitenancy | Không | Native tenant isolation |
| Ops | Chung với PG (migration, backup phức tạp) | Container riêng, stateless deploy, snapshot API |

Qdrant chạy Docker riêng, tách biệt hoàn toàn khỏi PostgreSQL. Python service kết nối Qdrant qua `qdrant-client`, NestJS không cần biết Qdrant tồn tại.

**Qdrant concepts:**
- **Collection** = tương đương 1 "bảng" — vd: `hotel_embeddings`, `review_embeddings`
- **Point** = 1 vector + payload (metadata JSON) — vd: vector + `{hotel_id, name, location}`
- **Payload** = metadata đính kèm vector, dùng để **filter** khi search — vd: chỉ search hotels ở "Đà Nẵng"

**Khi nào chạy:**
- NestJS tạo hotel mới → publish `hotel.created` → AI consumer tạo embedding → upsert vào Qdrant collection
- NestJS tạo review mới → publish `review.created` → AI consumer embed → upsert Qdrant
- Hotel update → publish `hotel.updated` → AI cập nhật point trong Qdrant
- Hotel/review xóa → publish `hotel.deleted` / `review.deleted` → AI xóa point khỏi Qdrant (đồng bộ xóa)

### Semantic Search

User search bằng ngôn ngữ tự nhiên thay vì keyword. NestJS gọi `POST /ai/search` với query text → service embed query → Qdrant tìm points có vector gần nhất (cosine similarity) + filter theo payload (location, rating...) → trả về hotel IDs + score → NestJS fetch full data từ Prisma.

### RAG (Retrieval-Augmented Generation)

Gợi ý lịch trình du lịch dựa trên dữ liệu thực:

1. **Retrieve** — Qdrant search hotels + reviews liên quan đến yêu cầu user
2. **Augment** — Ghép dữ liệu thực vào prompt template
3. **Generate** — LLM tạo lịch trình JSON, grounded trong data thực (không hallucinate)

---

## Nhiệm vụ 2: Web Scraping

### Tại sao dùng AI thay vì CSS selectors

CSS selectors (`div.hotel-card > h2`) brittle — website thay đổi layout là break. LLM đọc hiểu ngữ nghĩa của text nên robust hơn và 1 extractor dùng được cho nhiều sources.

### Pipeline

```
URL → Playwright (render JS, scroll) → raw HTML
    → BeautifulSoup (bỏ script/style/nav, giữ content)
    → LLM extraction (cleaned text → structured JSON)
    → Pydantic validation
    → Return / Publish qua RabbitMQ
```

**Khi nào chạy:**
- NestJS admin trigger → publish `crawler.job` → AI consumer crawl + extract → publish `scraping.completed` → NestJS consume update DB
- Có thể gọi trực tiếp `POST /scraping/extract` cho one-off jobs

---

## Nhiệm vụ 3: AI Chat Agent (LangGraph)

### Kiến trúc

Chat module dùng **LangGraph ReAct agent** — không phải RAG chatbot thuần text. Agent có access tới 4 tools để truy vấn dữ liệu thực:

| Tool | Mô tả |
|------|--------|
| `search_hotels` | Tìm khách sạn bằng ngôn ngữ tự nhiên (Qdrant vector search) |
| `get_hotel_details` | Lấy chi tiết hotel + rooms + reviews từ PostgreSQL |
| `check_room_availability` | Kiểm tra phòng trống theo ngày/số khách |
| `get_popular_hotels` | Top hotels theo rating, filter theo city |

### Hai chế độ hoạt động

**Stateful** (có `conversation_id`):
- LangGraph load full state từ checkpoint (messages + tool calls + tool results)
- Chỉ cần gửi message mới — checkpoint có history
- Không dùng CAG (response phụ thuộc context)

**Stateless** (không `conversation_id`):
- One-shot, pass tất cả messages
- Dùng CAG: check cache trước, cache response sau

### CAG (Cache-Augmented Generation)

Giảm chi phí LLM bằng 2 tầng cache:

1. **BasicCache** — In-memory LRU, exact match, O(1) lookup
2. **SemanticCache** — Qdrant vector similarity (cosine ≥ 0.95), tốn 1 embed call

Flow: BasicCache → (miss) → SemanticCache → (miss) → Agent → cache response

### Checkpointing (AsyncPostgresSaver)

`AsyncPostgresSaver` persist full agent state vào PostgreSQL, keyed by `thread_id` = `conversation_id`.
Agent nhớ cả tool calls và tool results giữa các lượt chat — conversations sống sót qua restart.

Ví dụ:
- Turn 1: "find hotels in Danang" → agent gọi search_hotels → trả 5 kết quả
- Turn 2: "tell me about the 2nd one" → agent load checkpoint → thấy tool_result → gọi get_hotel_details trực tiếp

---

## Giao tiếp với NestJS

### REST — NestJS → AI (đồng bộ — cần response ngay)

| NestJS gọi AI | Mô tả |
|-----------|-------|
| `POST /ai/search` | Semantic search hotels (trả về hotel IDs + scores) |
| `POST /ai/similar/{hotel_id}` | Hotels tương tự (vector similarity) |
| `POST /ai/rag/itinerary` | Generate lịch trình du lịch (RAG) |
| `POST /scraping/extract` | Scrape 1 URL + extract structured data |
| `POST /ai/chat` | Chat với AI agent (SSE streaming hoặc JSON) |

### NestJS Backend API (36 endpoints hiện tại)

AI service cần biết các endpoints này khi đọc data hoặc debug:

| Module | Endpoints |
|--------|-----------|
| Health | `GET /health` |
| Auth | `POST /api/auth/register, login, refresh, logout` |
| Users | `GET, PATCH, DELETE /api/users/me` |
| Hotels | `GET /api/hotels` (search, nearby, :id), `POST, PATCH, DELETE /api/hotels/:id`, `DELETE /api/hotels/:id/permanent` |
| Rooms | `GET, POST /api/hotels/:hotelId/rooms`, `GET .../availability`, `DELETE, DELETE .../permanent` |
| Bookings | `GET, POST /api/bookings`, `GET, DELETE /api/bookings/:id`, `PATCH .../cancel` |
| Payments | `POST /api/payments/intent/:bookingId`, `POST /api/payments/webhook` |
| Reviews | `GET, POST /api/reviews`, `DELETE /api/reviews/:id` |
| Search | `GET /api/search?q=...` (PostgreSQL full-text + AI semantic) |
| Crawler | `POST /api/crawler/trigger`, `GET /api/crawler/status` |
| Chat | `GET /api/chat/conversations`, `GET .../conversations/:id`, `DELETE .../conversations/:id`, `WS /chat` |

### RabbitMQ (bất đồng bộ — fire and forget)

| Event | Hướng | Mô tả |
|-------|-------|-------|
| `hotel.created` | NestJS → AI | Auto tạo embedding |
| `hotel.updated` | NestJS → AI | Update embedding trong Qdrant |
| `hotel.deleted` | NestJS → AI | Xóa embedding khỏi Qdrant (payload: `hotelId`, `permanent`) |
| `review.created` | NestJS → AI | Embed review |
| `review.deleted` | NestJS → AI | Xóa review embedding khỏi Qdrant (payload: `reviewId`, `hotelId`) |
| `crawler.job` | NestJS → AI | Trigger crawl task |
| `embedding.completed` | AI → NestJS | Thông báo embed xong |
| `scraping.completed` | AI → NestJS | Trả data đã extract |

---

## Shared Infrastructure

Dùng chung PostgreSQL và RabbitMQ với NestJS. Thêm **Qdrant** riêng cho vector storage.
Infrastructure được quản lý bởi NestJS backend project (`backend/docker-compose.yml`).

**Qdrant Dashboard**: Truy cập `http://localhost:6333/dashboard` để xem collections, points, test search trực tiếp trên UI.

---

## Getting Started

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup
cd ai
cp .env.example .env
uv sync

# Start dependencies (từ backend project)
# cd ../backend && docker compose up -d postgres rabbitmq qdrant

# Dev server
uv run uvicorn travelmind_ai.main:app --reload --port 8000

# Playwright browsers (cho scraping)
uv run playwright install chromium

# Tests
uv run pytest

# Lint
uv run ruff check src/
```

---

## Tổ chức repo

```
# Monorepo hiện tại
TRAVELMIND/
├── backend/      ← NestJS API (port 3000) + docker-compose.yml
├── ai/           ← Python AI service (port 8000) — repo này
└── frontend/     ← React SPA (port 5173)

# Hoặc multi-repo
github.com/org/travelmind-backend     ← NestJS backend
github.com/org/travelmind-ai          ← Python AI (repo này)
github.com/org/travelmind-frontend    ← React frontend
```
