# TravelMind AI Service

Python microservice (FastAPI) — semantic search, RAG itineraries, web scraping.
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
- **Vector DB**: Qdrant (port 6333) — collections: `hotels`, `reviews`
- **Message Queue**: RabbitMQ (port 5672, mgmt 15672)
- **Database**: PostgreSQL via asyncpg — **READ-ONLY** (owned by NestJS/Prisma)
- **Scraping**: Playwright + BeautifulSoup + LLM extraction

## Project Layout

```
src/travelmind_ai/
├── main.py              # FastAPI app, lifespan (startup/shutdown)
├── config.py            # Pydantic Settings, loaded from .env
├── dependencies.py      # FastAPI Depends: get_llm_client, get_db_session, etc.
├── core/                # Infrastructure clients (database, rabbitmq, qdrant, llm, embedding)
├── ai/                  # Semantic search, similar hotels, RAG itinerary
│   ├── router.py        # POST /ai/search, /ai/similar/{id}, /ai/rag/itinerary
│   ├── schemas.py       # Request/response Pydantic models
│   ├── *_service.py     # Business logic (embedding, search, rag)
│   ├── prompts.py       # LLM prompt templates
│   └── consumer.py      # RabbitMQ: hotel.created/updated, review.created → auto embed
├── scraping/            # Web scraping + LLM extraction
│   ├── router.py        # POST /scraping/extract
│   ├── browser.py       # Playwright lifecycle
│   ├── llm_extractor.py # HTML → LLM → structured JSON
│   └── consumer.py      # RabbitMQ: scraping.job → scraping.completed
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

| Consumed (from NestJS)  | Queue                | Action                    |
|-------------------------|----------------------|---------------------------|
| `hotel.created`         | ai.hotel.created     | Embed hotel into Qdrant   |
| `hotel.updated`         | ai.hotel.updated     | Re-embed hotel            |
| `review.created`        | ai.review.created    | Embed review into Qdrant  |
| `scraping.job`          | ai.scraping.job      | Scrape URL → publish result |

Published: `scraping.completed` (with extracted hotel data + reviews)

## Key Design Decisions

- Startup is **resilient**: server starts even without RabbitMQ/Qdrant (logs warnings)
- Embedding uses chunking (500 tokens, 50 overlap) for long hotel descriptions
- Search deduplicates chunks by hotel_id, keeping best score
- Scraping pipeline: Playwright render → BS4 strip scripts/nav → LLM extract JSON
- Health endpoint reports connection status of each service
