# TravelMind AI

FastAPI microservice — semantic search, RAG, LangGraph agent, web scraping, data sync.
Kết nối NestJS (port 3000) qua REST + RabbitMQ. PostgreSQL là **read-only**.

- **Python** 3.12 | **uv** | **Port** 8000 | Swagger `/docs`
- **LLM**: 3 providers — OpenAI / Ollama / Alibaba Cloud (Qwen)
- **Qdrant** 6333 | **RabbitMQ** 5672 | **PostgreSQL** read-only
- **Checkpoint**: LangGraph agent state → PostgreSQL (3 tables: `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`)

## LLM Provider (switch trong `.env`)

```bash
LLM_PROVIDER=openai    # OpenAI gpt-4o-mini + text-embedding-3-small
LLM_PROVIDER=ollama    # Ollama llama3.2 + nomic-embed-text (local, free)
LLM_PROVIDER=alibaba   # Alibaba Cloud qwen-plus + text-embedding-v3 (DashScope)
```

## Commands

```bash
uv sync                                # Install dependencies
uv run uvicorn travelmind_ai.main:app --reload --port 8000  # Dev server
uv run pytest -v                       # Tests (17 tests, all mock)
uv run ruff check src/ --fix           # Lint
curl -X POST http://localhost:8000/ai/sync  # Sync PostgreSQL → Qdrant
```

## Context Files

Load file phù hợp với task đang làm:

| File | Load khi nào |
|------|-------------|
| `docs/claude/context-general.md` | **Luôn load** — stack, layout, conventions, commands |
| `docs/claude/context-agent.md` | Làm chat agent, LangGraph, tools, CAG, streaming, NestJS chat integration |
| `docs/claude/context-database.md` | Làm PostgreSQL queries, Qdrant collections, embedding |
| `docs/claude/context-api.md` | Làm endpoints, schemas, FastAPI Depends, middleware, NestJS integration |
| `docs/claude/context-events.md` | Làm RabbitMQ consumers, publishers, event flows, scraping flows |
| `docs/claude/context-scraping.md` | Làm scraping, Playwright, LLM extraction, HTTP direct call |
| `docs/claude/context-rag.md` | Làm RAG itinerary, semantic search, similar hotels, embedding pipeline, sync |

## NestJS Backend Gọi AI Service

| NestJS gọi | AI endpoint | Khi nào |
|------------|-------------|---------|
| Search proxy | `POST /ai/search` | User semantic search |
| Chat gateway | `POST /ai/chat` (SSE) | User chat qua WebSocket |
| Crawler | `POST /scraping/extract` | Admin scrape URL tạo hotel |
| Sync script | `POST /ai/sync` | Sau seed, rebuild Qdrant |

## Cách dùng

```
"Đọc docs/claude/context-general.md và context-agent.md, sau đó..."
"Đọc docs/claude/context-general.md và context-database.md, fix lỗi này..."
```
