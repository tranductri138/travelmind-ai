# TravelMind AI Service

Python microservice (FastAPI) — semantic search, RAG itineraries, AI chat agent, web scraping.
Connects to NestJS backend via REST + RabbitMQ.

## Quick Start

```bash
uv sync                                          # install deps
docker compose up -d                              # rabbitmq + qdrant
uv run uvicorn travelmind_ai.main:app --reload    # http://localhost:8000
```

## Stack

- **Python 3.12**, FastAPI, uv (package manager)
- **LLM**: OpenAI (prod) / Ollama (dev) — switch via `LLM_PROVIDER` env
- **Agent**: LangGraph (`langgraph>=0.2`), LangChain (`langchain-openai>=0.3`)
- **Vector DB**: Qdrant (port 6333) — collections: `hotels`, `reviews`, `bookings`, `response_cache`
- **Message Queue**: RabbitMQ (port 5672, mgmt 15672)
- **Database**: PostgreSQL via asyncpg — **READ-ONLY** (owned by NestJS/Prisma)
- **Scraping**: Playwright + BeautifulSoup + LLM extraction

## Project Layout

```
src/travelmind_ai/
├── main.py              # FastAPI app, lifespan (startup/shutdown)
├── config.py            # Pydantic Settings, loaded from .env
├── dependencies.py      # FastAPI Depends: get_llm_client, get_db_session, etc.
├── core/                # Infrastructure clients (database, rabbitmq, qdrant, llm, embedding, cache)
│   └── cache.py         # CAG: BasicCache (LRU) + SemanticCache (Qdrant vector similarity)
├── ai/                  # Semantic search, similar hotels, RAG itinerary
│   ├── router.py        # POST /ai/search, /ai/similar/{id}, /ai/rag/itinerary
│   ├── schemas.py       # Request/response Pydantic models
│   ├── *_service.py     # Business logic (embedding, search, rag)
│   ├── prompts.py       # LLM prompt templates
│   └── consumer.py      # RabbitMQ: hotel.created/updated, review.created → auto embed
├── booking/             # Booking analytics + event processing
│   ├── schemas.py       # BookingEventData, BookingAnalyticsEvent
│   ├── service.py       # Embed/delete bookings in Qdrant
│   └── consumer.py      # RabbitMQ: booking.created/confirmed/cancelled
├── chat/                # LangGraph ReAct agent (AI chat)
│   ├── router.py        # POST /ai/chat (SSE streaming or non-streaming)
│   ├── schemas.py       # ChatMessage, ChatRequest (with conversation_id), ChatResponse
│   ├── prompts.py       # Agent system prompt with tool usage instructions
│   ├── tools.py         # 4 @tool functions: search_hotels, get_hotel_details, check_room_availability, get_popular_hotels
│   ├── graph.py         # LangGraph ReAct agent with MemorySaver checkpointer
│   └── service.py       # Stateful (checkpoint, no CAG) and Stateless (CAG, no checkpoint) modes
├── scraping/            # Web scraping + LLM extraction
│   ├── router.py        # POST /scraping/extract
│   ├── browser.py       # Playwright lifecycle
│   ├── llm_extractor.py # HTML → LLM → structured JSON
│   └── consumer.py      # RabbitMQ: crawler.job → crawler.completed
└── shared/              # Middleware, exceptions, text_utils (chunking, tiktoken)
tests/                   # pytest + pytest-asyncio, mocked external services
```

## Conventions

- All imports use `from __future__ import annotations`
- Absolute imports: `from travelmind_ai.core.llm import LLMClient`
- Type hints everywhere, `str | None` syntax (not Optional)
- Protocol classes for abstractions (e.g. `EmbeddingClient`)
- Global singletons prefixed with `_` (e.g. `_client`, `_connection`)
- Ruff: line-length 100, rules E/F/I/N/UP/B/SIM, B008 ignored (FastAPI Depends pattern)

## Commands

```bash
uv run ruff check src/         # lint
uv run ruff check src/ --fix   # auto-fix
uv run pytest -v               # tests (17 tests, all mocked, no external services)
uv run pytest --cov            # with coverage
```

## DB Models (read-only, maps Prisma schema)

- **Hotel**: hotels table — name, slug, city, country, stars, rating, amenities, images
- **Room**: rooms table — hotel_id, type, price, max_guests, amenities
- **Review**: reviews table — user_id, hotel_id, rating, title, comment

Prisma source: `/home/admin1/Documents/TRAVELMIND/backend/prisma/schema.prisma`

## RabbitMQ Events

Exchange: `travelmind` (topic)

| Consumed (from NestJS)  | Queue                  | Action                         |
|-------------------------|------------------------|--------------------------------|
| `hotel.created`         | ai.hotel.created       | Embed hotel into Qdrant        |
| `hotel.updated`         | ai.hotel.updated       | Re-embed hotel                 |
| `hotel.deleted`         | ai.hotel.deleted       | Delete hotel embeddings        |
| `review.created`        | ai.review.created      | Embed review into Qdrant       |
| `review.deleted`        | ai.review.deleted      | Delete review embedding        |
| `booking.created`       | ai.booking.created     | Embed booking + analytics      |
| `booking.confirmed`     | ai.booking.confirmed   | Re-embed + analytics           |
| `booking.cancelled`     | ai.booking.cancelled   | Delete embedding + analytics   |
| `crawler.job`           | ai.crawler.job         | Scrape URL → publish result    |

Published: `crawler.completed` (with extracted hotel data + reviews), `booking.analytics` (booking events)

## Chat Module (LangGraph Agent)

**Endpoint**: `POST /ai/chat` — supports SSE streaming and non-streaming responses.

**Architecture**: LangGraph ReAct agent (not simple RAG). The agent reasons step-by-step and invokes tools to answer travel queries.

**4 LangChain tools** (`chat/tools.py`):
- `search_hotels` — semantic search via Qdrant embeddings
- `get_hotel_details` — fetch full hotel info from PostgreSQL
- `check_room_availability` — query available rooms for dates
- `get_popular_hotels` — top-rated hotels by city/country

**Two operating modes** (`chat/service.py`):
- **Stateful**: Uses LangGraph `MemorySaver` checkpointer keyed by `conversation_id`. Full conversation history is preserved across requests. No CAG (every request hits the LLM).
- **Stateless**: Uses CAG (Cache-Augmented Generation) to skip the LLM when a cached response is available. No checkpointing (each request is independent).

**CAG (Cache-Augmented Generation)** (`core/cache.py`):
- `BasicCache` — in-memory LRU cache with configurable max size and TTL
- `SemanticCache` — Qdrant-backed vector similarity cache (collection: `response_cache`, threshold: 0.95). Falls back to BasicCache on Qdrant failure.
- Config: `cag_basic_max_size`, `cag_basic_ttl`, `cag_semantic_threshold` (0.95), `cag_semantic_ttl`, `qdrant_collection_cache`

**Initialization**: `dependencies.py` exposes `init_semantic_cache()` and `get_cache_layer()` singletons. `main.py` calls `init_semantic_cache()` after Qdrant connects at startup.

## Key Design Decisions

- Startup is **resilient**: server starts even without RabbitMQ/Qdrant (logs warnings)
- Embedding uses chunking (500 tokens, 50 overlap) for long hotel descriptions
- Search deduplicates chunks by hotel_id, keeping best score
- Scraping pipeline: Playwright render → BS4 strip scripts/nav → LLM extract JSON
- Health endpoint reports connection status of each service
