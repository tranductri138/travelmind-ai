# Context: Database — PostgreSQL & Qdrant

> Load khi làm việc với: models, queries, Qdrant collections, embedding pipeline.

## PostgreSQL (Read-Only)

Schema do NestJS/Prisma tạo. AI service chỉ **đọc**, không ghi.
Prisma source: `/home/admin1/Documents/TRAVELMIND/backend/prisma/schema.prisma`

**Session pattern** (`dependencies.py`):
```python
async def get_db_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

### Models

**Hotel** (`hotels` table):
```
id, name, slug, city, country, stars (int), rating (float),
amenities (list[str]), images (list[str]), description, address, is_active
```

**Room** (`rooms` table):
```
id, hotel_id (FK), type, price (Decimal), max_guests (int),
amenities (list[str]), is_active
```

**Review** (`reviews` table):
```
id, user_id (FK), hotel_id (FK), rating (float), title, comment, created_at
```

**RoomAvailability** (`room_availability` table):
```
id, room_id (FK), date, is_available (bool)
```

### Ví Dụ Query Pattern

```python
# Fetch hotel + rooms
stmt = select(Hotel).where(Hotel.id == hotel_id).options(selectinload(Hotel.rooms))
hotel = await session.scalar(stmt)

# Check availability
stmt = select(RoomAvailability).where(
    RoomAvailability.room_id == room_id,
    RoomAvailability.date.between(check_in, check_out),
    RoomAvailability.is_available == False,
)
```

## Qdrant (Vector DB)

### Collections

| Collection | Nội dung | Vector dim |
|-----------|---------|-----------|
| `hotels` | Hotel text chunks | 1536 |
| `reviews` | Review title + comment | 1536 |
| `bookings` | Booking context | 1536 |
| `response_cache` | Cached LLM responses (CAG) | 1536 |

### Payload Chuẩn — Hotels

```json
{
  "hotel_id": "uuid",
  "chunk_index": 0,
  "text": "chunk text",
  "city": "Hanoi",
  "country": "Vietnam",
  "stars": 4
}
```

### Payload Chuẩn — Response Cache

```json
{
  "query": "normalized query text",
  "response": "cached LLM response",
  "created_at": 1709123456.0,
  "ttl": 3600
}
```

### Embedding Pipeline

```python
# Chunking: 500 tokens, 50 overlap (shared/text_utils.py)
chunks = chunk_text(text, max_tokens=500, overlap=50)

# Embed + upsert
for i, chunk in enumerate(chunks):
    vector = await embedding_client.embed(chunk)
    point = PointStruct(
        id=str(uuid5(hotel_id, str(i))),  # deterministic
        vector=vector,
        payload={"hotel_id": hotel_id, "chunk_index": i, ...}
    )
    await qdrant.upsert(collection_name="hotels", points=[point])
```

### Search Pattern

```python
results = await qdrant.search(
    collection_name="hotels",
    query_vector=query_vector,
    query_filter=Filter(must=[FieldCondition(key="city", match=MatchValue(value=city))]),
    limit=20,
)
# Deduplicate by hotel_id, keep best score
seen = {}
for r in results:
    hid = r.payload["hotel_id"]
    if hid not in seen or r.score > seen[hid].score:
        seen[hid] = r
top5 = sorted(seen.values(), key=lambda x: x.score, reverse=True)[:5]
```
