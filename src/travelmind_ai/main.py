from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from travelmind_ai.config import settings
from travelmind_ai.core import qdrant, rabbitmq
from travelmind_ai.dependencies import init_clients, init_semantic_cache, shutdown_clients
from travelmind_ai.shared.exceptions import register_exception_handlers
from travelmind_ai.shared.middleware import CorrelationIDMiddleware

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)

_rabbitmq_ok = False
_qdrant_ok = False


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    global _rabbitmq_ok, _qdrant_ok

    # Startup
    logger.info("Starting TravelMind AI service (env=%s)", settings.app_env)
    init_clients()

    # RabbitMQ — optional in dev
    try:
        await rabbitmq.connect()
        _rabbitmq_ok = True
    except Exception:
        logger.warning("RabbitMQ unavailable — consumers disabled. Start RabbitMQ to enable.")

    # LangGraph checkpoint (PostgreSQL)
    from travelmind_ai.chat.graph import setup_checkpointer, shutdown_checkpointer

    try:
        await setup_checkpointer()
    except Exception:
        logger.warning("Checkpoint DB unavailable — chat history will not persist across restarts.")

    # Qdrant — optional in dev
    try:
        await qdrant.connect()
        _qdrant_ok = True
        # Initialise semantic cache now that Qdrant is available
        init_semantic_cache()
    except Exception:
        logger.warning("Qdrant unavailable — vector search disabled. Start Qdrant to enable.")

    # Start RabbitMQ consumers only if both services are up
    if _rabbitmq_ok and _qdrant_ok:
        from travelmind_ai.ai.consumer import start_ai_consumers
        from travelmind_ai.booking.consumer import start_booking_consumers
        from travelmind_ai.scraping.consumer import start_scraping_consumers

        await start_ai_consumers()
        await start_scraping_consumers()
        await start_booking_consumers()

    yield

    # Shutdown
    logger.info("Shutting down TravelMind AI service")
    await shutdown_checkpointer()
    await shutdown_clients()
    if _rabbitmq_ok:
        await rabbitmq.disconnect()
    if _qdrant_ok:
        await qdrant.disconnect()


DESCRIPTION = """\
## TravelMind AI Service

Python microservice powering the AI features of TravelMind:

- **Semantic Search** — natural-language hotel search via vector embeddings (Qdrant)
- **Similar Hotels** — find hotels similar to a given one by vector distance
- **RAG Itinerary** — Retrieval-Augmented Generation: retrieve relevant hotels, \
then ask the LLM to build a day-by-day travel plan
- **Web Scraping** — headless browser (Playwright) + LLM extraction of structured \
hotel data from any URL
- **AI Chat** — conversational travel assistant with RAG-powered hotel recommendations
- **Booking Analytics** — embed and track booking events \
(created, confirmed, cancelled) for analytics

### Architecture
`NestJS backend` → REST / RabbitMQ → `this service` →
OpenAI / Ollama + Qdrant + PostgreSQL (read-only)
"""

app = FastAPI(
    title="TravelMind AI",
    description=DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "AI",
            "description": "Semantic search, similar hotels, RAG itinerary generation",
        },
        {
            "name": "Scraping",
            "description": "Headless browser scraping + LLM data extraction",
        },
        {
            "name": "Chat",
            "description": "AI chat assistant with RAG-powered hotel recommendations",
        },
        {
            "name": "Booking",
            "description": "Booking analytics and event processing",
        },
        {
            "name": "System",
            "description": "Health checks and service status",
        },
    ],
)

app.add_middleware(CorrelationIDMiddleware)
register_exception_handlers(app)

# Routers
from travelmind_ai.ai.router import router as ai_router  # noqa: E402
from travelmind_ai.chat.router import router as chat_router  # noqa: E402
from travelmind_ai.scraping.router import router as scraping_router  # noqa: E402

app.include_router(ai_router)
app.include_router(chat_router)
app.include_router(scraping_router)


@app.get("/health", tags=["System"], summary="Health check")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "rabbitmq": "connected" if _rabbitmq_ok else "disconnected",
        "qdrant": "connected" if _qdrant_ok else "disconnected",
    }
