# Context: AI Agent — LangGraph ReAct + CAG

> Load khi làm việc với: chat/, core/cache.py, LangGraph agent, tools, streaming.

## Endpoint

```
POST /ai/chat
{ messages: [{role, content}], conversation_id?: string, stream?: bool }
```
- `stream=true` → SSE `text/event-stream`, yield `{"chunk": "..."}`, kết thúc `[DONE]`
- `stream=false` → JSON `{"content": "..."}`

## Agent Setup (`chat/graph.py`)

```python
agent = create_react_agent(
    model=ChatOpenAI(temperature=0.7, max_tokens=2048, streaming=True),
    tools=ALL_TOOLS,           # từ chat/tools.py
    prompt=_build_prompt,      # callable: SystemMessage + trim last N messages
    checkpointer=AsyncPostgresSaver(pool),  # PostgreSQL, keyed by thread_id
)
# singleton — get_agent() / reset_agent()
# _build_prompt(state) trim messages → chỉ gửi 20 gần nhất cho LLM (CHECKPOINT_MESSAGES_LIMIT)
```

## 4 Tools (`chat/tools.py`)

| Tool | Params | Source | Ghi chú |
|------|--------|--------|---------|
| `search_hotels` | query, city?, min_stars? | Qdrant → PostgreSQL | deduplicate by hotel_id |
| `get_hotel_details` | hotel_id | PostgreSQL | hotel + rooms + 5 reviews |
| `check_room_availability` | hotel_id, check_in, check_out, guests? | RoomAvailability table | tính total cost |
| `get_popular_hotels` | city?, limit?=5 | PostgreSQL | sort by rating + review_count |

## Hai Chế Độ (`chat/service.py`)

**Stateful** — khi có `conversation_id`:
- config: `{"configurable": {"thread_id": conversation_id}}`
- AsyncPostgresSaver lưu toàn bộ messages + tool results vào PostgreSQL qua requests
- Mỗi request đều gọi LLM (không cache)

**Stateless** — không có `conversation_id`:
- Không dùng checkpoint — mỗi request độc lập
- Pipeline: `CacheLayer.get(query)` → hit? return ngay : `agent.ainvoke()` → `CacheLayer.set()`

## CAG (`core/cache.py`)

```
CacheLayer
├── BasicCache   — in-memory LRU, max 1000, TTL 3600s, key = normalize(query)
└── SemanticCache — Qdrant collection "response_cache", cosine threshold=0.95, TTL 3600s
```

**get(query)**: Basic → Semantic (embed + search) → miss
- Semantic hit → promote lên Basic để lần sau exact match
- Semantic dùng UUID5(normalize(query)) làm point_id — deterministic

**set(query, response)**: ghi cả 2 tầng cùng lúc

## Luồng Service (Stateless Streaming)

```python
async def _stream_stateless(messages, cache):
    query = _get_last_user_message(messages)
    response, status = await cache.get(query)
    if status != "miss":
        yield response  # no LLM call
        return
    full = ""
    async for chunk in agent.astream_events(...):
        yield chunk; full += chunk
    await cache.set(query, full)
```

## Khởi Tạo Cache

```python
# dependencies.py
init_clients()          # tạo BasicCache → _cache_layer (tầng 1)
init_semantic_cache()   # gọi sau Qdrant connect → thêm SemanticCache vào _cache_layer
get_cache_layer()       # FastAPI Depends → CacheLayer singleton
```

## Tích Hợp Với NestJS Backend

NestJS Chat Module (WebSocket gateway, namespace `/chat`) gọi AI qua HTTP SSE:

```
Browser (Socket.io) → NestJS Chat Gateway (JWT auth)
  → POST http://ai:8000/ai/chat (SSE)
    body: { messages: [{role:"user", content}], conversation_id, stream: true }
  ← SSE chunks: data: {"chunk": "..."}\n\n ... data: [DONE]\n\n
  → NestJS parse chunks → emit('messageChunk') về browser
  → Save full response vào PostgreSQL (ChatMessage, role=ASSISTANT)
```

**Quan trọng:**
- NestJS chỉ gửi **1 message mới nhất**, KHÔNG gửi history
- AI dùng `conversation_id` làm `thread_id` cho AsyncPostgresSaver → tự khôi phục lịch sử
- NestJS quản lý ChatConversation + ChatMessage trong PostgreSQL (CRUD, ownership check)
- AI chỉ xử lý AI logic (agent, tools, streaming) — không touch database
