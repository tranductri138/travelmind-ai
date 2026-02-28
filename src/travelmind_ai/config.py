from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = 8000
    log_level: str = "info"

    # LLM provider
    llm_provider: Literal["openai", "ollama"] = "openai"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_embedding_model: str = "nomic-embed-text"

    # Database (read-only, shared with NestJS backend)
    database_url: str = "postgresql+asyncpg://travelmind:secret@localhost:5432/travelmind"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_hotels: str = "hotels"
    qdrant_collection_reviews: str = "reviews"
    qdrant_collection_bookings: str = "bookings"
    qdrant_collection_cache: str = "response_cache"

    # Embedding
    embedding_dimension: int = 1536

    # CAG (Cache-Augmented Generation)
    cag_basic_max_size: int = 1000
    cag_basic_ttl: int = 3600  # 1 hour
    cag_semantic_threshold: float = 0.95
    cag_semantic_ttl: int = 3600  # 1 hour

    # Scraping limits (demo mode)
    scraping_max_requests_per_day: int = 2  # Limit to 2 scrapes per day for demo
    scraping_enabled: bool = True  # Toggle scraping on/off


settings = Settings()
