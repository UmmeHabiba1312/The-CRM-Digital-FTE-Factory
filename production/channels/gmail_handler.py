"""
NovaFlow Customer Success FTE — Gmail Channel Handler
Handles Gmail push notifications via Pub/Sub and sends email replies.
"""
from __future__ import annotations

import base64
import logging
import os
import re
from datetime import datetime
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class GmailHandler:
    def __init__(self):
        self.service = None

    def _get_service(self):
        if self.service is None:
            import json
            creds_json = os.getenv("GMAIL_CREDENTIALS")
            if not creds_json:
                raise EnvironmentError("GMAIL_CREDENTIALS env var not set")
            creds_data = json.loads(creds_json)
            creds = Credentials.from_authorized_user_info(creds_data)
            self.service = build("gmail", "v1", credentials=creds)
        return self.service

    # ------------------------------------------------------------------
    # Webhook / push setup
    # ------------------------------------------------------------------

    async def setup_push_notifications(self, topic_name: str) -> dict:
        """Register Gmail push notifications via Cloud Pub/Sub."""
        svc = self._get_service()
        return svc.users().watch(
            userId="me",
            body={"labelIds": ["INBOX"], "topicName": topic_name,
                  "labelFilterAction": "include"},
        ).execute()

    async def process_notification(self, pubsub_message: dict) -> list[dict]:
        """Decode a Pub/Sub notification and return parsed messages."""
        history_id = pubsub_message.get("historyId")
        if not history_id:
            return []
        svc = self._get_service()
        history = svc.users().history().list(
            userId="me",
            startHistoryId=history_id,
            historyTypes=["messageAdded"],
        ).execute()

        messages = []
        for record in history.get("history", []):
            for added in record.get("messagesAdded", []):
                msg_id = added["message"]["id"]
                try:
                    messages.append(await self.get_message(msg_id))
                except Exception as exc:
                    logger.error("Failed to fetch Gmail message %s: %s", msg_id, exc)
        return messages

    async def get_message(self, message_id: str) -> dict:
        svc = self._get_service()
        msg = svc.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        body = self._extract_body(msg["payload"])
        return {
            "channel": "email",
            "channel_message_id": message_id,
            "customer_email": self._extract_email(headers.get("From", "")),
            "customer_name": self._extract_name(headers.get("From", "")),
            "subject": headers.get("Subject", "Support Request"),
            "content": body,
            "received_at": datetime.utcnow().isoformat(),
            "thread_id": msg.get("threadId"),
            "metadata": {"headers": headers, "labels": msg.get("labelIds", [])},
        }

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    async def send_reply(
        self,
        to_email: str,
        subject: str,
        body: str,
        thread_id: str = None,
    ) -> dict:
        svc = self._get_service()
        msg = MIMEText(body)
        msg["to"] = to_email
        msg["subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        payload: dict = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id
        result = svc.users().messages().send(userId="me", body=payload).execute()
        return {"channel_message_id": result["id"], "delivery_status": "sent"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_body(self, payload: dict) -> str:
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            if part["mimeType"] == "text/plain":
                return base64.urlsafe_b64decode(
                    part["body"]["data"]
                ).decode("utf-8", errors="replace")
        return ""

    def _extract_email(self, from_header: str) -> str:
        match = re.search(r"<(.+?)>", from_header)
        return match.group(1) if match else from_header.strip()

    def _extract_name(self, from_header: str) -> str:
        match = re.match(r'^"?([^"<]+)"?\s*<', from_header)
        return match.group(1).strip() if match else ""
