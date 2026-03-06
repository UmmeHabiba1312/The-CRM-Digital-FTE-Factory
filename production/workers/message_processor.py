"""
NovaFlow Customer Success FTE — Unified Message Processor
Kafka consumer that routes all channels through the production agent.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from agents import Runner

from database.queries import (
    get_or_create_customer,
    get_or_create_conversation,
    store_message,
    load_conversation_history,
)
from kafka_client import FTEKafkaConsumer, FTEKafkaProducer, TOPICS
from production.agent.customer_success_agent import customer_success_agent
from production.channels.gmail_handler import GmailHandler
from production.channels.whatsapp_handler import WhatsAppHandler

logger = logging.getLogger(__name__)


class UnifiedMessageProcessor:
    def __init__(self):
        self.gmail = GmailHandler()
        self.whatsapp = WhatsAppHandler()
        self.producer = FTEKafkaProducer()

    async def start(self) -> None:
        await self.producer.start()
        consumer = FTEKafkaConsumer(
            topics=[TOPICS["tickets_incoming"]],
            group_id="fte-message-processor",
        )
        await consumer.start()
        logger.info("Message processor started — listening on %s", TOPICS["tickets_incoming"])
        await consumer.consume(self.process_message)

    # ------------------------------------------------------------------
    # Core processing loop
    # ------------------------------------------------------------------

    async def process_message(self, topic: str, message: dict) -> None:
        start = datetime.now(timezone.utc)
        channel = message.get("channel", "web_form")

        try:
            # 1. Resolve customer (cross-channel)
            customer_id = await self._resolve_customer(message)

            # 2. Get / create conversation
            conversation_id = await get_or_create_conversation(customer_id, channel)

            # 3. Store inbound message
            await store_message(
                conversation_id=conversation_id,
                channel=channel,
                direction="inbound",
                role="customer",
                content=message.get("content", ""),
                channel_message_id=message.get("channel_message_id"),
            )

            # 4. Build message history for agent
            history = await load_conversation_history(conversation_id)
            openai_messages = [
                {"role": "user" if m["role"] == "customer" else "assistant",
                 "content": m["content"]}
                for m in history
            ]

            # 5. Run agent
            result = await Runner.run(
                customer_success_agent,
                messages=openai_messages,
                context={
                    "customer_id": customer_id,
                    "conversation_id": conversation_id,
                    "channel": channel,
                    "ticket_subject": message.get("subject", "Support Request"),
                    "customer_name": message.get("customer_name", "Valued Customer"),
                },
            )

            latency_ms = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )

            # 6. Store agent response
            tool_calls = [
                {"tool": tc.tool_name, "input": tc.tool_input}
                for tc in getattr(result, "tool_calls", [])
            ]
            await store_message(
                conversation_id=conversation_id,
                channel=channel,
                direction="outbound",
                role="agent",
                content=result.final_output or "",
                latency_ms=latency_ms,
                tool_calls=tool_calls,
            )

            # 7. Publish metrics
            await self.producer.publish(TOPICS["metrics"], {
                "event_type": "message_processed",
                "channel": channel,
                "latency_ms": latency_ms,
                "tool_calls_count": len(tool_calls),
            })

            logger.info(
                "Processed channel=%s latency=%dms tools=%d",
                channel, latency_ms, len(tool_calls),
            )

        except Exception as exc:
            logger.error("Processing error channel=%s: %s", channel, exc)
            await self._handle_error(message, exc)

    # ------------------------------------------------------------------
    # Customer resolution
    # ------------------------------------------------------------------

    async def _resolve_customer(self, message: dict) -> str:
        email = message.get("customer_email", "").strip().lower() or None
        phone = message.get("customer_phone", "").strip() or None
        name  = message.get("customer_name", "") or None
        return await get_or_create_customer(email=email, phone=phone, name=name)

    # ------------------------------------------------------------------
    # Error fallback
    # ------------------------------------------------------------------

    async def _handle_error(self, message: dict, error: Exception) -> None:
        channel = message.get("channel", "web_form")
        apology = (
            "I'm sorry, I'm having trouble processing your request right now. "
            "A human agent will follow up shortly."
        )
        try:
            if channel == "email" and message.get("customer_email"):
                await self.gmail.send_reply(
                    to_email=message["customer_email"],
                    subject=message.get("subject", "Support Request"),
                    body=apology,
                )
            elif channel == "whatsapp" and message.get("customer_phone"):
                await self.whatsapp.send_message(
                    to_phone=message["customer_phone"],
                    body=apology,
                )
        except Exception as send_err:
            logger.error("Failed to send error apology: %s", send_err)

        await self.producer.publish(TOPICS["escalations"], {
            "event_type": "processing_error",
            "channel": channel,
            "error": str(error),
            "original_message": message,
            "requires_human": True,
        })

        await self.producer.publish_to_dlq(
            TOPICS["tickets_incoming"], message, str(error)
        )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    processor = UnifiedMessageProcessor()
    await processor.start()


if __name__ == "__main__":
    asyncio.run(main())
