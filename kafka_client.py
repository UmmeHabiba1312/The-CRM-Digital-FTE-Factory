"""
NovaFlow Customer Success FTE — Kafka Client
All inter-service ticket processing flows through Kafka (Principle IV).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

TOPICS = {
    # Unified intake — all channels publish here
    "tickets_incoming":   "fte.tickets.incoming",
    # Channel-specific inbound
    "email_inbound":      "fte.channels.email.inbound",
    "whatsapp_inbound":   "fte.channels.whatsapp.inbound",
    "webform_inbound":    "fte.channels.webform.inbound",
    # Channel-specific outbound
    "email_outbound":     "fte.channels.email.outbound",
    "whatsapp_outbound":  "fte.channels.whatsapp.outbound",
    # Escalations for human agents
    "escalations":        "fte.escalations",
    # Observability
    "metrics":            "fte.metrics",
    # Dead-letter queue — no silent drops (Principle IV)
    "dlq":                "fte.dlq",
}

_producer: FTEKafkaProducer | None = None


async def get_producer() -> "FTEKafkaProducer":
    global _producer
    if _producer is None:
        _producer = FTEKafkaProducer()
        await _producer.start()
    return _producer


class FTEKafkaProducer:
    def __init__(self):
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self._producer.start()
        logger.info("Kafka producer started — %s", KAFKA_BOOTSTRAP)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def publish(self, topic: str, event: dict) -> None:
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        await self._producer.send_and_wait(topic, event)
        logger.debug("Published to %s", topic)

    async def publish_to_dlq(self, original_topic: str, event: dict, error: str) -> None:
        await self.publish(
            TOPICS["dlq"],
            {"original_topic": original_topic, "event": event, "error": error},
        )


class FTEKafkaConsumer:
    def __init__(self, topics: list[str], group_id: str):
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=KAFKA_BOOTSTRAP,
            group_id=group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            enable_auto_commit=True,
            auto_offset_reset="earliest",
        )

    async def start(self) -> None:
        await self._consumer.start()
        logger.info("Kafka consumer started topics=%s", list(self._consumer.subscription()))

    async def stop(self) -> None:
        await self._consumer.stop()

    async def consume(
        self, handler: Callable[[str, dict], Awaitable[None]]
    ) -> None:
        async for msg in self._consumer:
            try:
                await handler(msg.topic, msg.value)
            except Exception as exc:
                logger.error("Handler error topic=%s: %s", msg.topic, exc)
