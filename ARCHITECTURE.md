# TravelMind AI - Giải Thich Chi Tiet Kien Truc & Code

> File nay giai thich tung module, tung file, code lam gi, hoat dong nhu the nao,
> du lieu chay tu dau den dau trong he thong.

---

## Muc Luc

1. [Tong Quan He Thong](#1-tong-quan-he-thong)
2. [Luong Du Lieu Toan Bo](#2-luong-du-lieu-toan-bo)
3. [Khoi Dong Ung Dung (main.py)](#3-khoi-dong-ung-dung-mainpy)
4. [Cau Hinh (config.py)](#4-cau-hinh-configpy)
5. [Dependency Injection (dependencies.py)](#5-dependency-injection-dependenciespy)
6. [Core - Tang Ha Tang](#6-core---tang-ha-tang)
7. [Module AI - Tim Kiem Ngu Nghia & RAG](#7-module-ai---tim-kiem-ngu-nghia--rag)
8. [Module Scraping - Thu Thap Du Lieu Web](#8-module-scraping---thu-thap-du-lieu-web)
9. [Module Booking - Phan Tich Dat Phong](#9-module-booking---phan-tich-dat-phong)
10. [Shared - Tien Ich Dung Chung](#10-shared---tien-ich-dung-chung)
11. [RabbitMQ - He Thong Event Chi Tiet](#11-rabbitmq---he-thong-event-chi-tiet)
12. [Qdrant - Vector Database Chi Tiet](#12-qdrant---vector-database-chi-tiet)
13. [Tests](#13-tests)

---

## 1. Tong Quan He Thong

TravelMind AI la **Python microservice** chay doc lap, phuc vu cac tinh nang AI cho ung dung
du lich TravelMind. No **KHONG** quan ly du lieu chinh (hotel, user, booking) — viec do la cua
NestJS backend. Service nay chi:

- **Doc** du lieu tu PostgreSQL (read-only, bang do NestJS/Prisma tao)
- **Lang nghe** event tu NestJS qua RabbitMQ de biet khi nao co hotel/review/booking moi
- **Tao embedding** (vector so) tu text va luu vao Qdrant (vector database)
- **Tim kiem ngu nghia** — user go "beach resort with pool" → tim hotel phu hop nhat
- **Tao lich trinh** bang RAG (lay hotel lien quan tu Qdrant roi dua cho LLM viet lich trinh)
- **Crawl website** — vao trang web khach san, lay HTML, dung LLM trich xuat du lieu co cau truc

```
                    ┌─────────────────────────────────────────┐
                    │              NestJS Backend              │
                    │  (quan ly hotel, user, booking, review)  │
                    └──────┬──────────────┬───────────────┬────┘
                           │              │               │
                    REST API       RabbitMQ Events    PostgreSQL
                    (goi truc tiep) (bat dong bo)     (cung database)
                           │              │               │
                    ┌──────▼──────────────▼───────────────▼────┐
                    │          TravelMind AI Service            │
                    │  ┌──────────┐ ┌──────────┐ ┌──────────┐  │
                    │  │ AI       │ │ Scraping │ │ Booking  │  │
                    │  │ Module   │ │ Module   │ │ Module   │  │
                    │  └────┬─────┘ └────┬─────┘ └────┬─────┘  │
                    │       │            │            │         │
                    │  ┌────▼────────────▼────────────▼─────┐  │
                    │  │              Core Layer             │  │
                    │  │  LLM · Embedding · Qdrant · RMQ    │  │
                    │  └────────────────────────────────────┘  │
                    └──────────────────────────────────────────┘
                                      │
                        ┌─────────────┼─────────────┐
                        ▼             ▼             ▼
                    OpenAI/Ollama   Qdrant      RabbitMQ
                    (LLM + embed)  (vectors)   (message queue)
```

---

## 2. Luong Du Lieu Toan Bo

### 2.1. Khi Admin tao hotel moi tren NestJS:

```
1. NestJS luu hotel vao PostgreSQL
2. NestJS publish event "hotel.created" len RabbitMQ (exchange "travelmind")
3. AI service dang lang nghe queue "ai.hotel.created"
4. Consumer nhan duoc data hotel (id, name, city, description, ...)
5. Goi embed_hotel():
   a. build_hotel_text() → tao 1 doan text mo ta hotel
   b. chunk_text() → cat thanh nhieu doan nho (neu text qua dai)
   c. embedding_client.embed() → gui text len OpenAI/Ollama, nhan lai vector [0.12, -0.34, ...]
   d. qdrant_client.upsert() → luu vector vao Qdrant collection "hotels"
6. Hotel da duoc index, co the tim kiem ngu nghia
```

### 2.2. Khi User tim kiem "luxury beach hotel in Bali":

```
1. Frontend gui POST /ai/search { query: "luxury beach hotel in Bali" }
2. API nhan request, embed cau query thanh vector
3. Gui vector do vao Qdrant, tim cac hotel co vector gan nhat (cosine similarity)
4. Loai bo trung lap (1 hotel co the co nhieu chunk), giu diem cao nhat
5. Tra ve danh sach hotel_id + score
6. Frontend dung hotel_id goi NestJS de lay thong tin chi tiet
```

### 2.3. Khi User yeu cau tao lich trinh (RAG):

```
1. Frontend gui POST /ai/rag/itinerary { destination: "Paris", days: 3, interests: ["food"] }
2. Service embed "Hotels in Paris for food" thanh vector
3. Tim 10 hotel phu hop nhat tu Qdrant
4. Ghep thong tin hotel vao prompt: "Day la cac hotel o Paris: ... Hay tao lich trinh 3 ngay"
5. Gui prompt cho LLM (OpenAI/Ollama)
6. LLM tra ve lich trinh markdown chi tiet
7. Tra ve cho frontend
```

### 2.4. Khi NestJS gui link can crawl:

```
1. NestJS publish event "crawler.job" { url: "https://booking.com/hotel/abc" }
2. AI service nhan event qua queue "ai.crawler.job"
3. Mo trinh duyet Playwright (headless Chrome), vao trang web
4. Doi trang load xong (JS render), lay HTML
5. Dung BeautifulSoup loc bo script/style/nav → chi con text sach
6. Gui text cho LLM voi prompt "Hay trich xuat thong tin hotel tu text nay"
7. LLM tra ve JSON: { name, city, stars, amenities, ... }
8. Publish ket qua len RabbitMQ event "crawler.completed"
9. NestJS nhan ket qua va luu vao database
```

---

## 3. Khoi Dong Ung Dung (main.py)

File: `src/travelmind_ai/main.py`

Day la file entry point, tao FastAPI app va quan ly **lifecycle** (khoi dong/tat).

### Lifespan (startup/shutdown):

```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
```

**Khi server khoi dong:**
1. `init_clients()` — tao LLMClient + EmbeddingClient (singleton, chi tao 1 lan)
2. Ket noi RabbitMQ — neu that bai thi **KHONG crash**, chi log warning va bo qua
3. Ket noi Qdrant — tuong tu, khong crash neu khong ket noi duoc
4. Neu CA HAI RabbitMQ va Qdrant deu ok → bat cac consumer lang nghe event:
   - `start_ai_consumers()` — hotel.created/updated/deleted, review.created/deleted
   - `start_scraping_consumers()` — crawler.job
   - `start_booking_consumers()` — booking.created/confirmed/cancelled

**Tai sao thiet ke "resilient" (khong crash)?**
Trong moi truong dev, ban co the chi muon test API ma khong can RabbitMQ/Qdrant.
Server van chay, chi la cac tinh nang lien quan se bi disable.

**Khi server tat:**
1. Dong LLM + Embedding client
2. Dong ket noi RabbitMQ
3. Dong ket noi Qdrant

### FastAPI App:

```python
app = FastAPI(
    title="TravelMind AI",
    description=DESCRIPTION,
    ...
    openapi_tags=[...],  # Nhom API theo tag: AI, Scraping, Booking, System
)
```

- Dang ky middleware `CorrelationIDMiddleware` (theo doi request across services)
- Dang ky exception handlers
- Mount 2 router: `/ai/*` va `/scraping/*`
- Health check endpoint: `GET /health` → bao trang thai ket noi cac service

---

## 4. Cau Hinh (config.py)

File: `src/travelmind_ai/config.py`

Dung **Pydantic Settings** de doc bien moi truong tu file `.env` hoac system env.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", ...)

    llm_provider: Literal["openai", "ollama"] = "openai"  # chon LLM provider
    openai_api_key: str = ""          # API key cua OpenAI
    openai_model: str = "gpt-4o-mini" # model LLM cho chat
    openai_embedding_model: str = "text-embedding-3-small"  # model tao embedding

    database_url: str = "postgresql+asyncpg://..."  # PostgreSQL (chi doc)
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    qdrant_url: str = "http://localhost:6333"

    qdrant_collection_hotels: str = "hotels"    # ten collection trong Qdrant
    qdrant_collection_reviews: str = "reviews"
    qdrant_collection_bookings: str = "bookings"

    embedding_dimension: int = 1536  # kich thuoc vector (1536 cho OpenAI)
```

**Cach chuyen tu OpenAI sang Ollama (dev local, mien phi):**
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

**Singleton:** `settings = Settings()` — chi tao 1 lan, import o bat ky dau.

---

## 5. Dependency Injection (dependencies.py)

File: `src/travelmind_ai/dependencies.py`

Quan ly cac **singleton client** — chi tao 1 instance cho toan bo app.

```python
_llm_client: LLMClient | None = None
_embedding_client: EmbeddingClient | None = None
```

- `init_clients()` — goi luc startup, tao LLMClient + EmbeddingClient
- `shutdown_clients()` — goi luc shutdown, dong ket noi
- `get_llm_client()` → tra ve LLMClient singleton
- `get_embedding_client()` → tra ve EmbeddingClient singleton
- `get_qdrant_client()` → tra ve Qdrant client singleton
- `get_db_session()` → tao database session (dung cho FastAPI `Depends`)

**Tai sao dung singleton?**
Cac client nay giu ket noi TCP den OpenAI/Qdrant/RabbitMQ. Tao moi cho moi request
se rat ton tai nguyen. Singleton = 1 ket noi, tai su dung cho tat ca request.

---

## 6. Core - Tang Ha Tang

### 6.1. database.py — Ket noi PostgreSQL

File: `src/travelmind_ai/core/database.py`

**CHI DOC (read-only).** Database do NestJS + Prisma quan ly (tao bang, migration).
AI service chi doc du lieu de phuc vu tim kiem.

```python
engine = create_async_engine(settings.database_url, echo=...)
async_session_factory = async_sessionmaker(engine, ...)
```

**3 model ORM map voi bang Prisma:**

- **Hotel** (bang `hotels`): name, slug, city, country, stars, rating, amenities, images, ...
  - Quan he: 1 hotel → nhieu Room, nhieu Review
- **Room** (bang `rooms`): hotel_id, type, price, max_guests, amenities, ...
  - Quan he: nhieu room → 1 hotel
- **Review** (bang `reviews`): user_id, hotel_id, rating, title, comment
  - Quan he: nhieu review → 1 hotel
  - Rang buoc: 1 user chi review 1 hotel 1 lan (UniqueConstraint)

### 6.2. llm.py — Giao Tiep Voi LLM

File: `src/travelmind_ai/core/llm.py`

**LLMClient** — lop thong nhat de goi chat voi OpenAI hoac Ollama.

```python
class LLMClient:
    def __init__(self):
        if settings.llm_provider == "openai":
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        else:
            # Ollama ho tro OpenAI-compatible API tai /v1
            self._client = AsyncOpenAI(api_key="ollama", base_url=".../v1")
```

**Meo:** Ollama ho tro API tuong thich OpenAI, nen chi can doi `base_url` la xong,
khong can viet code rieng.

```python
async def chat(self, messages, temperature=0.7, max_tokens=2048, response_format=None) -> str:
```
- `messages`: list dict {"role": "system"/"user", "content": "..."}
- `temperature`: do "sang tao" — 0.1 = chinh xac, 0.8 = sang tao
- `response_format`: bat buoc tra JSON (dung cho data extraction)

**OllamaEmbeddingClient** — dung khi chay Ollama, goi truc tiep API `/api/embed`
(vi Ollama embedding API khong tuong thich OpenAI).

```python
async def embed(self, texts: list[str]) -> list[list[float]]:
    # Gui tung text mot len Ollama, nhan vector ve
    resp = await self._http.post(f"{base_url}/api/embed", json={...})
    return data["embeddings"][0]
```

### 6.3. embedding.py — Tao Vector Embedding

File: `src/travelmind_ai/core/embedding.py`

**EmbeddingClient Protocol** — dinh nghia interface, bat ky client nao cung phai co:
- `embed(texts) → list[list[float]]` — nhan list cau text, tra ve list vector
- `close()` — dong ket noi

**OpenAIEmbeddingClient:**
```python
async def embed(self, texts):
    response = await self._client.embeddings.create(model=self._model, input=texts)
    return [item.embedding for item in response.data]
```
OpenAI ho tro batch — gui nhieu text 1 lan, nhan nhieu vector 1 lan. Nhanh hon Ollama.

**Factory:**
```python
def create_embedding_client() -> EmbeddingClient:
    if settings.llm_provider == "openai":
        return OpenAIEmbeddingClient()
    return OllamaEmbeddingClient()
```

### 6.4. qdrant.py — Vector Database

File: `src/travelmind_ai/core/qdrant.py`

Qdrant la database chuyen luu **vector** va tim kiem theo **do tuong dong** (cosine similarity).

```python
_client: AsyncQdrantClient | None = None  # singleton

async def connect():
    _client = AsyncQdrantClient(url=settings.qdrant_url)
    await _ensure_collections()  # tu dong tao collection neu chua co
```

**Tu dong tao 3 collection:**
```python
async def _ensure_collections():
    for name in ["hotels", "reviews", "bookings"]:
        if not await _client.collection_exists(name):
            await _client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )
```

Moi collection luu cac "diem" (point), moi diem gom:
- `id` — dinh danh duy nhat
- `vector` — mang so [0.12, -0.34, 0.56, ...] (1536 chieu)
- `payload` — metadata dinh kem (hotel_id, city, text, ...)

### 6.5. rabbitmq.py — Hang Doi Tin Nhan

File: `src/travelmind_ai/core/rabbitmq.py`

RabbitMQ la **message broker** — NestJS gui tin nhan, AI service nhan va xu ly.

**Ket noi:**
```python
_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
_channel = await _connection.channel()
await _channel.set_qos(prefetch_count=10)  # xu ly toi da 10 message cung luc
```

**Publish (gui tin nhan):**
```python
async def publish(exchange_name, routing_key, body):
    exchange = await channel.declare_exchange(exchange_name, TOPIC, durable=True)
    message = aio_pika.Message(body=json.dumps(body).encode(), ...)
    await exchange.publish(message, routing_key=routing_key)
```
- `exchange_name`: "travelmind" — ten exchange dung chung
- `routing_key`: vd "crawler.completed" — dinh tuyen tin nhan
- `body`: dict Python → chuyen thanh JSON → gui di
- `durable=True`: tin nhan khong mat khi RabbitMQ restart

**Consume (lang nghe tin nhan):**
```python
async def consume(queue_name, exchange_name, routing_key, callback):
    exchange = await channel.declare_exchange(exchange_name, TOPIC, durable=True)
    queue = await channel.declare_queue(queue_name, durable=True)
    await queue.bind(exchange, routing_key=routing_key)  # gan queue voi routing key
    await queue.consume(_on_message)  # bat dau lang nghe
```

**Luong xu ly tin nhan:**
```
1. NestJS publish message voi routing_key "hotel.created" len exchange "travelmind"
2. Exchange "travelmind" la kieu TOPIC → match routing_key voi cac queue da bind
3. Queue "ai.hotel.created" da bind voi routing_key "hotel.created" → nhan duoc message
4. Ham _on_message() duoc goi:
   a. Giai ma JSON tu message body
   b. Goi callback (vd: _on_hotel_event)
   c. Neu thanh cong → ACK (xoa message khoi queue)
   d. Neu loi → log error, van ACK (tranh re-delivery loop)
```

---

## 7. Module AI - Tim Kiem Ngu Nghia & RAG

### 7.1. schemas.py — Cac Model Du Lieu

File: `src/travelmind_ai/ai/schemas.py`

**SearchRequest:**
```python
class SearchRequest(BaseModel):
    query: str          # "luxury beach resort with spa"
    city: str | None    # loc theo thanh pho (tuy chon)
    country: str | None # loc theo quoc gia (tuy chon)
    min_stars: int | None  # so sao toi thieu (tuy chon)
    limit: int = 10     # so ket qua toi da
```

**HotelScore:** ket qua tim kiem — `hotel_id` + `score` (0-1, cang cao cang phu hop)

**RAGItineraryRequest:**
```python
class RAGItineraryRequest(BaseModel):
    destination: str       # "Paris"
    days: int             # 3
    interests: list[str]  # ["food", "museums"]
    budget: str | None    # "mid-range"
```

### 7.2. router.py — API Endpoints

File: `src/travelmind_ai/ai/router.py`

**3 endpoint:**

| Method | Path | Chuc nang |
|--------|------|-----------|
| POST | `/ai/search` | Tim kiem hotel bang ngon ngu tu nhien |
| POST | `/ai/similar/{hotel_id}` | Tim hotel tuong tu |
| POST | `/ai/rag/itinerary` | Tao lich trinh du lich (RAG) |

Moi endpoint dung FastAPI `Depends` de inject client:
```python
async def search_hotels(
    request: SearchRequest,
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant_client),
) -> SearchResponse:
    return await semantic_search(request, embedding_client, qdrant_client)
```

### 7.3. search_service.py — Logic Tim Kiem

File: `src/travelmind_ai/ai/search_service.py`

**semantic_search():**
```
1. Embed cau query thanh vector
   "luxury beach resort" → [0.12, -0.34, 0.56, ...]

2. Xay dung filter (tuy chon):
   - city = "Bali" → chi tim hotel o Bali
   - min_stars = 4 → chi hotel 4-5 sao

3. Tim trong Qdrant:
   qdrant.search(collection="hotels", query_vector=..., limit=20)
   → tra ve 20 diem gan nhat (cosine similarity)

4. Loai bo trung lap:
   1 hotel co the co nhieu chunk (vi description dai).
   Vd: hotel-123 co 3 chunk, diem lan luot 0.85, 0.72, 0.68
   → chi giu 0.85 (diem cao nhat)

5. Sap xep theo diem giam dan, tra ve top N
```

**Tai sao fetch `limit * 2`?**
Vi 1 hotel co nhieu chunk, neu chi lay dung `limit` diem thi sau khi loai trung co the
con it hon so luong mong muon. Lay gap doi de dam bao du.

**find_similar():**
```
1. Dung hotel_id lam query → Qdrant tim cac vector gan nhat
2. Loai bo chinh hotel do (khong muon "tuong tu chinh no")
3. Loai trung lap, tra ve top N
```

### 7.4. embedding_service.py — Tao & Xoa Embedding

File: `src/travelmind_ai/ai/embedding_service.py`

**embed_hotel():**
```python
async def embed_hotel(hotel_data, embedding_client, qdrant_client):
    # 1. Tao text mo ta hotel
    text = build_hotel_text(name, city, country, description, amenities, stars, rating)
    # Ket qua vd: "Grand Palace Hotel — 5-star hotel in Paris, France\nRating: 4.8/5\n..."

    # 2. Cat thanh nhieu doan (chunking)
    chunks = chunk_text(text, max_tokens=500)
    # Neu text ngan → 1 chunk. Neu text dai → nhieu chunk (overlap 50 token)

    # 3. Embed tat ca chunk cung luc
    vectors = await embedding_client.embed(chunks)  # [[0.1, ...], [0.2, ...], ...]

    # 4. Tao cac diem de luu vao Qdrant
    points = [
        PointStruct(
            id="hotel-123" (chunk 0) hoac "hotel-123_1" (chunk 1), ...
            vector=vector,
            payload={"hotel_id": "hotel-123", "chunk_index": 0, "text": chunk, "city": "Paris", ...}
        )
    ]

    # 5. Luu vao Qdrant
    await qdrant_client.upsert(collection_name="hotels", points=points)
```

**Tai sao phai chunk?**
- Embedding model co gioi han so luong token xu ly (vd: 8191 token cho OpenAI)
- Van ban ngan → embedding chinh xac hon
- 500 token/chunk, overlap 50 → dam bao khong mat y nghia o cho cat

**embed_review():**
- Don gian hon: noi title + comment, embed 1 vector duy nhat (review ngan)
- Neu review khong co title va comment → bo qua (khong embed)

**delete_hotel_embeddings():**
```python
await qdrant_client.delete(
    collection_name="hotels",
    points_selector=Filter(
        must=[FieldCondition(key="hotel_id", match=MatchValue(value=hotel_id))]
    ),
)
```
Xoa **TAT CA** chunk cua hotel do (khong chi 1 diem, ma tat ca diem co `hotel_id` khop).

**delete_review_embedding():**
Tuong tu — xoa diem co `review_id` khop.

### 7.5. rag_service.py — Pipeline RAG

File: `src/travelmind_ai/ai/rag_service.py`

RAG = **Retrieval-Augmented Generation** — lay du lieu lien quan roi dua cho LLM sinh noi dung.

```python
async def generate_itinerary(request, llm_client, embedding_client, qdrant_client):
    # Buoc 1: RETRIEVAL — Tim hotel phu hop
    search_text = f"Hotels in {request.destination} for {interests}"
    vectors = await embedding_client.embed([search_text])
    hits = await qdrant_client.search(collection="hotels", query_vector=vectors[0], limit=10)

    # Buoc 2: AUGMENTATION — Ghep thong tin hotel vao prompt
    hotel_context = "\n".join(f"- {hotel_text} (relevance: {score})" ...)
    user_prompt = RAG_ITINERARY_USER.format(
        days=3, destination="Paris",
        hotel_context=hotel_context,  # ← day la phan "augmented"
    )

    # Buoc 3: GENERATION — LLM tao lich trinh
    itinerary = await llm_client.chat(
        messages=[
            {"role": "system", "content": "You are TravelMind, expert travel planner..."},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,   # sang tao hon cho viec viet lich trinh
        max_tokens=4096,   # lich trinh dai → can nhieu token
    )
```

**Tai sao RAG tot hon chi hoi LLM?**
- LLM khong biet cac hotel trong database cua ban
- RAG dua thong tin hotel THAT vao prompt → LLM goi y hotel CU THE tu he thong

### 7.6. prompts.py — Mau Prompt LLM

File: `src/travelmind_ai/ai/prompts.py`

```python
RAG_ITINERARY_SYSTEM = """
You are TravelMind, an expert travel planner. Create detailed day-by-day itineraries...
"""

RAG_ITINERARY_USER = """
Plan a {days}-day trip to {destination}.
{interests_section}
{budget_section}

Here are some recommended hotels in the area:
{hotel_context}               ← hotel lay tu Qdrant duoc chen vao day

Create a detailed day-by-day itinerary...
"""
```

### 7.7. consumer.py — Lang Nghe Event RabbitMQ

File: `src/travelmind_ai/ai/consumer.py`

**5 consumer, xu ly 5 loai event:**

```python
async def _on_hotel_event(data):
    """hotel.created hoac hotel.updated → tao/cap nhat embedding."""
    await embed_hotel(data, get_embedding_client(), get_qdrant())

async def _on_review_created(data):
    """review.created → tao embedding cho review."""
    await embed_review(data, get_embedding_client(), get_qdrant())

async def _on_hotel_deleted(data):
    """hotel.deleted → xoa embedding khoi Qdrant."""
    hotel_id = data.get("id")
    if not hotel_id:
        return  # bo qua neu thieu id
    await delete_hotel_embeddings(hotel_id, get_qdrant())

async def _on_review_deleted(data):
    """review.deleted → xoa embedding khoi Qdrant."""
    review_id = data.get("id")
    if not review_id:
        return
    await delete_review_embedding(review_id, get_qdrant())
```

**Dang ky consumer:**
```python
async def start_ai_consumers():
    await rabbitmq.consume(queue="ai.hotel.created",  routing_key="hotel.created",  callback=_on_hotel_event)
    await rabbitmq.consume(queue="ai.hotel.updated",  routing_key="hotel.updated",  callback=_on_hotel_event)
    await rabbitmq.consume(queue="ai.review.created", routing_key="review.created", callback=_on_review_created)
    await rabbitmq.consume(queue="ai.hotel.deleted",  routing_key="hotel.deleted",  callback=_on_hotel_deleted)
    await rabbitmq.consume(queue="ai.review.deleted", routing_key="review.deleted", callback=_on_review_deleted)
```

**Giai thich moi dong:**
- `queue_name="ai.hotel.created"` → ten queue rieng cua AI service (prefix `ai.` de phan biet)
- `exchange_name="travelmind"` → exchange chung cho toan he thong
- `routing_key="hotel.created"` → chi nhan message co routing key nay
- `callback=_on_hotel_event` → ham xu ly khi nhan duoc message

---

## 8. Module Scraping - Thu Thap Du Lieu Web

### 8.1. browser.py — Quan Ly Trinh Duyet

File: `src/travelmind_ai/scraping/browser.py`

Dung **Playwright** (headless Chromium) de render trang web nhu trinh duyet that.

```python
async def get_browser():
    """Khoi tao trinh duyet (lazy — chi tao khi can)."""
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(headless=True)  # khong hien giao dien
```

```python
async def fetch_page_html(url, wait_ms=3000):
    """Mo trang web, doi load xong, tra ve HTML."""
    browser = await get_browser()
    page = await browser.new_page()
    await page.goto(url, wait_until="networkidle", timeout=30000)
    # doi 3s cho JS render them (SPA, lazy load, ...)
    await page.wait_for_timeout(wait_ms)
    return await page.content()  # tra ve HTML day du
```

**Tai sao can Playwright ma khong dung requests?**
Nhieu trang khach san (Booking.com, Agoda, ...) dung JavaScript de render noi dung.
`requests` chi lay HTML goc (chua co du lieu). Playwright chay trinh duyet that,
doi JS chay xong moi lay HTML.

### 8.2. scraping_service.py — Pipeline Scraping

File: `src/travelmind_ai/scraping/scraping_service.py`

```python
def clean_html(html):
    """Loc HTML → chi giu text sach."""
    soup = BeautifulSoup(html, "html.parser")

    # Xoa cac tag khong can thiet
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()

    # Lay text, xoa dong trong thua
    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)
```

```python
async def scrape_hotel(request, llm_client):
    """Pipeline day du: fetch → clean → extract."""
    html = await fetch_page_html(url)     # 1. Mo trang web
    cleaned = clean_html(html)             # 2. Loc HTML → text
    hotel = await extract_hotel_data(cleaned, llm_client)  # 3. LLM trich xuat
    reviews = []
    if request.extract_reviews:
        reviews = await extract_reviews(cleaned, llm_client)  # 4. (tuy chon) trich xuat review
    return ScrapeResponse(url=url, hotel=hotel, reviews=reviews, raw_text_length=len(cleaned))
```

### 8.3. llm_extractor.py — LLM Trich Xuat Du Lieu

File: `src/travelmind_ai/scraping/llm_extractor.py`

Dua text sach cho LLM va yeu cau tra ve JSON co cau truc.

```python
EXTRACT_HOTEL_PROMPT = """
Given the following cleaned text from a hotel webpage, extract:
{
  "name": "string or null",
  "city": "string or null",
  "stars": "integer 0-5 or null",
  "amenities": ["list of strings"],
  ...
}

Webpage text:
{text}
"""
```

```python
async def extract_hotel_data(text, llm_client):
    prompt = EXTRACT_HOTEL_PROMPT.format(text=text[:8000])  # cat 8000 ky tu dau
    result = await llm_client.chat(messages=[...], temperature=0.1)  # chinh xac, khong sang tao
    data = json.loads(result)
    return ExtractedHotelData.model_validate(data)  # validate bang Pydantic
```

**temperature=0.1** — rat thap vi muon LLM trich xuat CHINH XAC, khong "sang tao".

**Tai sao cat 8000 ky tu?** Token limit cua LLM. 8000 ky tu ~ 2000 token,
du cho noi dung chinh cua trang ma khong vuot gioi han.

### 8.4. consumer.py — Lang Nghe Event Crawler

File: `src/travelmind_ai/scraping/consumer.py`

```python
async def _on_scraping_job(data):
    """NestJS gui URL can crawl → AI service crawl va tra ket qua."""
    url = data.get("url")
    if not url:
        return  # bo qua neu thieu URL

    request = ScrapeRequest(url=url, extract_reviews=data.get("extract_reviews", False))
    result = await scrape_hotel(request, get_llm_client())

    # Gui ket qua ve cho NestJS
    await rabbitmq.publish(
        exchange_name="travelmind",
        routing_key="crawler.completed",
        body={
            "url": result.url,
            "hotel": result.hotel.model_dump(),
            "reviews": [r.model_dump() for r in result.reviews],
            "job_id": data.get("job_id"),  # de NestJS biet job nao da xong
        },
    )
```

**Luong:**
```
NestJS                    RabbitMQ                  AI Service
  │                         │                         │
  │─── crawler.job ────────>│                         │
  │    {url, job_id}        │──── ai.crawler.job ────>│
  │                         │                         │── Playwright fetch
  │                         │                         │── BeautifulSoup clean
  │                         │                         │── LLM extract JSON
  │                         │<── crawler.completed ───│
  │<── crawler.completed ───│    {hotel, reviews}     │
  │    luu vao DB           │                         │
```

---

## 9. Module Booking - Phan Tich Dat Phong

### 9.1. schemas.py — Du Lieu Booking

File: `src/travelmind_ai/booking/schemas.py`

```python
class BookingEventData(BaseModel):
    id: str               # "booking-001"
    user_id: str          # "user-789"
    room_id: str          # "room-101"
    check_in: str         # "2026-03-15"
    check_out: str        # "2026-03-20"
    guests: int           # 2
    total_price: float    # 750.00
    currency: str = "USD"
    status: str = "PENDING"  # PENDING → CONFIRMED → CANCELLED
    special_requests: str | None  # "Late check-in"
    hotel_name: str | None   # "Grand Palace Hotel"
    hotel_city: str | None   # "Paris"
    hotel_country: str | None # "France"
```

### 9.2. service.py — Xu Ly Booking

File: `src/travelmind_ai/booking/service.py`

```python
def build_booking_text(hotel_name, hotel_city, ..., status):
    """Tao text mo ta booking de embed."""
    # Ket qua vd: "Hotel: Grand Palace Hotel | Location: Paris, France |
    #              Check-in: 2026-03-15, Check-out: 2026-03-20 |
    #              Guests: 2 | Price: 750.0 USD | Status: CONFIRMED"
```

**embed_booking():** — giong embed_hotel() nhung DON GIAN hon (khong chunk, vi text ngan)
```python
async def embed_booking(booking_data, embedding_client, qdrant_client):
    text = build_booking_text(...)
    vectors = await embedding_client.embed([text])  # 1 vector duy nhat
    point = PointStruct(id=booking_data["id"], vector=vectors[0], payload={...})
    await qdrant_client.upsert(collection_name="bookings", points=[point])
```

**delete_booking_embedding():** — xoa booking khoi Qdrant bang filter tren `booking_id`.

### 9.3. consumer.py — Lang Nghe Event Booking

File: `src/travelmind_ai/booking/consumer.py`

**3 handler:**

```python
async def _on_booking_created(data):
    """Dat phong moi → embed vao Qdrant + gui analytics."""
    await embed_booking(data, get_embedding_client(), get_qdrant())
    await _publish_analytics(data, action="created")

async def _on_booking_confirmed(data):
    """Xac nhan dat phong → cap nhat embedding (status=CONFIRMED) + analytics."""
    data["status"] = "CONFIRMED"
    await embed_booking(data, get_embedding_client(), get_qdrant())  # upsert = ghi de
    await _publish_analytics(data, action="confirmed")

async def _on_booking_cancelled(data):
    """Huy dat phong → xoa embedding + gui analytics."""
    await delete_booking_embedding(booking_id, get_qdrant())
    data["status"] = "CANCELLED"
    await _publish_analytics(data, action="cancelled")
```

**_publish_analytics():** — gui event `booking.analytics` len RabbitMQ de cac service khac
(vd: analytics service, notification service) co the xu ly tiep.

```python
async def _publish_analytics(data, action):
    await rabbitmq.publish(
        exchange_name="travelmind",
        routing_key="booking.analytics",
        body={
            "booking_id": data["id"],
            "action": action,  # "created" / "confirmed" / "cancelled"
            "user_id": data["user_id"],
            ...
        },
    )
```

---

## 10. Shared - Tien Ich Dung Chung

### 10.1. exceptions.py — Xu Ly Loi

File: `src/travelmind_ai/shared/exceptions.py`

```python
class AppError(Exception):       # Loi chung — 500
class LLMError(AppError):        # Loi goi LLM — 502
class ScrapingError(AppError):   # Loi crawl web — 502
class EmbeddingError(AppError):  # Loi tao embedding — 502
```

502 Bad Gateway — vi loi xay ra o **service ben ngoai** (OpenAI, Ollama, website), khong phai
loi cua API nay.

### 10.2. middleware.py — Theo Doi Request

File: `src/travelmind_ai/shared/middleware.py`

```python
class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
```

**Muc dich:** Khi NestJS goi AI service, no gui kem `X-Correlation-ID`.
AI service giu nguyen ID do va tra lai trong response. Nhu vay trong log cua CA HAI service,
ban co the tim tat ca log lien quan den 1 request bang cung 1 ID.

### 10.3. text_utils.py — Xu Ly Van Ban

File: `src/travelmind_ai/shared/text_utils.py`

**count_tokens():** Dem so token cua text (dung tiktoken, giong nhu OpenAI dem).
```python
def count_tokens(text):
    return len(tiktoken.encoding_for_model("gpt-4o-mini").encode(text))
    # "Hello world" → 2 tokens, "Khach san sang trong" → ~5 tokens
```

**chunk_text():** Cat van ban dai thanh nhieu doan nho co overlap.
```python
def chunk_text(text, max_tokens=500, overlap=50):
    tokens = encoder.encode(text)
    if len(tokens) <= 500:
        return [text]  # khong can cat

    # Cat thanh cac doan 500 token, moi doan overlap 50 token voi doan truoc
    # Overlap de giu ngu canh — doan 1 ket thuc "...beautiful beach",
    # doan 2 bat dau "beautiful beach and..." → khong mat y
```

**Vi du chunking:**
```
Text goc: [=====500 tokens=====][=====500 tokens=====][===300 tokens===]
Chunk 1:  [=====500 tokens=====]
Chunk 2:              [50 overlap][=====500 tokens=====]
Chunk 3:                                    [50 overlap][===300 tokens===]
```

**build_hotel_text():** Tao text mo ta hotel cho embedding.
```python
def build_hotel_text(name, city, country, description, amenities, stars, rating):
    # "Grand Palace Hotel — 5-star hotel in Paris, France
    #  Rating: 4.8/5
    #  A luxury hotel in the heart of Paris with stunning views
    #  Amenities: Pool, Spa, Restaurant, WiFi"
```

---

## 11. RabbitMQ - He Thong Event Chi Tiet

### Khai niem co ban:

- **Exchange** = "buu dien" — nhan tin nhan va chuyen di dung noi
- **Queue** = "hop thu" — noi tin nhan nam doi xu ly
- **Routing Key** = "dia chi" — xac dinh tin nhan di dau
- **Binding** = "dang ky" — noi queue voi exchange + routing key

### Kieu TOPIC exchange:

Exchange `travelmind` la kieu **TOPIC** — routing key dung dau `.` de phan cap.
Queue bind voi pattern, vd:
- `hotel.created` → chi khop chinh xac
- `hotel.*` → khop hotel.created, hotel.updated, hotel.deleted
- `#` → khop tat ca

### Bang tong hop tat ca event:

```
CONSUMED (AI service lang nghe):
┌────────────────────┬───────────────────────┬─────────────────────────────┐
│ Routing Key        │ Queue                 │ Xu ly                       │
├────────────────────┼───────────────────────┼─────────────────────────────┤
│ hotel.created      │ ai.hotel.created      │ Tao embedding hotel         │
│ hotel.updated      │ ai.hotel.updated      │ Cap nhat embedding hotel    │
│ hotel.deleted      │ ai.hotel.deleted      │ Xoa embedding hotel         │
│ review.created     │ ai.review.created     │ Tao embedding review        │
│ review.deleted     │ ai.review.deleted     │ Xoa embedding review        │
│ booking.created    │ ai.booking.created    │ Embed booking + analytics   │
│ booking.confirmed  │ ai.booking.confirmed  │ Re-embed + analytics        │
│ booking.cancelled  │ ai.booking.cancelled  │ Xoa embedding + analytics   │
│ crawler.job        │ ai.crawler.job        │ Crawl URL va trich xuat     │
└────────────────────┴───────────────────────┴─────────────────────────────┘

PUBLISHED (AI service gui di):
┌────────────────────┬─────────────────────────────────────────────┐
│ Routing Key        │ Noi dung                                    │
├────────────────────┼─────────────────────────────────────────────┤
│ crawler.completed  │ Ket qua crawl: hotel data + reviews JSON    │
│ booking.analytics  │ Thong tin analytics: action + booking data   │
└────────────────────┴─────────────────────────────────────────────┘
```

### Luong event day du:

```
NestJS Backend                   RabbitMQ                    AI Service
     │                              │                            │
     │  Admin tao hotel             │                            │
     │──── hotel.created ──────────>│                            │
     │     {id, name, city, ...}    │─── ai.hotel.created ─────>│
     │                              │                            │── build_hotel_text()
     │                              │                            │── chunk_text()
     │                              │                            │── embed()  → OpenAI
     │                              │                            │── upsert() → Qdrant
     │                              │                            │
     │  Admin xoa hotel             │                            │
     │──── hotel.deleted ──────────>│                            │
     │     {id: "hotel-123"}        │─── ai.hotel.deleted ─────>│
     │                              │                            │── delete() → Qdrant
     │                              │                            │
     │  User dat phong              │                            │
     │──── booking.created ────────>│                            │
     │     {id, user_id, ...}       │─── ai.booking.created ───>│
     │                              │                            │── embed_booking() → Qdrant
     │                              │<── booking.analytics ──────│
     │                              │    {action: "created"}     │
     │                              │                            │
     │  Admin gui link crawl        │                            │
     │──── crawler.job ────────────>│                            │
     │     {url, job_id}            │─── ai.crawler.job ────────>│
     │                              │                            │── Playwright fetch
     │                              │                            │── BeautifulSoup clean
     │                              │                            │── LLM extract JSON
     │                              │<── crawler.completed ──────│
     │<── crawler.completed ────────│    {hotel, reviews}        │
     │    luu vao PostgreSQL        │                            │
```

---

## 12. Qdrant - Vector Database Chi Tiet

### Vector Embedding la gi?

**Embedding** = chuyen text thanh mang so (vector) sao cho text co nghia TUONG TU
thi vector THAN nhau.

```
"luxury beach resort"  → [0.82, -0.15, 0.43, 0.67, ...]  (1536 so)
"premium seaside hotel" → [0.80, -0.12, 0.45, 0.65, ...]  ← gan giong!
"cheap bus ticket"      → [-0.3, 0.71, -0.22, 0.11, ...]  ← rat khac
```

**Cosine Similarity** = do do tuong dong giua 2 vector (0 = khac hoan toan, 1 = giong het).

### 3 Collection trong Qdrant:

**hotels** — moi hotel co 1+ diem (chunked)
```json
{
  "id": "hotel-123",
  "vector": [0.12, -0.34, ...],
  "payload": {
    "hotel_id": "hotel-123",
    "chunk_index": 0,
    "text": "Grand Palace Hotel — 5-star hotel in Paris...",
    "city": "Paris",
    "country": "France",
    "stars": 5
  }
}
```

**reviews** — moi review co 1 diem
```json
{
  "id": "review-456",
  "vector": [0.45, 0.12, ...],
  "payload": {
    "review_id": "review-456",
    "hotel_id": "hotel-123",
    "rating": 5,
    "text": "Amazing stay — Beautiful hotel with excellent service"
  }
}
```

**bookings** — moi booking co 1 diem
```json
{
  "id": "booking-001",
  "vector": [0.33, -0.56, ...],
  "payload": {
    "booking_id": "booking-001",
    "user_id": "user-789",
    "room_id": "room-101",
    "hotel_name": "Grand Palace Hotel",
    "hotel_city": "Paris",
    "status": "CONFIRMED",
    "text": "Hotel: Grand Palace Hotel | Location: Paris, France | ..."
  }
}
```

### Tim kiem trong Qdrant:

```python
# User nhap: "romantic hotel near beach"
# → embed thanh vector [0.55, -0.28, ...]
# → Qdrant tim cac diem trong collection "hotels" co vector gan nhat
# → Tra ve: hotel-456 (score: 0.92), hotel-789 (score: 0.87), ...
```

---

## 13. Tests

Toan bo test **KHONG** ket noi service that — dung **mock** (gia lap).

### conftest.py — Fixtures dung chung

```python
@pytest.fixture
def mock_qdrant_client():
    client = AsyncMock()
    client.upsert.return_value = None   # gia lap thanh cong
    client.delete.return_value = None
    client.search.return_value = []
    return client

@pytest.fixture
def sample_hotel_data():
    return {"id": "hotel-123", "name": "Grand Palace Hotel", "city": "Paris", ...}
```

### Cac test file:

| File | Test gi |
|------|---------|
| `test_config.py` | Settings load dung default values |
| `test_text_utils.py` | Dem token, chunk text, build hotel text |
| `test_embedding_service.py` | Embed hotel/review goi dung collection |
| `test_delete_embeddings.py` | Xoa hotel/review embedding dung collection |
| `test_search_service.py` | Tim kiem loai trung, xu ly ket qua rong, filter |
| `test_scraping_service.py` | Loc HTML bo script/style/nav |
| `test_booking_service.py` | Embed/xoa booking, build booking text |

### Chay test:

```bash
uv run pytest -v          # chay tat ca test, hien chi tiet
uv run pytest --cov       # chay test + bao cao do phu (coverage)
```
