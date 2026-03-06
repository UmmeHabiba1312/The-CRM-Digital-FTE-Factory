"""End-to-end integration tests for the full message processing pipeline."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from production.api.main import app
    return TestClient(app)


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg pool so tests don't need a real DB."""
    pool = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    pool.acquire = AsyncMock(return_value=conn)
    pool.__aenter__ = AsyncMock(return_value=pool)
    pool.__aexit__ = AsyncMock()
    return pool


@pytest.fixture
def mock_kafka_producer():
    producer = MagicMock()
    producer.publish = AsyncMock()
    producer.publish_to_dlq = AsyncMock()
    return producer


# ---------------------------------------------------------------------------
# E2E: Web Form → Kafka → Processor (mocked)
# ---------------------------------------------------------------------------

class TestWebFormE2E:
    def test_form_submission_publishes_to_kafka(self, client, mock_kafka_producer):
        payload = {
            "name": "Carlos",
            "email": "carlos@acme.com",
            "category": "technical",
            "priority": "medium",
            "subject": "API rate limit exceeded",
            "message": "I keep getting 429 errors on your REST API since this morning.",
        }
        with patch("production.channels.web_form_handler.get_producer",
                   return_value=mock_kafka_producer):
            response = client.post("/support", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "ticket_id" in data
        assert "estimated_response_time" in data

    def test_form_submission_returns_ticket_id_format(self, client, mock_kafka_producer):
        payload = {
            "name": "Diana",
            "email": "diana@corp.com",
            "category": "billing",
            "priority": "high",
            "subject": "Double charged last month",
            "message": "I was charged twice for my subscription in February.",
        }
        with patch("production.channels.web_form_handler.get_producer",
                   return_value=mock_kafka_producer):
            response = client.post("/support", json=payload)

        ticket_id = response.json()["ticket_id"]
        assert ticket_id.startswith("TKT-")
        assert len(ticket_id) > 4


# ---------------------------------------------------------------------------
# E2E: WhatsApp webhook → validation → publish (mocked)
# ---------------------------------------------------------------------------

class TestWhatsAppE2E:
    def test_whatsapp_webhook_without_signature_rejected(self, client):
        form_data = {
            "From": "whatsapp:+15005550006",
            "Body": "I need help",
            "MessageSid": "SM123",
            "AccountSid": "AC123",
        }
        response = client.post(
            "/webhooks/whatsapp",
            data=form_data,
            headers={"X-Twilio-Signature": "bad-signature"},
        )
        # Should be 403 Forbidden
        assert response.status_code == 403

    def test_whatsapp_status_callback_accepted(self, client):
        """Status callbacks (delivered, read) should always return 200."""
        form_data = {
            "MessageSid": "SM123",
            "MessageStatus": "delivered",
            "To": "whatsapp:+15005550006",
        }
        response = client.post("/webhooks/whatsapp/status", data=form_data)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# E2E: Gmail Pub/Sub notification
# ---------------------------------------------------------------------------

class TestGmailE2E:
    def test_gmail_webhook_requires_pubsub_format(self, client):
        """Malformed Pub/Sub payload should return 400."""
        response = client.post(
            "/webhooks/gmail",
            json={"not": "pubsub"},
        )
        assert response.status_code in (400, 422)

    def test_gmail_webhook_valid_pubsub_accepted(self, client, mock_kafka_producer):
        import base64
        notification = base64.b64encode(
            json.dumps({"emailAddress": "user@example.com", "historyId": "12345"}).encode()
        ).decode()

        pubsub_payload = {
            "message": {
                "data": notification,
                "messageId": "msg-001",
                "publishTime": "2026-03-06T10:00:00Z",
            },
            "subscription": "projects/my-project/subscriptions/gmail-push",
        }
        with patch("production.channels.gmail_handler.GmailHandler.process_notification",
                   new_callable=AsyncMock) as mock_process, \
             patch("production.channels.gmail_handler.GmailHandler.setup_push_notifications",
                   new_callable=AsyncMock):
            mock_process.return_value = None
            response = client.post("/webhooks/gmail", json=pubsub_payload)
            assert response.status_code in (200, 202)


# ---------------------------------------------------------------------------
# E2E: Message processor (unit-level with full mock)
# ---------------------------------------------------------------------------

class TestMessageProcessor:
    @pytest.mark.asyncio
    async def test_process_message_calls_runner(self, mock_db_pool, mock_kafka_producer):
        from production.workers.message_processor import UnifiedMessageProcessor

        mock_result = MagicMock()
        mock_result.final_output = "Your ticket has been created."

        with patch("production.workers.message_processor.asyncpg") as mock_asyncpg, \
             patch("production.workers.message_processor.Runner") as MockRunner, \
             patch("production.workers.message_processor.get_producer",
                   return_value=mock_kafka_producer):

            mock_asyncpg.create_pool = AsyncMock(return_value=mock_db_pool)
            MockRunner.run = AsyncMock(return_value=mock_result)

            processor = UnifiedMessageProcessor.__new__(UnifiedMessageProcessor)
            processor.pool = mock_db_pool
            processor.producer = mock_kafka_producer

            message = {
                "channel": "web_form",
                "customer_email": "test@example.com",
                "customer_name": "Test User",
                "message_text": "I need help with billing",
                "ticket_id": "TKT-TEST001",
                "conversation_id": None,
            }

            with patch.object(processor, "_resolve_customer", new_callable=AsyncMock,
                              return_value={"id": 1, "name": "Test User"}), \
                 patch("production.workers.message_processor.get_or_create_conversation",
                       new_callable=AsyncMock, return_value={"id": 10}), \
                 patch("production.workers.message_processor.store_message",
                       new_callable=AsyncMock, return_value={"id": 100}), \
                 patch("production.workers.message_processor.get_conversation_history",
                       new_callable=AsyncMock, return_value=[]), \
                 patch("production.workers.message_processor.record_agent_metrics",
                       new_callable=AsyncMock):
                await processor.process_message(message)

            MockRunner.run.assert_called_once()
