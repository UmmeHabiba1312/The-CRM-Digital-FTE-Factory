"""
NovaFlow Customer Success FTE — Web Form Channel Handler
FastAPI router mounted at /support
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, field_validator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/support", tags=["support-form"])

VALID_CATEGORIES = {"general", "technical", "billing", "feedback", "bug_report"}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SupportFormSubmission(BaseModel):
    name: str
    email: EmailStr
    subject: str
    category: str
    message: str
    priority: Optional[str] = "medium"
    attachments: Optional[list[str]] = []

    @field_validator("name")
    @classmethod
    def name_min_length(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v.strip()

    @field_validator("message")
    @classmethod
    def message_min_length(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("Message must be at least 10 characters")
        return v.strip()

    @field_validator("category")
    @classmethod
    def category_valid(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}")
        return v


class SupportFormResponse(BaseModel):
    ticket_id: str
    message: str
    estimated_response_time: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/submit", response_model=SupportFormResponse)
async def submit_support_form(submission: SupportFormSubmission):
    """
    Accept a web support form submission.
    1. Validate input (Pydantic)
    2. Publish normalised message to Kafka
    3. Return ticket confirmation
    """
    from kafka_client import get_producer, TOPICS

    ticket_id = str(uuid.uuid4())
    message_data = {
        "channel": "web_form",
        "channel_message_id": ticket_id,
        "customer_email": str(submission.email),
        "customer_name": submission.name,
        "subject": submission.subject,
        "content": submission.message,
        "category": submission.category,
        "priority": submission.priority,
        "received_at": datetime.utcnow().isoformat(),
        "metadata": {
            "form_version": "1.0",
            "attachments": submission.attachments,
        },
    }

    try:
        producer = await get_producer()
        await producer.publish(TOPICS["tickets_incoming"], message_data)
    except Exception as exc:
        logger.error("Kafka publish failed for web form: %s", exc)
        # Don't block the customer response — ticket will be retried via DLQ

    return SupportFormResponse(
        ticket_id=ticket_id,
        message="Thank you for contacting us! Our AI assistant will respond shortly.",
        estimated_response_time="Usually within 5 minutes",
    )


@router.get("/ticket/{ticket_id}")
async def get_ticket_status(ticket_id: str):
    """Get ticket status and conversation history by ticket ID."""
    from database.queries import get_ticket, load_conversation_history

    ticket = await get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    history: list = []
    if ticket.get("conversation_id"):
        history = await load_conversation_history(ticket["conversation_id"])

    return {
        "ticket_id": ticket_id,
        "status": ticket["status"],
        "source_channel": ticket["source_channel"],
        "created_at": ticket["created_at"].isoformat() if ticket.get("created_at") else None,
        "messages": [
            {"role": m["role"], "content": m["content"], "channel": m["channel"]}
            for m in history
        ],
    }
