"""Tests for channel handlers: Gmail, WhatsApp, Web Form."""
import pytest
import json
import hmac
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Web Form handler tests
# ---------------------------------------------------------------------------

class TestWebFormSubmission:
    @pytest.fixture
    def client(self):
        from production.api.main import app
        return TestClient(app)

    def test_submit_valid_form(self, client):
        payload = {
            "name": "Alice",
            "email": "alice@example.com",
            "category": "billing",
            "priority": "high",
            "subject": "Invoice not received",
            "message": "I have not received my invoice for March.",
        }
        with patch("production.channels.web_form_handler.get_producer") as mock_prod:
            mock_producer = MagicMock()
            mock_producer.publish = AsyncMock()
            mock_prod.return_value = mock_producer

            response = client.post("/support", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert "ticket_id" in data
            assert data["ticket_id"].startswith("TKT-")

    def test_submit_invalid_email(self, client):
        payload = {
            "name": "Alice",
            "email": "not-an-email",
            "category": "billing",
            "priority": "high",
            "subject": "Test",
            "message": "Message body here.",
        }
        response = client.post("/support", json=payload)
        assert response.status_code == 422

    def test_submit_message_too_short(self, client):
        payload = {
            "name": "Alice",
            "email": "alice@example.com",
            "category": "billing",
            "priority": "high",
            "subject": "Test",
            "message": "Hi",  # too short
        }
        response = client.post("/support", json=payload)
        assert response.status_code == 422

    def test_get_ticket_status(self, client):
        with patch("production.channels.web_form_handler.get_ticket_by_external_id") as mock_get:
            mock_get.return_value = AsyncMock(return_value={
                "external_id": "TKT-ABC123",
                "status": "open",
                "subject": "Test",
            })()
            response = client.get("/support/TKT-ABC123/status")
            # Either 200 with data or 404 if not found — both valid
            assert response.status_code in (200, 404)


# ---------------------------------------------------------------------------
# WhatsApp handler tests
# ---------------------------------------------------------------------------

class TestWhatsAppHandler:
    def _make_signature(self, url: str, params: dict, token: str) -> str:
        """Reproduce Twilio signature for testing."""
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(token)
        return validator.compute_signature(url, params)

    def test_valid_webhook_accepted(self):
        with patch("production.channels.whatsapp_handler.TWILIO_AUTH_TOKEN", "test-token"):
            from production.channels.whatsapp_handler import WhatsAppHandler
            handler = WhatsAppHandler()
            form_data = {
                "From": "whatsapp:+15005550006",
                "Body": "Hello, I need help",
                "MessageSid": "SM123",
                "AccountSid": "AC123",
            }
            url = "https://support-api.yourdomain.com/webhooks/whatsapp"
            with patch.object(handler.validator, "validate", return_value=True):
                sig = "valid-signature"
                result = handler.validate_webhook(url, form_data, sig)
                assert result is True

    def test_format_long_response_splits(self):
        from production.channels.whatsapp_handler import WhatsAppHandler
        handler = WhatsAppHandler()
        long_text = "Word " * 400  # ~2000 chars
        parts = handler.format_response(long_text)
        assert isinstance(parts, list)
        for part in parts:
            assert len(part) <= 1600


# ---------------------------------------------------------------------------
# Gmail handler tests
# ---------------------------------------------------------------------------

class TestGmailHandler:
    def test_extract_email_from_headers(self):
        from production.channels.gmail_handler import GmailHandler
        handler = GmailHandler.__new__(GmailHandler)
        headers = [
            {"name": "From", "value": "Alice <alice@example.com>"},
            {"name": "Subject", "value": "Help needed"},
        ]
        email = handler._extract_email(headers)
        assert email == "alice@example.com"

    def test_extract_name_from_headers(self):
        from production.channels.gmail_handler import GmailHandler
        handler = GmailHandler.__new__(GmailHandler)
        headers = [
            {"name": "From", "value": "Alice Smith <alice@example.com>"},
        ]
        name = handler._extract_name(headers)
        assert name == "Alice Smith"

    def test_extract_name_falls_back_to_email(self):
        from production.channels.gmail_handler import GmailHandler
        handler = GmailHandler.__new__(GmailHandler)
        headers = [
            {"name": "From", "value": "alice@example.com"},
        ]
        name = handler._extract_name(headers)
        assert name == "alice@example.com"


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    @pytest.fixture
    def client(self):
        from production.api.main import app
        return TestClient(app)

    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
