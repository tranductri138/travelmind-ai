from __future__ import annotations

import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import aio_pika

from travelmind_ai.config import settings

logger = logging.getLogger(__name__)

_connection: aio_pika.abc.AbstractRobustConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None


async def connect() -> aio_pika.abc.AbstractChannel:
    global _connection, _channel
    _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    _channel = await _connection.channel()
    await _channel.set_qos(prefetch_count=10)
    logger.info("RabbitMQ connected")
    return _channel


async def disconnect() -> None:
    global _connection, _channel
    if _channel:
        await _channel.close()
        _channel = None
    if _connection:
        await _connection.close()
        _connection = None
    logger.info("RabbitMQ disconnected")


def get_channel() -> aio_pika.abc.AbstractChannel:
    if _channel is None:
        raise RuntimeError("RabbitMQ channel not initialized — call connect() first")
    return _channel


async def publish(exchange_name: str, routing_key: str, body: dict[str, Any]) -> None:
    channel = get_channel()
    exchange = await channel.declare_exchange(
        exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
    )
    message = aio_pika.Message(
        body=json.dumps(body).encode(),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await exchange.publish(message, routing_key=routing_key)


async def consume(
    queue_name: str,
    exchange_name: str,
    routing_key: str,
    callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
) -> None:
    channel = get_channel()
    exchange = await channel.declare_exchange(
        exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue(queue_name, durable=True)
    await queue.bind(exchange, routing_key=routing_key)

    async def _on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
        async with message.process():
            try:
                data = json.loads(message.body.decode())
                await callback(data)
            except Exception:
                logger.exception("Error processing message from %s", queue_name)

    await queue.consume(_on_message)
    logger.info("Consuming queue=%s routing_key=%s", queue_name, routing_key)
