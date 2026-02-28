# Context: Events — RabbitMQ Consumers & Publishers

> Load khi làm việc với: consumers, RabbitMQ, event-driven flows, embedding pipeline.

## Setup

- Exchange: `travelmind`, type: `topic`
- Connection: `get_rabbitmq_channel()` từ `dependencies.py`
- Consumers chỉ start nếu **cả** RabbitMQ + Qdrant đều kết nối được (kiểm tra trong `main.py` lifespan)

## Consumed Events (từ NestJS)

| Routing Key | Queue | Consumer file | Hành động |
|-------------|-------|--------------|-----------|
| `hotel.created` | ai.hotel.created | ai/consumer.py | chunk → embed → upsert Qdrant `hotels` |
| `hotel.updated` | ai.hotel.updated | ai/consumer.py | delete cũ → re-embed |
| `hotel.deleted` | ai.hotel.deleted | ai/consumer.py | delete từ Qdrant `hotels` |
| `review.created` | ai.review.created | ai/consumer.py | embed → upsert Qdrant `reviews` |
| `review.deleted` | ai.review.deleted | ai/consumer.py | delete từ Qdrant `reviews` |
| `booking.created` | ai.booking.created | booking/consumer.py | embed → `bookings` + analytics |
| `booking.confirmed` | ai.booking.confirmed | booking/consumer.py | re-embed + analytics |
| `booking.cancelled` | ai.booking.cancelled | booking/consumer.py | delete + analytics |
| `crawler.job` | ai.crawler.job | scraping/consumer.py | scrape URL → publish result |

## Published Events (bởi AI service)

| Routing Key | Published từ | Payload chính |
|-------------|-------------|--------------|
| `crawler.completed` | scraping/consumer.py | `{url, hotels: [...], reviews: [...]}` |
| `booking.analytics` | booking/consumer.py | `{booking_id, action, user_id, room_id, check_in, check_out, guests, total_price, hotel_id, hotel_name, status}` |

## Consumer Pattern

```python
# Đăng ký consumer trong start_*_consumers()
async def start_booking_consumers(channel: Channel):
    await channel.set_qos(prefetch_count=1)

    # Declare queue + bind to exchange
    queue = await channel.declare_queue("ai.booking.created", durable=True)
    await queue.bind("travelmind", routing_key="booking.created")

    async def on_message(message: IncomingMessage):
        async with message.process():
            data = BookingEventData(**json.loads(message.body))
            await _on_booking_created(data)

    await queue.consume(on_message)
```

## Analytics Payload (`booking/consumer.py`)

```python
async def _publish_analytics(data: BookingEventData, action: str, channel: Channel):
    payload = {
        "booking_id": data.id,
        "action": action,           # "created" | "confirmed" | "cancelled"
        "user_id": data.user_id,
        "room_id": data.room_id,
        "check_in": data.check_in,
        "check_out": data.check_out,
        "guests": data.guests,
        "total_price": data.total_price,
        "hotel_id": data.hotel_id,
        "hotel_name": data.hotel_name,
        "status": data.status,
    }
    await channel.default_exchange.publish(
        Message(json.dumps(payload).encode()),
        routing_key="booking.analytics",
    )
```

## Booking Consumer Flow

```
booking.created  → embed_booking(data)  → upsert Qdrant "bookings"
               → _publish_analytics(action="created")

booking.confirmed → update status="CONFIRMED"
                 → re-embed (delete cũ + upsert mới)
                 → _publish_analytics(action="confirmed")

booking.cancelled → delete_booking_embedding(data.id)
                 → _publish_analytics(action="cancelled")
```

## Scraping Consumer Flow

```
crawler.job → {url, options}
  → Playwright.render(url)           # full JS render
  → BeautifulSoup.clean(html)        # strip scripts/nav
  → LLM.extract(clean_html)          # → {hotels, reviews}
  → publish crawler.completed
```
