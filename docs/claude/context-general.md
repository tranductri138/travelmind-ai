# Context: General — TravelMind AI

> Luôn load file này. Chứa stack, layout, conventions, commands.

## Service

Python microservice (FastAPI, port 8000) — semantic search, RAG, AI chat agent, web scraping.
Kết nối NestJS qua REST + RabbitMQ. PostgreSQL là **read-only** (do NestJS/Prisma sở hữu).

## Stack

- Python 3.12, FastAPI, uv
- LLM: OpenAI `gpt-4o-mini` / Ollama `llama3.2` — switch qua `LLM_PROVIDER` env
- Embedding: `text-embedding-3-small` (dim=1536)
- Agent: LangGraph `create_react_agent` + LangChain
- Qdrant (6333): vector DB — collections: `hotels`, `reviews`, `bookings`, `response_cache`
- RabbitMQ (5672): exchange `travelmind` (topic)
- PostgreSQL: asyncpg, read-only

## Layout

```
src/travelmind_ai/
├── main.py          # FastAPI app + lifespan
├── config.py        # Pydantic Settings (.env)
├── dependencies.py  # singletons: llm, embedding, cache, db, qdrant
├── core/cache.py    # CAG: BasicCache + SemanticCache → CacheLayer
├── ai/              # semantic search + RAG (POST /ai/search, /similar, /rag/itinerary)
├── booking/         # booking embed + analytics events
├── chat/            # LangGraph agent (POST /ai/chat)
├── scraping/        # Playwright + LLM extract (POST /scraping/extract)
└── shared/          # middleware, exceptions, text_utils
tests/               # pytest-asyncio, tất cả mock
```

## Conventions

- `from __future__ import annotations` ở đầu mỗi file
- Absolute imports: `from travelmind_ai.core.llm import LLMClient`
- `str | None` không dùng `Optional`
- Protocol classes cho abstraction (e.g. `EmbeddingClient`)
- Global singleton: prefix `_` (e.g. `_llm_client`, `_cache_layer`)
- Ruff: line-length 100, rules E/F/I/N/UP/B/SIM, B008 ignored

## Commands

```bash
uv run ruff check src/ --fix   # lint
uv run pytest -v               # test
uv run pytest --cov            # coverage
uv run uvicorn travelmind_ai.main:app --reload  # dev server
```
