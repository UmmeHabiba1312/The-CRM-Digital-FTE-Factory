"""
NovaFlow Customer Success FTE — MCP Server
Phase 1: Incubation

Exposes prototype capabilities as MCP tools so Claude Code can
call them as structured functions during the incubation phase.

Tools exposed:
  1. search_knowledge_base   — query product docs
  2. create_ticket           — log an interaction with channel metadata
  3. get_customer_history    — retrieve past interactions across ALL channels
  4. escalate_to_human       — hand off to human agent
  5. send_response           — deliver reply via the correct channel
  6. analyse_sentiment       — score customer message sentiment
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make sure prototype module is importable
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from pydantic import BaseModel

from agent.prototype import (
    Channel,
    IncomingMessage,
    _ticket_store,
    _conversation_store,
    _next_ticket_id,
    analyse_sentiment,
    search_knowledge_base as _search_kb,
    format_for_channel,
    detect_escalation,
    extract_topics,
    process_message,
)
from datetime import datetime

# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------

server = Server("novaflow-customer-success-fte")


# ---------------------------------------------------------------------------
# Tool 1: search_knowledge_base
# ---------------------------------------------------------------------------

@server.tool("search_knowledge_base")
async def search_knowledge_base(query: str, max_results: int = 5) -> str:
    """
    Search NovaFlow product documentation for relevant information.

    Use this when:
    - Customer asks a product feature question
    - Customer needs how-to guidance
    - Customer reports an issue that may have a documented solution

    Args:
        query:       Natural language search query from the customer message
        max_results: Maximum number of documentation chunks to return (1-5)

    Returns:
        Formatted documentation snippets with section titles
    """
    results = _search_kb(query, max_results=max_results)

    if not results:
        return (
            "No relevant documentation found for this query. "
            "Consider escalating to a human agent with reason 'knowledge_gap'."
        )

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"**[{i}] {r['title']}**")
        lines.append(r["content"][:600])
        lines.append("---")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 2: create_ticket
# ---------------------------------------------------------------------------

@server.tool("create_ticket")
async def create_ticket(
    customer_id: str,
    issue: str,
    priority: str = "medium",
    channel: str = "web_form",
    customer_name: str = "Valued Customer",
    subject: str = "Support Request",
) -> str:
    """
    Create a support ticket to log the customer interaction.

    ALWAYS call this tool FIRST at the start of every conversation,
    before searching the knowledge base or sending any response.
    Include the source channel so cross-channel reports are accurate.

    Args:
        customer_id:   Email address (email/web_form) or phone number (whatsapp)
        issue:         Brief description of the customer's issue
        priority:      'low' | 'medium' | 'high' | 'critical'
        channel:       'email' | 'whatsapp' | 'web_form'
        customer_name: Customer's display name if available
        subject:       Email subject or form subject line

    Returns:
        Ticket ID string (e.g., 'TKT-0001') for use in subsequent tool calls
    """
    ticket_id = _next_ticket_id()
    _ticket_store[ticket_id] = {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "channel": channel,
        "subject": subject,
        "issue": issue,
        "priority": priority,
        "status": "open",
        "created_at": datetime.utcnow().isoformat(),
        "topics": extract_topics(issue),
    }
    return f"Ticket created: {ticket_id} | Channel: {channel} | Priority: {priority}"


# ---------------------------------------------------------------------------
# Tool 3: get_customer_history
# ---------------------------------------------------------------------------

@server.tool("get_customer_history")
async def get_customer_history(customer_id: str, limit: int = 10) -> str:
    """
    Retrieve a customer's full interaction history across ALL channels.

    Use this AFTER create_ticket to check for prior context, including
    conversations that happened on different channels (e.g., customer
    first emailed, now on WhatsApp).

    Args:
        customer_id: Email address or phone number
        limit:       Max number of recent messages to return

    Returns:
        Formatted conversation history showing channel, role, and content,
        or a message indicating this is a new customer.
    """
    history = _conversation_store.get(customer_id, [])

    if not history:
        return f"New customer: no prior interactions found for '{customer_id}'."

    lines = [f"Customer history for {customer_id} ({len(history)} messages):"]
    for msg in history[-limit:]:
        ts = msg.get("timestamp", "")[:10]
        role = msg.get("role", "unknown").upper()
        channel = msg.get("channel", "unknown")
        content = msg.get("content", "")[:120]
        lines.append(f"[{ts}] [{channel}] {role}: {content}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 4: escalate_to_human
# ---------------------------------------------------------------------------

@server.tool("escalate_to_human")
async def escalate_to_human(
    ticket_id: str,
    reason: str,
    urgency: str = "normal",
    context: str = "",
) -> str:
    """
    Escalate a conversation to a human support agent.

    Use this when ANY of the following are true:
    - Customer mentions 'lawyer', 'legal', 'sue', or 'attorney'
    - Customer requests a refund or chargeback
    - Customer sentiment is very negative (angry, abusive)
    - Knowledge base has no relevant answer after 2 searches
    - Customer explicitly asks for a human
    - WhatsApp customer sends 'human', 'agent', or 'representative'
    - Customer is on Enterprise plan with complex issue

    Args:
        ticket_id: Ticket ID from create_ticket
        reason:    One of: legal_threat | refund_request | pricing_negotiation |
                   abusive_language | human_requested | security_incident |
                   compliance_inquiry | knowledge_gap | negative_sentiment |
                   bug_report | repeat_contact | enterprise_priority
        urgency:   'critical' | 'high' | 'normal'
        context:   Brief summary of conversation context for the human agent

    Returns:
        Escalation confirmation with ticket ID and reason
    """
    if ticket_id in _ticket_store:
        _ticket_store[ticket_id]["status"] = "escalated"
        _ticket_store[ticket_id]["escalation_reason"] = reason
        _ticket_store[ticket_id]["escalation_urgency"] = urgency
        _ticket_store[ticket_id]["escalation_context"] = context
        _ticket_store[ticket_id]["escalated_at"] = datetime.utcnow().isoformat()

    return (
        f"Escalated ticket {ticket_id} to human agent. "
        f"Reason: {reason} | Urgency: {urgency}. "
        f"Human agent will contact the customer directly."
    )


# ---------------------------------------------------------------------------
# Tool 5: send_response
# ---------------------------------------------------------------------------

@server.tool("send_response")
async def send_response(
    ticket_id: str,
    message: str,
    channel: str,
    customer_id: str = "",
    customer_name: str = "Valued Customer",
) -> str:
    """
    Send a response to the customer via their channel.

    ALWAYS call this as the LAST tool before finishing.
    Never respond without using this tool — it ensures correct
    channel formatting and delivery status tracking.

    The message will be automatically formatted for the channel:
    - Email:     Formal greeting + structured body + signature
    - WhatsApp:  Concise (≤300 chars) + emoji CTA
    - Web Form:  Semi-formal + ticket reference

    Args:
        ticket_id:     Ticket ID from create_ticket
        message:       Raw response text (before channel formatting)
        channel:       'email' | 'whatsapp' | 'web_form'
        customer_id:   Customer identifier (for storing in history)
        customer_name: Customer name for personalised greeting

    Returns:
        Delivery status confirmation with formatted preview
    """
    try:
        ch = Channel(channel)
    except ValueError:
        return f"Error: unknown channel '{channel}'. Use: email | whatsapp | web_form"

    formatted = format_for_channel(message, ch, customer_name, ticket_id)

    # Store in conversation history
    if customer_id:
        _conversation_store.setdefault(customer_id, []).append({
            "role": "agent",
            "content": formatted,
            "channel": channel,
            "timestamp": datetime.utcnow().isoformat(),
        })

    # Update ticket status
    if ticket_id in _ticket_store:
        _ticket_store[ticket_id]["status"] = "resolved"
        _ticket_store[ticket_id]["resolved_at"] = datetime.utcnow().isoformat()

    preview = formatted[:200] + ("..." if len(formatted) > 200 else "")
    return f"Response sent via {channel}. Delivery: sent\nPreview: {preview}"


# ---------------------------------------------------------------------------
# Tool 6: analyse_sentiment
# ---------------------------------------------------------------------------

@server.tool("analyse_sentiment")
async def analyse_sentiment_tool(message: str) -> str:
    """
    Analyse the sentiment of a customer message.

    Use this on EVERY incoming customer message to:
    - Gauge emotional state before responding
    - Detect when escalation may be needed (score < 0.3)
    - Track sentiment trends across the conversation

    Args:
        message: Raw customer message text

    Returns:
        JSON with score (0.0–1.0), label, and escalation recommendation.
        0.0 = extremely negative, 0.5 = neutral, 1.0 = very positive
    """
    score = analyse_sentiment(message)
    label = (
        "very_negative" if score < 0.2 else
        "negative"      if score < 0.4 else
        "neutral"        if score < 0.6 else
        "positive"       if score < 0.8 else
        "very_positive"
    )
    should_escalate = score < 0.3
    return json.dumps({
        "score": score,
        "label": label,
        "should_escalate": should_escalate,
        "recommendation": (
            "Escalate immediately — customer is very unhappy"
            if should_escalate else
            "Proceed with empathetic response"
        ),
    }, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                         server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
