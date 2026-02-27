# TravelMind AI Service

Python microservice xử lý AI/LLM và Web Scraping cho nền tảng TravelMind.

---

## Vai trò trong hệ thống

Service này là **worker chuyên biệt**, chỉ đảm nhận 2 việc mà Python làm tốt hơn Node.js:

1. **AI/LLM** — Text Embeddings, Vector Search, RAG
2. **Web Scraping** — Thu thập dữ liệu + bóc tách bằng AI

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
│   │   └── embedding.py        # Embedding client abstraction
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

## Giao tiếp với NestJS

### REST — NestJS → AI (đồng bộ — cần response ngay)

| NestJS gọi AI | Mô tả |
|-----------|-------|
| `POST /ai/search` | Semantic search hotels (trả về hotel IDs + scores) |
| `POST /ai/similar/{hotel_id}` | Hotels tương tự (vector similarity) |
| `POST /ai/rag/itinerary` | Generate lịch trình du lịch (RAG) |
| `POST /scraping/extract` | Scrape 1 URL + extract structured data |

### NestJS Backend API (33 endpoints hiện tại)

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
| Search | `GET /api/search?q=...` (Elasticsearch full-text) |
| Crawler | `POST /api/crawler/trigger`, `GET /api/crawler/status` |

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

Dùng chung PostgreSQL và RabbitMQ với NestJS. Thêm **Qdrant** container riêng cho vector storage:

```yaml
# Thêm vào docker-compose.yml của backend/

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"   # REST API
      - "6334:6334"   # gRPC
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334

  ai-service:
    build:
      context: ../ai
      dockerfile: Dockerfile.dev
    ports:
      - "8000:8000"
    volumes:
      - ../ai/src:/app/src
    depends_on:
      - postgres
      - rabbitmq
      - qdrant
    environment:
      - DATABASE_URL=postgresql+asyncpg://travelmind:secret@postgres:5432/travelmind
      - QDRANT_URL=http://qdrant:6333
      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OLLAMA_URL=http://ollama:11434

  # Optional: Local LLM cho dev không cần OpenAI key
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

volumes:
  qdrant_data:
  ollama_data:
```

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

# Start dependencies (cùng NestJS project)
cd ../backend && docker compose up -d postgres rabbitmq qdrant

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
├── backend/      ← NestJS API (port 3000)
├── ai/           ← Python AI service (port 8000) — repo này
├── frontend/     ← React SPA (port 5173)
└── docker-compose.yml

# Hoặc multi-repo
github.com/org/travelmind-backend     ← NestJS backend
github.com/org/travelmind-ai          ← Python AI (repo này)
github.com/org/travelmind-frontend    ← React frontend
```
