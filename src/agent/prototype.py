"""
NovaFlow Customer Success FTE — Core Interaction Loop Prototype
Phase 1: Incubation

This prototype handles the full customer interaction cycle:
  1. Normalise incoming message (any channel)
  2. Retrieve customer history
  3. Search knowledge base
  4. Detect escalation need
  5. Generate channel-appropriate response
  6. Track ticket + sentiment
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class Channel(str, Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    WEB_FORM = "web_form"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResolutionStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    PENDING = "pending"


@dataclass
class IncomingMessage:
    """Normalised representation of a customer message regardless of channel."""
    channel: Channel
    content: str
    customer_id: str           # email or phone (unified key)
    customer_name: str = "Valued Customer"
    subject: str = "Support Request"
    channel_message_id: str = ""
    received_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Result produced by the agent for a given message."""
    ticket_id: str
    content: str               # raw response before channel formatting
    formatted_content: str     # channel-appropriate response
    channel: Channel
    should_escalate: bool
    escalation_reason: str
    sentiment_score: float
    resolution_status: ResolutionStatus
    topics_discussed: list[str]
    tool_calls: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# In-memory stores (replaced by PostgreSQL in production)
# ---------------------------------------------------------------------------

_ticket_store: dict[str, dict] = {}
_conversation_store: dict[str, list] = {}   # customer_id -> message history
_ticket_counter = 0


def _next_ticket_id() -> str:
    global _ticket_counter
    _ticket_counter += 1
    return f"TKT-{_ticket_counter:04d}"


# ---------------------------------------------------------------------------
# Knowledge base (loaded from product-docs.md)
# ---------------------------------------------------------------------------

def _load_knowledge_base() -> list[dict]:
    """Load product docs into searchable chunks."""
    docs_path = Path(__file__).parent.parent.parent / "context" / "product-docs.md"
    if not docs_path.exists():
        return []

    text = docs_path.read_text(encoding="utf-8")
    chunks = []
    current_section = ""
    current_content: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_section and current_content:
                chunks.append({
                    "title": current_section,
                    "content": "\n".join(current_content).strip(),
                    "category": current_section.lower().replace(" ", "_"),
                })
            current_section = line.lstrip("# ").strip()
            current_content = []
        elif line.startswith("### "):
            current_content.append(line)
        else:
            current_content.append(line)

    if current_section and current_content:
        chunks.append({
            "title": current_section,
            "content": "\n".join(current_content).strip(),
            "category": current_section.lower().replace(" ", "_"),
        })

    return chunks


_KB: list[dict] = _load_knowledge_base()


def search_knowledge_base(query: str, max_results: int = 3) -> list[dict]:
    """
    Simple keyword-based search (prototype).
    Production replaces this with pgvector cosine similarity.
    """
    query_tokens = set(re.sub(r"[^\w\s]", "", query.lower()).split())
    scored: list[tuple[float, dict]] = []

    for chunk in _KB:
        text = (chunk["title"] + " " + chunk["content"]).lower()
        text_tokens = set(re.sub(r"[^\w\s]", "", text).split())
        overlap = query_tokens & text_tokens
        if overlap:
            score = len(overlap) / (len(query_tokens) + 1)
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:max_results]]


# ---------------------------------------------------------------------------
# Escalation rules (loaded from escalation-rules.md keywords)
# ---------------------------------------------------------------------------

HARD_ESCALATION_KEYWORDS = {
    "legal_threat": ["lawyer", "legal", "sue", "attorney", "litigation", "lawsuit"],
    "refund_request": ["refund", "money back", "chargeback", "dispute", "reimburse"],
    "pricing_negotiation": ["custom deal", "discount", "cheaper", "lower price",
                             "negotiate", "custom quote"],
    "abusive_language": ["stupid", "idiot", "useless", "scam", "fraud", "terrible",
                          "ridiculous", "garbage"],
    "human_requested": ["speak to a human", "real person", "live agent", "speak to manager",
                         "talk to someone"],
    "security_incident": ["hacked", "unauthorized access", "someone logged in",
                           "breach", "compromised"],
    "compliance_inquiry": ["gdpr", "hipaa", "soc 2", "data deletion", "baa",
                            "penetration test", "pentest"],
}

WHATSAPP_HUMAN_TRIGGERS = {"human", "agent", "representative", "help me", "person"}


def detect_escalation(message: str, channel: Channel,
                       sentiment: float) -> tuple[bool, str]:
    """
    Returns (should_escalate, reason_code).
    Checks hard keyword triggers and sentiment threshold.
    """
    msg_lower = message.lower()

    # WhatsApp exact keyword triggers
    if channel == Channel.WHATSAPP:
        msg_stripped = msg_lower.strip().rstrip("!?.").strip()
        if msg_stripped in WHATSAPP_HUMAN_TRIGGERS:
            return True, "human_requested"

    # Hard keyword escalation
    for reason, keywords in HARD_ESCALATION_KEYWORDS.items():
        for kw in keywords:
            if kw in msg_lower:
                return True, reason

    # Sentiment-based escalation
    if sentiment < 0.25:
        return True, "negative_sentiment"

    return False, ""


# ---------------------------------------------------------------------------
# Sentiment analysis (prototype — rule-based; production uses LLM)
# ---------------------------------------------------------------------------

POSITIVE_WORDS = {"thank", "thanks", "great", "amazing", "love", "excellent",
                   "perfect", "awesome", "helpful", "quick", "resolved", "working"}
NEGATIVE_WORDS = {"broken", "error", "fail", "crash", "wrong", "issue", "problem",
                   "not working", "frustrated", "angry", "ridiculous", "terrible",
                   "never", "always fails", "still broken", "again"}
INTENSIFIERS = {"very", "extremely", "completely", "absolutely", "totally", "so"}


def analyse_sentiment(text: str) -> float:
    """
    Returns score in [0.0, 1.0]. 0 = very negative, 1 = very positive.
    Prototype uses keyword counting; production uses LLM classifier.
    """
    words = text.lower().split()
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)

    score = 0.5 + (pos * 0.08) - (neg * 0.1) - (caps_ratio * 0.3)
    return max(0.0, min(1.0, round(score, 2)))


# ---------------------------------------------------------------------------
# Channel-specific response formatting
# ---------------------------------------------------------------------------

MAX_LENGTHS = {
    Channel.EMAIL: 2000,
    Channel.WHATSAPP: 300,
    Channel.WEB_FORM: 600,
}


def format_for_channel(response: str, channel: Channel,
                        customer_name: str = "Valued Customer",
                        ticket_id: str = "") -> str:
    """Adapt the raw response to match channel tone and length constraints."""

    if channel == Channel.EMAIL:
        return (
            f"Hi {customer_name},\n\n"
            f"Thank you for reaching out to NovaFlow Support.\n\n"
            f"{response}\n\n"
            f"Please don't hesitate to reply if you have any further questions — "
            f"I'm happy to help.\n\n"
            f"Best regards,\n"
            f"NovaFlow Support Team\n"
            f"---\n"
            f"Ticket Reference: {ticket_id}\n"
            f"This response was generated by our AI assistant. "
            f"Reply to this email to continue the conversation."
        )

    elif channel == Channel.WHATSAPP:
        # Truncate to 300 chars for preferred WhatsApp length
        if len(response) > MAX_LENGTHS[Channel.WHATSAPP]:
            response = response[:297] + "..."
        return f"{response}\n\n📱 Reply for more help or type 'human' for live support."

    else:  # web_form
        return (
            f"{response}\n\n"
            f"---\n"
            f"Need more help? Reply to this message or visit support.novasaas.io.\n"
            f"Ticket ref: {ticket_id}"
        )


# ---------------------------------------------------------------------------
# Topic extraction (prototype)
# ---------------------------------------------------------------------------

TOPIC_KEYWORDS = {
    "salesforce": ["salesforce"],
    "slack": ["slack"],
    "hubspot": ["hubspot"],
    "stripe": ["stripe"],
    "billing": ["billing", "invoice", "plan", "upgrade", "payment", "refund"],
    "password": ["password", "reset", "login", "access"],
    "workflow": ["workflow", "trigger", "step", "branch", "execution"],
    "api": ["api", "webhook", "request", "endpoint"],
    "compliance": ["gdpr", "hipaa", "soc2", "compliance", "legal"],
    "onboarding": ["getting started", "first workflow", "new account", "team"],
}


def extract_topics(text: str) -> list[str]:
    text_lower = text.lower()
    return [topic for topic, kws in TOPIC_KEYWORDS.items()
            if any(kw in text_lower for kw in kws)]


# ---------------------------------------------------------------------------
# Response generation (prototype — rule-based; production uses LLM via SDK)
# ---------------------------------------------------------------------------

def generate_response(message: str, kb_results: list[dict],
                       customer_history: list, channel: Channel) -> str:
    """
    Generate a helpful response based on KB results and conversation history.
    Prototype uses templates; production uses OpenAI Agents SDK + GPT-4o.
    """
    if not message.strip():
        return ("It looks like your message came through empty. "
                "Could you please describe how I can help you today?")

    if not kb_results:
        return (
            "I want to make sure I give you accurate information, but I wasn't "
            "able to find specific documentation about your question. "
            "I'm connecting you with our specialist team who can give you a "
            "definitive answer."
        )

    # Build response from top KB result
    top = kb_results[0]
    intro = f"I found some relevant information about **{top['title']}**:\n\n"
    content = top["content"]

    # Trim content for channel
    max_content = {
        Channel.EMAIL: 800,
        Channel.WHATSAPP: 200,
        Channel.WEB_FORM: 400,
    }[channel]

    if len(content) > max_content:
        content = content[:max_content].rsplit(".", 1)[0] + "."

    suffix = ""
    if len(kb_results) > 1:
        suffix = f"\n\nI also found information about: {kb_results[1]['title']}. Would you like details on that too?"

    return intro + content + suffix


# ---------------------------------------------------------------------------
# Main agent function
# ---------------------------------------------------------------------------

def process_message(msg: IncomingMessage) -> AgentResponse:
    """
    Full interaction loop:
      create_ticket → get_history → search_kb → detect_escalation
      → generate_response → format → store
    """
    tool_calls: list[str] = []

    # 1. Create ticket
    ticket_id = _next_ticket_id()
    tool_calls.append(f"create_ticket(customer_id={msg.customer_id}, channel={msg.channel})")
    _ticket_store[ticket_id] = {
        "ticket_id": ticket_id,
        "customer_id": msg.customer_id,
        "channel": msg.channel,
        "subject": msg.subject,
        "status": "open",
        "created_at": msg.received_at,
    }

    # 2. Get customer history
    tool_calls.append(f"get_customer_history(customer_id={msg.customer_id})")
    history = _conversation_store.get(msg.customer_id, [])

    # 3. Analyse sentiment
    sentiment = analyse_sentiment(msg.content)

    # 4. Check escalation (early)
    should_escalate, esc_reason = detect_escalation(
        msg.content, msg.channel, sentiment
    )
    tool_calls.append(f"detect_escalation(sentiment={sentiment})")

    # 5. Search knowledge base
    kb_results = search_knowledge_base(msg.content)
    tool_calls.append(f"search_knowledge_base(query='{msg.content[:60]}...')")

    # 6. If no KB results + not already escalating → soft escalate
    if not kb_results and not should_escalate:
        should_escalate = True
        esc_reason = "knowledge_gap"

    # 7. Generate raw response
    if should_escalate:
        raw_response = _escalation_message(esc_reason, msg.channel)
        tool_calls.append(f"escalate_to_human(ticket_id={ticket_id}, reason={esc_reason})")
        _ticket_store[ticket_id]["status"] = "escalated"
        resolution = ResolutionStatus.ESCALATED
    else:
        raw_response = generate_response(msg.content, kb_results, history, msg.channel)
        resolution = ResolutionStatus.RESOLVED

    # 8. Format for channel
    formatted = format_for_channel(
        raw_response, msg.channel, msg.customer_name, ticket_id
    )
    tool_calls.append(f"send_response(ticket_id={ticket_id}, channel={msg.channel})")

    # 9. Store in conversation history
    _conversation_store.setdefault(msg.customer_id, []).append({
        "role": "customer",
        "content": msg.content,
        "channel": msg.channel,
        "timestamp": msg.received_at,
    })
    _conversation_store[msg.customer_id].append({
        "role": "agent",
        "content": formatted,
        "channel": msg.channel,
        "timestamp": datetime.utcnow().isoformat(),
    })

    # 10. Update ticket
    _ticket_store[ticket_id].update({
        "sentiment_score": sentiment,
        "resolution_status": resolution,
        "topics": extract_topics(msg.content),
    })

    return AgentResponse(
        ticket_id=ticket_id,
        content=raw_response,
        formatted_content=formatted,
        channel=msg.channel,
        should_escalate=should_escalate,
        escalation_reason=esc_reason,
        sentiment_score=sentiment,
        resolution_status=resolution,
        topics_discussed=extract_topics(msg.content),
        tool_calls=tool_calls,
    )


def _escalation_message(reason: str, channel: Channel) -> str:
    messages = {
        "legal_threat": (
            "I've flagged this as urgent and escalated it to our senior team. "
            "A team member will reach out to you directly and promptly."
        ),
        "refund_request": (
            "I've escalated your request to our billing team who handle all "
            "refund and subscription queries. They'll be in touch shortly."
        ),
        "pricing_negotiation": (
            "For custom pricing discussions, I'm connecting you with our "
            "sales team who can discuss your specific needs."
        ),
        "human_requested": (
            "Of course! I'm connecting you with a live team member right now."
        ),
        "security_incident": (
            "This is marked as urgent. Our security team has been alerted and "
            "will contact you immediately. Please do not log in until you hear from us."
        ),
        "compliance_inquiry": (
            "Compliance and legal documentation requests are handled by our "
            "security team. I've escalated this — expect a response within 24 hours."
        ),
        "negative_sentiment": (
            "I'm sorry you're having a frustrating experience. I want to make "
            "sure you get the best help, so I'm escalating this to our team now."
        ),
        "knowledge_gap": (
            "I want to give you accurate information, so I'm connecting you "
            "with a specialist who can answer your question definitively."
        ),
        "bug_report": (
            "Thank you for this detailed report. I've escalated it to our "
            "engineering team for investigation. You'll receive an update shortly."
        ),
        "repeat_contact": (
            "I can see you've reached out about this before — I sincerely "
            "apologize for the inconvenience. I'm escalating this to ensure "
            "it gets resolved properly."
        ),
    }
    return messages.get(reason, (
        "I've escalated your case to our specialist team who will follow up shortly."
    ))


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_cases = [
        IncomingMessage(
            channel=Channel.EMAIL,
            content="How do I reset my password? I can't log in.",
            customer_id="demo@example.com",
            customer_name="Demo User",
            subject="Password Reset",
        ),
        IncomingMessage(
            channel=Channel.WHATSAPP,
            content="hi my workflow stopped working",
            customer_id="+14155550101",
            customer_name="Carlos M",
        ),
        IncomingMessage(
            channel=Channel.WEB_FORM,
            content="I want to sue you people, your product destroyed my data!",
            customer_id="angry@customer.com",
            customer_name="Angry User",
            subject="Complaint",
        ),
        IncomingMessage(
            channel=Channel.WHATSAPP,
            content="human",
            customer_id="+447911123456",
            customer_name="Emma W",
        ),
        IncomingMessage(
            channel=Channel.EMAIL,
            content="",
            customer_id="empty@test.com",
            customer_name="Test",
            subject="(no subject)",
        ),
    ]

    for msg in test_cases:
        print(f"\n{'='*60}")
        print(f"[{msg.channel.upper()}] From: {msg.customer_id}")
        print(f"Message: {msg.content[:80] or '(empty)'}")
        print("-" * 60)

        result = process_message(msg)

        print(f"Ticket:    {result.ticket_id}")
        print(f"Sentiment: {result.sentiment_score}")
        print(f"Escalate:  {result.should_escalate} ({result.escalation_reason})")
        print(f"Topics:    {result.topics_discussed}")
        print(f"Tools:     {result.tool_calls}")
        print(f"\nFormatted Response:\n{result.formatted_content}")
