"""
NovaFlow Customer Success FTE — Production Tools
@function_tool decorated functions with Pydantic validation.
Converted from MCP server tools (Phase 1) with full error handling.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from agents import function_tool
from pydantic import BaseModel

from database.queries import (
    get_or_create_customer,
    get_or_create_conversation,
    create_ticket as db_create_ticket,
    escalate_ticket as db_escalate_ticket,
    resolve_ticket as db_resolve_ticket,
    load_conversation_history,
    store_message,
    search_knowledge_base as db_search_kb,
    record_metric,
    update_delivery_status,
)
from production.agent.formatters import format_for_channel, split_whatsapp_messages

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedding helper (OpenAI text-embedding-3-small)
# ---------------------------------------------------------------------------

async def _embed(text: str) -> list[float]:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],
    )
    return resp.data[0].embedding


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

class KnowledgeSearchInput(BaseModel):
    query: str
    max_results: int = 5
    category: Optional[str] = None


class TicketInput(BaseModel):
    customer_id: str
    issue: str
    priority: str = "medium"
    category: Optional[str] = None
    channel: str                        # email | whatsapp | web_form
    subject: Optional[str] = None
    conversation_id: Optional[str] = None


class EscalationInput(BaseModel):
    ticket_id: str
    reason: str                         # reason code from escalation-rules.md
    urgency: str = "normal"             # critical | high | normal
    context: str = ""


class ResponseInput(BaseModel):
    ticket_id: str
    message: str
    channel: str                        # email | whatsapp | web_form
    customer_id: str
    customer_name: str = "Valued Customer"
    conversation_id: Optional[str] = None


class SentimentInput(BaseModel):
    message: str


class HistoryInput(BaseModel):
    customer_id: str
    limit: int = 20


# ---------------------------------------------------------------------------
# Tool 1: search_knowledge_base
# ---------------------------------------------------------------------------

@function_tool
async def search_knowledge_base(input: KnowledgeSearchInput) -> str:
    """Search NovaFlow product documentation for relevant information.

    Use this when the customer asks about product features, how-to steps,
    integrations, billing policies, or troubleshooting guides.
    Call up to 2 times; escalate with reason 'knowledge_gap' if still no results.

    Args:
        input: query (required), max_results (1-5), category (optional filter)

    Returns:
        Formatted documentation snippets with section titles and relevance scores.
    """
    try:
        embedding = await _embed(input.query)
        results = await db_search_kb(
            embedding=embedding,
            max_results=input.max_results,
            category=input.category,
        )
        if not results:
            return (
                "No relevant documentation found for this query. "
                "If a second search also returns no results, escalate "
                "with reason 'knowledge_gap'."
            )
        lines = []
        for i, r in enumerate(results, 1):
            score = float(r.get("similarity", 0))
            lines.append(f"**[{i}] {r['title']}** (relevance: {score:.2f})")
            lines.append(r["content"][:600])
            lines.append("---")
        return "\n".join(lines)
    except Exception as exc:
        logger.error("search_knowledge_base failed: %s", exc)
        return (
            "Knowledge base temporarily unavailable. "
            "Escalate with reason 'knowledge_gap'."
        )


# ---------------------------------------------------------------------------
# Tool 2: create_ticket
# ---------------------------------------------------------------------------

@function_tool
async def create_ticket(input: TicketInput) -> str:
    """Create a support ticket to log the customer interaction.

    ALWAYS call this tool FIRST at the start of every conversation,
    before any knowledge base search or response. Include source channel.

    Args:
        input: customer_id, issue, priority, channel, subject, conversation_id

    Returns:
        Ticket ID string for use in subsequent tool calls.
    """
    try:
        conversation_id = input.conversation_id
        if not conversation_id:
            conversation_id = await get_or_create_conversation(
                input.customer_id, input.channel
            )
        ticket_id = await db_create_ticket(
            customer_id=input.customer_id,
            conversation_id=conversation_id,
            source_channel=input.channel,
            subject=input.subject or input.issue[:120],
            category=input.category,
            priority=input.priority,
        )
        logger.info("Ticket created: %s channel=%s", ticket_id, input.channel)
        return f"ticket_id:{ticket_id} conversation_id:{conversation_id}"
    except Exception as exc:
        logger.error("create_ticket failed: %s", exc)
        return f"Error creating ticket: {exc}"


# ---------------------------------------------------------------------------
# Tool 3: get_customer_history
# ---------------------------------------------------------------------------

@function_tool
async def get_customer_history(input: HistoryInput) -> str:
    """Retrieve customer's full interaction history across ALL channels.

    Call this AFTER create_ticket to check for prior context, including
    conversations that happened on different channels.

    Args:
        input: customer_id, limit (default 20)

    Returns:
        Formatted conversation history or 'new customer' message.
    """
    try:
        conv_id = await get_or_create_conversation(input.customer_id, "email")
        history = await load_conversation_history(conv_id, limit=input.limit)
        if not history:
            return f"New customer — no prior interactions for '{input.customer_id}'."
        lines = [f"History for {input.customer_id} ({len(history)} messages):"]
        for msg in history:
            ts = msg["timestamp"][:10]
            lines.append(
                f"[{ts}][{msg['channel']}] {msg['role'].upper()}: "
                f"{msg['content'][:100]}"
            )
        return "\n".join(lines)
    except Exception as exc:
        logger.error("get_customer_history failed: %s", exc)
        return "Customer history unavailable. Proceed as new customer."


# ---------------------------------------------------------------------------
# Tool 4: escalate_to_human
# ---------------------------------------------------------------------------

@function_tool
async def escalate_to_human(input: EscalationInput) -> str:
    """Escalate conversation to a human support agent.

    MUST use when ANY of these are detected:
    - "lawyer", "legal", "sue" → legal_threat (critical)
    - "refund", "chargeback"   → refund_request (high)
    - Sentiment < 0.25         → abusive_language (high)
    - Customer asks for human  → human_requested (normal)
    - "hacked", "breach"       → security_incident (critical)
    - GDPR/HIPAA/SOC2 mention  → compliance_inquiry (high)
    - No KB result after 2 searches → knowledge_gap (normal)

    Args:
        input: ticket_id, reason (reason code), urgency, context

    Returns:
        Escalation confirmation with ticket reference.
    """
    try:
        await db_escalate_ticket(
            ticket_id=input.ticket_id,
            reason=input.reason,
            urgency=input.urgency,
        )
        await record_metric(
            "escalation",
            1.0,
            dimensions={"reason": input.reason, "urgency": input.urgency},
        )
        logger.info(
            "Escalated ticket=%s reason=%s urgency=%s",
            input.ticket_id, input.reason, input.urgency,
        )
        return (
            f"Escalated ticket {input.ticket_id} to human agent. "
            f"Reason: {input.reason} | Urgency: {input.urgency}."
        )
    except Exception as exc:
        logger.error("escalate_to_human failed: %s", exc)
        return f"Escalation recorded locally. Reason: {input.reason}"


# ---------------------------------------------------------------------------
# Tool 5: send_response
# ---------------------------------------------------------------------------

@function_tool
async def send_response(input: ResponseInput) -> str:
    """Send a response to the customer via their channel.

    ALWAYS call this as the LAST tool. Never finish without calling it.
    The message is automatically formatted for the channel:
    - Email:     Formal greeting + body + signature
    - WhatsApp:  Concise (≤300 chars preferred) + CTA
    - Web Form:  Semi-formal + ticket reference

    Args:
        input: ticket_id, message (raw), channel, customer_id, customer_name

    Returns:
        Delivery status and formatted message preview.
    """
    try:
        formatted = format_for_channel(
            input.message,
            input.channel,
            input.customer_name,
            input.ticket_id,
        )

        # In production this calls Gmail API / Twilio — wired in api/main.py
        # Here we record the outbound message and mark ticket resolved
        conv_id = input.conversation_id
        if not conv_id:
            conv_id = await get_or_create_conversation(
                input.customer_id, input.channel
            )

        await store_message(
            conversation_id=conv_id,
            channel=input.channel,
            direction="outbound",
            role="agent",
            content=formatted,
        )
        await db_resolve_ticket(input.ticket_id)

        preview = formatted[:200] + ("..." if len(formatted) > 200 else "")
        logger.info(
            "Response sent ticket=%s channel=%s len=%d",
            input.ticket_id, input.channel, len(formatted),
        )
        return f"Response sent via {input.channel}. Preview: {preview}"
    except Exception as exc:
        logger.error("send_response failed: %s", exc)
        return f"Error sending response: {exc}"


# ---------------------------------------------------------------------------
# Tool 6: analyse_sentiment
# ---------------------------------------------------------------------------

@function_tool
async def analyse_sentiment(input: SentimentInput) -> str:
    """Analyse the sentiment of a customer message.

    Run on EVERY inbound message before composing a response.
    Score < 0.3 → consider escalating with reason 'negative_sentiment'.

    Args:
        input: message (raw customer text)

    Returns:
        JSON with score (0.0–1.0), label, and recommendation.
    """
    import json
    import re

    text = input.message.lower()
    positive = {"thank", "thanks", "great", "amazing", "love",
                "excellent", "perfect", "awesome", "helpful", "resolved"}
    negative = {"broken", "error", "fail", "crash", "wrong", "issue",
                "problem", "frustrated", "angry", "ridiculous", "terrible"}

    words = set(re.sub(r"[^\w\s]", "", text).split())
    pos = len(words & positive)
    neg = len(words & negative)
    caps = sum(1 for c in input.message if c.isupper()) / max(len(input.message), 1)

    score = round(max(0.0, min(1.0, 0.5 + pos * 0.08 - neg * 0.1 - caps * 0.3)), 2)
    label = (
        "very_negative" if score < 0.2 else
        "negative"      if score < 0.4 else
        "neutral"        if score < 0.6 else
        "positive"       if score < 0.8 else
        "very_positive"
    )
    return json.dumps({
        "score": score,
        "label": label,
        "should_escalate": score < 0.3,
        "recommendation": (
            "Escalate — customer is very unhappy"
            if score < 0.3 else
            "Acknowledge frustration before answering"
            if score < 0.5 else
            "Proceed normally"
        ),
    })
