from __future__ import annotations

import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from travelmind_ai.config import settings
from travelmind_ai.core import qdrant, rabbitmq
from travelmind_ai.dependencies import init_clients, init_semantic_cache, shutdown_clients
from travelmind_ai.shared.exceptions import register_exception_handlers
from travelmind_ai.shared.middleware import CorrelationIDMiddleware


# --- Loguru setup ---
class _InterceptHandler(logging.Handler):
    """Route stdlib logging (uvicorn, sqlalchemy, etc.) through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _setup_logging() -> None:
    log_level = settings.log_level.upper()

    # Custom level colors — avoid white, use vivid colors for readability
    logger.level("TRACE", color="<dim><cyan>")
    logger.level("DEBUG", color="<blue>")
    logger.level("INFO", color="<bold><green>")
    logger.level("SUCCESS", color="<bold><magenta>")
    logger.level("WARNING", color="<bold><yellow>")
    logger.level("ERROR", color="<bold><red>")
    logger.level("CRITICAL", color="<bold><white><RED>")

    # Remove default loguru handler, add custom one
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # Intercept stdlib logging → loguru
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.handlers = [_InterceptHandler()]
        lg.propagate = False

    # Suppress verbose SQLAlchemy SQL echo (keep only WARNING+)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


_setup_logging()

_rabbitmq_ok = False
_qdrant_ok = False


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    global _rabbitmq_ok, _qdrant_ok

    # Startup
    logger.info(f"Starting TravelMind AI service (env={settings.app_env})")
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
