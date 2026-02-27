from travelmind_ai.config import Settings


def test_default_settings():
    s = Settings(
        _env_file=None,
        openai_api_key="test-key",
    )
    assert s.app_env == "development"
    assert s.llm_provider == "openai"
    assert s.embedding_dimension == 1536
    assert s.qdrant_collection_hotels == "hotels"


def test_ollama_settings():
    s = Settings(
        _env_file=None,
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434",
    )
    assert s.llm_provider == "ollama"
    assert s.ollama_model == "llama3.2"
