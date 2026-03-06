"""
NovaFlow Customer Success FTE — FastAPI Service
All channel webhook endpoints + support form + metrics.
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from database.queries import (
    close_db_pool,
    get_channel_metrics,
    load_conversation_history,
    update_delivery_status,
)
from kafka_client import FTEKafkaProducer, TOPICS, get_producer
from production.channels.gmail_handler import GmailHandler
from production.channels.whatsapp_handler import WhatsAppHandler
from production.channels.web_form_handler import router as web_form_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="NovaFlow Customer Success FTE API",
    description="24/7 AI-powered customer support — Email, WhatsApp, Web Form",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Lock down to specific origins in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(web_form_router)

gmail_handler    = GmailHandler()
whatsapp_handler = WhatsAppHandler()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    producer = await get_producer()
    logger.info("API started — Kafka producer ready")


@app.on_event("shutdown")
async def shutdown() -> None:
    from kafka_client import _producer
    if _producer:
        await _producer.stop()
    await close_db_pool()
    logger.info("API shutdown complete")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "channels": {"email": "active", "whatsapp": "active", "web_form": "active"},
    }


# ---------------------------------------------------------------------------
# Gmail webhook (Pub/Sub push)
# ---------------------------------------------------------------------------

@app.post("/webhooks/gmail")
async def gmail_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle Gmail push notifications via Cloud Pub/Sub."""
    try:
        body = await request.json()
        messages = await gmail_handler.process_notification(body)
        producer = await get_producer()
        for msg in messages:
            background_tasks.add_task(
                producer.publish, TOPICS["tickets_incoming"], msg
            )
        return {"status": "processed", "count": len(messages)}
    except Exception as exc:
        logger.error("Gmail webhook error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# WhatsApp webhook (Twilio)
# ---------------------------------------------------------------------------

@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming WhatsApp messages from Twilio."""
    # Validate Twilio signature (Principle VI — Security)
    if not await whatsapp_handler.validate_webhook(request):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    form_data = dict(await request.form())
    message   = await whatsapp_handler.process_webhook(form_data)
    producer  = await get_producer()
    background_tasks.add_task(
        producer.publish, TOPICS["tickets_incoming"], message
    )
    # Empty TwiML — agent replies asynchronously via Twilio API
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


@app.post("/webhooks/whatsapp/status")
async def whatsapp_status(request: Request):
    """Update delivery status from Twilio status callback."""
    form_data = dict(await request.form())
    await update_delivery_status(
        channel_message_id=form_data.get("MessageSid", ""),
        status=form_data.get("MessageStatus", "unknown"),
    )
    return {"status": "received"}


# ---------------------------------------------------------------------------
# Customer / conversation lookups
# ---------------------------------------------------------------------------

@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    history = await load_conversation_history(conversation_id)
    if not history:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation_id": conversation_id, "messages": history}


@app.get("/customers/lookup")
async def lookup_customer(email: str = None, phone: str = None):
    from database.queries import resolve_customer
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Provide email or phone")
    customer_id = await resolve_customer(email=email, phone=phone)
    if not customer_id:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"customer_id": customer_id, "email": email, "phone": phone}


# ---------------------------------------------------------------------------
# Metrics (Principle IX — Observability)
# ---------------------------------------------------------------------------

@app.get("/metrics/channels")
async def channel_metrics(hours: int = 24):
    """Return conversation metrics broken down by channel."""
    rows = await get_channel_metrics(hours=hours)
    return {r["channel"]: dict(r) for r in rows}
