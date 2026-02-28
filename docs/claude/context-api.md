# Context: API — FastAPI Routes & Dependencies

> Load khi làm việc với: routes, schemas, dependency injection, middleware, request/response.

## Tất Cả Endpoints

| Method | Path | Module | Mô tả |
|--------|------|--------|-------|
| GET | `/health` | main.py | Trạng thái RabbitMQ + Qdrant |
| POST | `/ai/search` | ai/router.py | Semantic search hotels |
| POST | `/ai/similar/{hotel_id}` | ai/router.py | Tìm hotels tương tự |
| POST | `/ai/rag/itinerary` | ai/router.py | RAG tạo lịch trình |
| POST | `/ai/chat` | chat/router.py | LangGraph agent chat |
| POST | `/scraping/extract` | scraping/router.py | Web scraping + LLM extract |

## Dependency Injection (`dependencies.py`)

```python
# FastAPI Depends — inject vào route handlers
get_llm_client()       → LLMClient          # singleton
get_embedding_client() → EmbeddingClient    # singleton
get_cache_layer()      → CacheLayer         # singleton (BasicCache + optional SemanticCache)
get_db_session()       → AsyncSession       # per-request
get_qdrant_client()    → AsyncQdrantClient  # per-request
get_rabbitmq_channel() → Channel            # per-request
```

**Dùng trong route:**
```python
@router.post("/search")
async def search(
    request: SearchRequest,
    embedding: EmbeddingClient = Depends(get_embedding_client),
    qdrant: AsyncQdrantClient = Depends(get_qdrant_client),
    db: AsyncSession = Depends(get_db_session),
): ...
```

**Quan trọng**: B008 ignored trong Ruff — `Depends(...)` trong function signature là pattern chuẩn.

## Schema Pattern

```python
# Dùng Pydantic v2
class SearchRequest(BaseModel):
    query: str
    city: str | None = None
    country: str | None = None
    min_stars: int | None = None

class HotelScore(BaseModel):
    hotel_id: str
    name: str
    score: float
    city: str
    stars: int

class SearchResponse(BaseModel):
    results: list[HotelScore]
    total: int
```

## Chat Request/Response

```python
class ChatMessage(BaseModel):
    role: str    # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    conversation_id: str | None = None  # None → stateless + CAG
    stream: bool = False

class ChatResponse(BaseModel):
    content: str
```

## Streaming SSE (chat/router.py)

```python
async def stream_gen():
    async for chunk in agent_chat_stream(messages, conversation_id):
        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
    yield "data: [DONE]\n\n"

return StreamingResponse(stream_gen(), media_type="text/event-stream")
```

## Middleware & Error Handling

- **CorrelationID**: gắn `X-Correlation-ID` header vào mọi request/response (`shared/middleware.py`)
- **Global exception handler**: trả JSON `{"error": "...", "detail": "..."}` chuẩn

## App Setup (`main.py`)

```python
app = FastAPI(lifespan=lifespan)
app.include_router(ai_router, prefix="/ai")
app.include_router(chat_router, prefix="/ai")
app.include_router(scraping_router, prefix="/scraping")
app.add_middleware(CorrelationIDMiddleware)
```
