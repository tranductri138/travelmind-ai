# Context: AI Agent — LangGraph StateGraph + Intent Routing + CAG

> Load khi làm việc với: chat/, core/cache.py, LangGraph agent, tools, streaming.

## Endpoint

```
POST /ai/chat
{ messages: [{role, content}], conversation_id?: string, stream?: bool }
```
- `stream=true` → SSE `text/event-stream`, yield `{"chunk": "..."}`, kết thúc `[DONE]`
- `stream=false` → JSON `{"content": "..."}`

## StateGraph Architecture (`chat/graph.py`)

Custom StateGraph với intent-based routing — phân loại intent trước, route trực tiếp tới tool phù hợp cho search/popular, giữ ReAct fallback cho complex queries.

```
START → classify_and_route (rule-based, LLM fallback)
  ├─ "search"       → handle_search       → respond → END
  ├─ "popular"      → handle_popular       → respond → END
  ├─ "details"      ──┐
  ├─ "availability" ──┼─→ handle_general (inner ReAct agent) → END
  └─ "general"      ──┘
```

**Tại sao không dùng `create_react_agent` cho tất cả?**
- `search` và `popular` dễ extract params bằng regex → gọi tool trực tiếp, skip tool schemas → tiết kiệm tokens
- `details` và `availability` cần extract hotel_id/dates phức tạp → ReAct xử lý tốt hơn
- `general` (chitchat, trip planning, multi-tool) → ReAct xử lý

### Agent State

```python
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    intent: str         # classified intent
    tool_result: str    # direct tool output (for search/popular)
```

### Agent Setup

```python
# chat/graph.py
graph = StateGraph(AgentState)
graph.add_node("classify_and_route", partial(classify_and_route, llm=llm))
graph.add_node("handle_search", handle_search)
graph.add_node("handle_popular", handle_popular)
graph.add_node("handle_general", partial(handle_general, llm=llm, prompt_fn=_build_prompt))
graph.add_node("respond", partial(respond, llm=llm))

agent = graph.compile(checkpointer=AsyncPostgresSaver(pool))
# singleton — get_agent() / reset_agent()
# _build_prompt(state) trim messages → chỉ gửi 20 gần nhất cho LLM (CHECKPOINT_MESSAGES_LIMIT)
```

## Intent Classification (`chat/intent.py`)

Rule-based first (~80% of queries), LLM fallback for uncertain cases.

| Intent | Trigger | Handler |
|--------|---------|---------|
| `search` | "tìm khách sạn", "resort", "homestay", "chỗ ở" | `handle_search` → direct tool call |
| `popular` | "top", "tốt nhất", "nổi tiếng", "best" | `handle_popular` → direct tool call |
| `details` | "chi tiết", "thông tin", UUID pattern | `handle_general` → ReAct |
| `availability` | "phòng trống", "check-in", dates | `handle_general` → ReAct |
| `general` | Everything else / uncertain | `handle_general` → ReAct |

```python
classify_intent_rules(message) -> str | None  # None = uncertain → LLM fallback
```

## Graph Nodes (`chat/nodes.py`)

| Node | Nhiệm vụ |
|------|-----------|
| `classify_and_route` | Rule-based → LLM fallback → set `intent` |
| `handle_search` | Extract query/city/stars → `search_hotels.ainvoke()` → set `tool_result` |
| `handle_popular` | Extract city → `get_popular_hotels.ainvoke()` → set `tool_result` |
| `handle_general` | Create inner ReAct agent (no checkpointer) → invoke with messages |
| `respond` | LLM formats `tool_result` → natural language (Vietnamese, markdown) |

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

### Streaming Node Filter

Service chỉ stream chunks từ `respond` và `handle_general` nodes.
`classify_and_route` LLM output (intent classification) không leak tới user.

```python
_STREAMABLE_NODES = {"respond", "handle_general"}
# Filter by: event["metadata"]["langgraph_node"] in _STREAMABLE_NODES
```

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
