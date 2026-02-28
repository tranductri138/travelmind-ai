# Context: RAG & Semantic Search — Module `ai/`

> Load khi làm việc với: ai/router.py, rag_service.py, search_service.py, embedding_service.py, ai/prompts.py.

## Endpoints (`ai/router.py`)

| Method | Path | Dependencies | Handler |
|--------|------|-------------|---------|
| POST | `/ai/search` | EmbeddingClient, AsyncQdrantClient | `semantic_search()` |
| POST | `/ai/similar/{hotel_id}` | AsyncQdrantClient | `find_similar()` |
| POST | `/ai/rag/itinerary` | LLMClient, EmbeddingClient, AsyncQdrantClient | `generate_itinerary()` |

---

## Schemas (`ai/schemas.py`)

```python
class SearchRequest(BaseModel):
    query: str                      # min 1, max 500 chars
    city: str | None = None
    country: str | None = None
    min_stars: int | None = None    # 0–5
    limit: int = 10                 # 1–50

class HotelScore(BaseModel):
    hotel_id: str
    score: float                    # cosine similarity 0–1

class SearchResponse(BaseModel):
    results: list[HotelScore]
    query: str

class SimilarRequest(BaseModel):
    limit: int = 5                  # 1–20

class RAGItineraryRequest(BaseModel):
    destination: str                # tên thành phố / vùng
    days: int                       # 1–30
    interests: list[str] = []       # ["museums", "food", "architecture"]
    budget: str | None = None       # "budget" | "mid-range" | "luxury"

class RAGItineraryResponse(BaseModel):
    destination: str
    days: int
    itinerary: str                  # markdown day-by-day plan
    hotel_suggestions: list[HotelScore]  # top 5, sorted by score
```

---

## RAG Itinerary Pipeline (`rag_service.py`)

```
RAGItineraryRequest
  ↓
1. Build search text:
   "Hotels in {destination}"
   + " for {interests}" nếu có interests

2. embedding_client.embed([search_text])  → vector 1536d

3. qdrant.search(collection="hotels", limit=10)
   → Deduplicate by hotel_id (keep best score + text)

4. Build hotel_context:
   "- {text} (relevance: {score:.2f})"
   (mỗi hotel 1 dòng, nối bằng "\n\n")

5. llm_client.chat(
       messages=[system, user],
       temperature=0.8,
       max_tokens=4096,
   ) → itinerary markdown

6. RAGItineraryResponse(
       hotel_suggestions=sorted(seen, by score)[:5]
   )
```

### Prompts (`ai/prompts.py`)

```python
RAG_ITINERARY_SYSTEM = """
You are TravelMind, an expert travel planner. Create detailed day-by-day itineraries
that are practical, fun, and well-organized. Include specific activities, meal
suggestions, and travel tips. Use markdown formatting.
"""

RAG_ITINERARY_USER = """
Plan a {days}-day trip to {destination}.

{interests_section}   # "Interests: museums, food" hoặc rỗng
{budget_section}      # "Budget level: mid-range" hoặc rỗng

Here are some recommended hotels in the area:
{hotel_context}       # danh sách từ Qdrant, hoặc "No hotel data available..."

Create a detailed day-by-day itinerary. For each day include:
- Morning, afternoon, and evening activities
- Restaurant/food suggestions
- Practical tips

At the end, recommend which hotel(s) from the list above would be the best fit and why.
"""
```

**Lưu ý**: Nếu Qdrant không trả về hotel nào → `hotel_context = "No hotel data available for this destination yet."` — LLM vẫn tạo lịch trình nhưng không recommend hotel cụ thể.

---

## Semantic Search (`search_service.py`)

```python
async def semantic_search(request, embedding_client, qdrant_client) -> SearchResponse:
    vectors = await embedding_client.embed([request.query])

    # Build Qdrant filters
    conditions = []
    if request.city:     conditions.append(FieldCondition(key="city", match=MatchValue(...)))
    if request.country:  conditions.append(FieldCondition(key="country", match=MatchValue(...)))
    if request.min_stars: conditions.append(FieldCondition(key="stars", range=Range(gte=...)))

    hits = await qdrant_client.search(
        collection_name="hotels",
        query_vector=vectors[0],
        query_filter=Filter(must=conditions) if conditions else None,
        limit=request.limit * 2,   # fetch double để sau dedup còn đủ kết quả
    )

    # Deduplicate chunks → keep best score per hotel_id
    seen: dict[str, float] = {}
    for hit in hits:
        hid = hit.payload["hotel_id"]
        if hid not in seen or hit.score > seen[hid]:
            seen[hid] = hit.score

    return SearchResponse(
        results=sorted(...)[:request.limit],
        query=request.query,
    )
```

---

## Find Similar (`search_service.py`)

```python
async def find_similar(hotel_id, limit, qdrant_client) -> list[HotelScore]:
    results = await qdrant_client.query_points(
        collection_name="hotels",
        query=hotel_id,       # dùng hotel_id làm query vector (lookup existing point)
        limit=limit + 5,      # fetch thêm để bù sau khi bỏ self
    )

    # Bỏ chính hotel_id ra, deduplicate chunks, giữ best score
    seen = {}
    for point in results.points:
        pid = point.payload["hotel_id"]
        if pid == hotel_id: continue    # bỏ chính nó
        if pid not in seen or point.score > seen[pid]:
            seen[pid] = point.score

    return sorted(...)[:limit]
```

---

## Embedding Pipeline (`embedding_service.py`)

### embed_hotel

```python
async def embed_hotel(hotel_data: dict, embedding_client, qdrant_client) -> None:
    # 1. Build text từ các trường
    text = build_hotel_text(name, city, country, description, amenities, stars, rating)

    # 2. Chunk: max 500 tokens (không có overlap — khác với CLAUDE.md mô tả cũ)
    chunks = chunk_text(text, max_tokens=500)

    # 3. Batch embed tất cả chunks
    vectors = await embedding_client.embed(chunks)

    # 4. Build PointStruct cho mỗi chunk
    # point_id: chunk 0 → hotel_id, chunk i>0 → "{hotel_id}_{i}"
    points = [
        PointStruct(
            id=f"{hotel_data['id']}_{i}" if i > 0 else hotel_data["id"],
            vector=vector,
            payload={
                "hotel_id": hotel_data["id"],
                "chunk_index": i,
                "text": chunk,
                "city": ..., "country": ..., "stars": ...,
            },
        )
        for i, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]

    await qdrant_client.upsert(collection_name="hotels", points=points)
```

### embed_review

```python
# text = "{title} — {comment}"  (bỏ qua nếu cả hai rỗng)
# 1 point duy nhất, id = review_id
payload = { "review_id", "hotel_id", "rating", "text" }
```

### delete_hotel_embeddings

```python
# Xóa theo payload field "hotel_id" — xóa tất cả chunks
await qdrant_client.delete(
    collection_name="hotels",
    points_selector=Filter(must=[FieldCondition(key="hotel_id", match=MatchValue(value=hotel_id))])
)
```

### delete_review_embedding

```python
# Xóa theo payload field "review_id"
await qdrant_client.delete(collection_name="reviews", points_selector=Filter(...))
```

---

## Point ID Strategy

| Collection | Chunk 0 | Chunk i (i > 0) |
|-----------|---------|----------------|
| `hotels` | `hotel_id` (UUID) | `"{hotel_id}_{i}"` (string) |
| `reviews` | `review_id` (UUID) | — (luôn 1 chunk) |
| `bookings` | `booking_id` | — |
| `response_cache` | `UUID5(normalize(query))` | — |

**Quan trọng**: Khi update hotel (hotel.updated), phải `delete_hotel_embeddings` trước rồi mới `embed_hotel` lại — vì số chunks có thể thay đổi, upsert không đủ để xóa chunks cũ thừa.

---

## Search Augmentation Prompt (chưa dùng trong search_service)

```python
SEARCH_AUGMENTATION_PROMPT = """
You are a travel search assistant. Given a user query, rephrase it into a detailed
description of the ideal hotel... Keep it under 200 words.
User query: {query}
"""
```

Prompt này có trong `ai/prompts.py` nhưng chưa được gọi trong `search_service.py`. Dùng để augment query trước khi embed nếu cần trong tương lai.
