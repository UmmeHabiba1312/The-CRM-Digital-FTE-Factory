"""
NovaFlow Customer Success FTE — WhatsApp Channel Handler (Twilio)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from fastapi import Request, HTTPException
from twilio.request_validator import RequestValidator
from twilio.rest import Client

logger = logging.getLogger(__name__)


class WhatsAppHandler:
    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_WHATSAPP_NUMBER")
        self._client = None
        self._validator = None

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = Client(self.account_sid, self.auth_token)
        return self._client

    @property
    def validator(self) -> RequestValidator:
        if self._validator is None:
            self._validator = RequestValidator(self.auth_token)
        return self._validator

    # ------------------------------------------------------------------
    # Webhook validation (Principle VI — Security)
    # ------------------------------------------------------------------

    async def validate_webhook(self, request: Request) -> bool:
        """Validate Twilio signature. Returns False → 403."""
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)
        form_data = await request.form()
        return self.validator.validate(url, dict(form_data), signature)

    # ------------------------------------------------------------------
    # Inbound message parsing
    # ------------------------------------------------------------------

    async def process_webhook(self, form_data: dict) -> dict:
        phone = form_data.get("From", "").replace("whatsapp:", "")
        return {
            "channel": "whatsapp",
            "channel_message_id": form_data.get("MessageSid"),
            "customer_phone": phone,
            "customer_name": form_data.get("ProfileName", ""),
            "content": form_data.get("Body", "").strip(),
            "received_at": datetime.utcnow().isoformat(),
            "metadata": {
                "num_media": form_data.get("NumMedia", "0"),
                "wa_id": form_data.get("WaId"),
                "status": form_data.get("SmsStatus"),
            },
        }

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    async def send_message(self, to_phone: str, body: str) -> dict:
        if not to_phone.startswith("whatsapp:"):
            to_phone = f"whatsapp:{to_phone}"
        message = self.client.messages.create(
            body=body,
            from_=self.from_number,
            to=to_phone,
        )
        logger.info("WhatsApp sent sid=%s status=%s", message.sid, message.status)
        return {"channel_message_id": message.sid, "delivery_status": message.status}

    def format_response(self, response: str, max_length: int = 1600) -> list[str]:
        """Split long response into Twilio-safe chunks (≤1600 chars each)."""
        if len(response) <= max_length:
            return [response]
        parts: list[str] = []
        while response:
            if len(response) <= max_length:
                parts.append(response)
                break
            split_at = response.rfind(". ", 0, max_length)
            if split_at == -1:
                split_at = response.rfind(" ", 0, max_length)
            if split_at == -1:
                split_at = max_length
            parts.append(response[: split_at + 1].strip())
            response = response[split_at + 1 :].strip()
        return parts
