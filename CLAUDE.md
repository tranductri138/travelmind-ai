# TravelMind AI

FastAPI microservice — semantic search, RAG, LangGraph agent, web scraping.
Kết nối NestJS qua REST + RabbitMQ. PostgreSQL là **read-only**.

## Context Files

Load file phù hợp với task đang làm:

| File | Load khi nào |
|------|-------------|
| `docs/claude/context-general.md` | **Luôn load** — stack, layout, conventions, commands |
| `docs/claude/context-agent.md` | Làm chat agent, LangGraph, tools, CAG, streaming |
| `docs/claude/context-database.md` | Làm PostgreSQL queries, Qdrant collections, embedding |
| `docs/claude/context-api.md` | Làm endpoints, schemas, FastAPI Depends, middleware |
| `docs/claude/context-events.md` | Làm RabbitMQ consumers, publishers, event flows |

## Cách dùng

```
"Đọc docs/claude/context-general.md và context-agent.md, sau đó..."
"Đọc docs/claude/context-general.md và context-database.md, fix lỗi này..."
```
