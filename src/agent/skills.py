"""
NovaFlow Customer Success FTE — Agent Skills Manifest
Phase 1: Incubation

Defines the 5 reusable skills the FTE agent can invoke.
Each skill is a self-contained capability with:
  - when_to_use   : trigger condition
  - inputs        : expected parameters
  - outputs       : returned data shape
  - mcp_tool      : corresponding MCP server tool name
  - channel_notes : channel-specific behaviour differences
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from agent.prototype import (
    Channel,
    IncomingMessage,
    analyse_sentiment,
    detect_escalation,
    extract_topics,
    format_for_channel,
    search_knowledge_base,
)


# ---------------------------------------------------------------------------
# Skill base type
# ---------------------------------------------------------------------------

@dataclass
class Skill:
    name: str
    description: str
    when_to_use: str
    inputs: dict[str, str]          # param_name -> description
    outputs: dict[str, str]         # field_name -> description
    mcp_tool: str
    channel_notes: dict[str, str]   # channel -> behaviour note
    execute: Optional[Callable] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Skill 1: Knowledge Retrieval
# ---------------------------------------------------------------------------

def _execute_knowledge_retrieval(query: str, max_results: int = 3) -> dict:
    results = search_knowledge_base(query, max_results=max_results)
    if not results:
        return {
            "found": False,
            "results": [],
            "summary": "No relevant documentation found.",
            "recommend_escalate": True,
        }
    return {
        "found": True,
        "results": results,
        "summary": f"Found {len(results)} relevant section(s): "
                   + ", ".join(r["title"] for r in results),
        "recommend_escalate": False,
    }


KNOWLEDGE_RETRIEVAL = Skill(
    name="Knowledge Retrieval",
    description=(
        "Searches NovaFlow product documentation to find answers "
        "to customer questions about features, how-to steps, integrations, "
        "billing policies, and troubleshooting guides."
    ),
    when_to_use=(
        "Customer asks a product question, how-to query, integration question, "
        "or troubleshooting request. Always invoke before composing a response."
    ),
    inputs={
        "query": "Natural language question extracted from the customer message.",
        "max_results": "Maximum KB sections to return (default 3, max 5).",
    },
    outputs={
        "found": "Boolean — whether relevant docs were found.",
        "results": "List of {title, content, category} dicts.",
        "summary": "Human-readable summary of what was found.",
        "recommend_escalate": "True if no docs found and human help is needed.",
    },
    mcp_tool="search_knowledge_base",
    channel_notes={
        Channel.EMAIL: "Return up to 3 results; include full step-by-step content.",
        Channel.WHATSAPP: "Use only top result; trim content to 200 chars.",
        Channel.WEB_FORM: "Return top 2 results; use structured formatting.",
    },
    execute=_execute_knowledge_retrieval,
)


# ---------------------------------------------------------------------------
# Skill 2: Sentiment Analysis
# ---------------------------------------------------------------------------

def _execute_sentiment_analysis(message: str) -> dict:
    score = analyse_sentiment(message)
    label = (
        "very_negative" if score < 0.2 else
        "negative"      if score < 0.4 else
        "neutral"        if score < 0.6 else
        "positive"       if score < 0.8 else
        "very_positive"
    )
    return {
        "score": score,
        "label": label,
        "should_escalate": score < 0.3,
        "confidence": "low" if 0.4 < score < 0.6 else "high",
        "recommendation": (
            "Escalate — customer is distressed"
            if score < 0.3 else
            "Acknowledge frustration before answering"
            if score < 0.5 else
            "Proceed normally"
        ),
    }


SENTIMENT_ANALYSIS = Skill(
    name="Sentiment Analysis",
    description=(
        "Analyses the emotional tone of a customer message and returns "
        "a sentiment score, label, and escalation recommendation."
    ),
    when_to_use=(
        "EVERY incoming customer message must be scored before responding. "
        "Re-run if the customer sends a follow-up that seems more frustrated."
    ),
    inputs={
        "message": "Raw customer message text (full content, not truncated).",
    },
    outputs={
        "score": "Float 0.0–1.0. 0=very negative, 0.5=neutral, 1.0=very positive.",
        "label": "One of: very_negative | negative | neutral | positive | very_positive.",
        "should_escalate": "Boolean — True if score < 0.3.",
        "confidence": "'high' when score is far from 0.5; 'low' near neutral.",
        "recommendation": "Plain-English action for the agent.",
    },
    mcp_tool="analyse_sentiment",
    channel_notes={
        Channel.EMAIL: "Emails are often more formal; lower base score expected.",
        Channel.WHATSAPP: (
            "Short messages may score neutral even when frustrated — "
            "weight ALL_CAPS and punctuation (!!!) more heavily."
        ),
        Channel.WEB_FORM: "Form messages tend to be considered; score fairly.",
    },
    execute=_execute_sentiment_analysis,
)


# ---------------------------------------------------------------------------
# Skill 3: Escalation Decision
# ---------------------------------------------------------------------------

def _execute_escalation_decision(
    message: str,
    channel: str,
    sentiment_score: float,
    search_attempts: int = 0,
) -> dict:
    ch = Channel(channel)
    should_escalate, reason = detect_escalation(message, ch, sentiment_score)

    # Soft escalation: knowledge gap after 2 searches
    if not should_escalate and search_attempts >= 2:
        should_escalate = True
        reason = "knowledge_gap"

    urgency = (
        "critical" if reason in ("legal_threat", "security_incident") else
        "high"     if reason in ("refund_request", "abusive_language",
                                  "compliance_inquiry") else
        "normal"
    )

    return {
        "should_escalate": should_escalate,
        "reason": reason,
        "urgency": urgency,
        "message_to_customer": _escalation_ack(reason, ch) if should_escalate else "",
    }


def _escalation_ack(reason: str, channel: Channel) -> str:
    base = {
        "legal_threat":        "I've urgently escalated your case to our senior team.",
        "refund_request":      "I'm connecting you with our billing team right now.",
        "pricing_negotiation": "Our sales team will reach out to discuss your needs.",
        "abusive_language":    "I'm escalating this for specialist attention.",
        "human_requested":     "Connecting you with a live agent now.",
        "security_incident":   "Our security team has been alerted and will contact you immediately.",
        "compliance_inquiry":  "Our compliance team will respond within 24 hours.",
        "knowledge_gap":       "Let me connect you with a specialist for this question.",
        "negative_sentiment":  "I'm sorry for the frustration — escalating to our team now.",
        "bug_report":          "I've raised this with our engineering team.",
        "repeat_contact":      "I sincerely apologise — escalating for priority resolution.",
        "enterprise_priority": "Escalating to your dedicated support team now.",
    }.get(reason, "Connecting you with our specialist team.")

    if channel == Channel.WHATSAPP and len(base) > 160:
        return base[:157] + "..."
    return base


ESCALATION_DECISION = Skill(
    name="Escalation Decision",
    description=(
        "Determines whether a conversation should be escalated to a human "
        "agent, and if so, the reason code and urgency level."
    ),
    when_to_use=(
        "Run AFTER sentiment analysis and AFTER each knowledge base search attempt. "
        "Also run when customer sends a follow-up indicating dissatisfaction."
    ),
    inputs={
        "message":          "Full customer message text.",
        "channel":          "Source channel: email | whatsapp | web_form.",
        "sentiment_score":  "Score from Sentiment Analysis skill (0.0–1.0).",
        "search_attempts":  "Number of KB searches already performed (default 0).",
    },
    outputs={
        "should_escalate":       "Boolean escalation decision.",
        "reason":                "Escalation reason code (see escalation-rules.md).",
        "urgency":               "critical | high | normal.",
        "message_to_customer":   "Pre-written acknowledgement to send the customer.",
    },
    mcp_tool="escalate_to_human",
    channel_notes={
        Channel.EMAIL:     "Include full context summary for human agent.",
        Channel.WHATSAPP:  "Keep ack message under 160 chars; send as separate message.",
        Channel.WEB_FORM:  "Include ticket reference in ack message.",
    },
    execute=_execute_escalation_decision,
)


# ---------------------------------------------------------------------------
# Skill 4: Channel Adaptation
# ---------------------------------------------------------------------------

def _execute_channel_adaptation(
    response: str,
    channel: str,
    customer_name: str = "Valued Customer",
    ticket_id: str = "",
) -> dict:
    ch = Channel(channel)
    formatted = format_for_channel(response, ch, customer_name, ticket_id)
    within_limit = len(formatted) <= {
        Channel.EMAIL: 2000,
        Channel.WHATSAPP: 1600,
        Channel.WEB_FORM: 1000,
    }[ch]
    return {
        "formatted_response": formatted,
        "length": len(formatted),
        "within_limit": within_limit,
        "channel": channel,
    }


CHANNEL_ADAPTATION = Skill(
    name="Channel Adaptation",
    description=(
        "Reformats a raw agent response to match the tone, length, and "
        "structural conventions of the target channel before sending."
    ),
    when_to_use=(
        "ALWAYS invoke before calling send_response. "
        "Never send a raw response directly to the customer."
    ),
    inputs={
        "response":       "Raw response text generated by the agent.",
        "channel":        "Target channel: email | whatsapp | web_form.",
        "customer_name":  "Customer's name for personalised greeting.",
        "ticket_id":      "Ticket ID for reference footer.",
    },
    outputs={
        "formatted_response": "Channel-ready response string.",
        "length":             "Character count of formatted response.",
        "within_limit":       "Boolean — True if within channel length limit.",
        "channel":            "Echo of input channel for confirmation.",
    },
    mcp_tool="send_response",
    channel_notes={
        Channel.EMAIL: (
            "Adds 'Hi {name},' greeting, paragraph body, offer to help further, "
            "signature, and ticket reference footer. Max 500 words."
        ),
        Channel.WHATSAPP: (
            "Keeps message under 300 chars when possible. "
            "Strips markdown. Adds '📱 Reply for more help or type human.' suffix."
        ),
        Channel.WEB_FORM: (
            "Semi-formal. Adds ticket reference and support portal link. "
            "Max 300 words."
        ),
    },
    execute=_execute_channel_adaptation,
)


# ---------------------------------------------------------------------------
# Skill 5: Customer Identification
# ---------------------------------------------------------------------------

def _execute_customer_identification(
    message_metadata: dict,
) -> dict:
    """
    Resolve a unified customer_id from message metadata.
    Prototype uses email/phone as key; production queries customer_identifiers table.
    """
    email = message_metadata.get("customer_email", "").strip().lower()
    phone = message_metadata.get("customer_phone", "").strip()
    channel = message_metadata.get("channel", "web_form")

    if email:
        customer_id = email
        id_type = "email"
    elif phone:
        customer_id = phone
        id_type = "whatsapp_phone"
    else:
        customer_id = f"unknown-{channel}-{id(message_metadata)}"
        id_type = "generated"

    return {
        "customer_id": customer_id,
        "id_type": id_type,
        "channel": channel,
        "is_new_customer": True,   # prototype: always new; production checks DB
        "merged_history": [],      # production: fetched cross-channel history
        "confidence": "high" if id_type == "email" else "medium",
    }


CUSTOMER_IDENTIFICATION = Skill(
    name="Customer Identification",
    description=(
        "Resolves a unified customer identity from incoming message metadata "
        "across all channels, enabling cross-channel conversation continuity."
    ),
    when_to_use=(
        "First skill to run on ANY incoming message, before create_ticket. "
        "Ensures the same customer is recognised whether they email, "
        "WhatsApp, or use the web form."
    ),
    inputs={
        "message_metadata": (
            "Dict containing any of: customer_email, customer_phone, "
            "channel, customer_name, channel_message_id."
        ),
    },
    outputs={
        "customer_id":     "Unified identifier (email or phone).",
        "id_type":         "email | whatsapp_phone | generated.",
        "channel":         "Source channel of this message.",
        "is_new_customer": "True if no prior history found.",
        "merged_history":  "List of prior interactions across all channels.",
        "confidence":      "high | medium | low — match confidence.",
    },
    mcp_tool="get_customer_history",
    channel_notes={
        Channel.EMAIL:     "Use email address as primary key. Always available.",
        Channel.WHATSAPP:  "Use phone number (E.164 format). May differ from email.",
        Channel.WEB_FORM:  "Use email address from form submission.",
    },
    execute=_execute_customer_identification,
)


# ---------------------------------------------------------------------------
# Skills registry
# ---------------------------------------------------------------------------

SKILLS: dict[str, Skill] = {
    "knowledge_retrieval":    KNOWLEDGE_RETRIEVAL,
    "sentiment_analysis":     SENTIMENT_ANALYSIS,
    "escalation_decision":    ESCALATION_DECISION,
    "channel_adaptation":     CHANNEL_ADAPTATION,
    "customer_identification": CUSTOMER_IDENTIFICATION,
}


def run_skill(skill_name: str, **kwargs: Any) -> dict:
    """Execute a registered skill by name."""
    skill = SKILLS.get(skill_name)
    if not skill:
        raise ValueError(f"Unknown skill: '{skill_name}'. "
                         f"Available: {list(SKILLS.keys())}")
    if not skill.execute:
        raise NotImplementedError(f"Skill '{skill_name}' has no executor.")
    return skill.execute(**kwargs)


# ---------------------------------------------------------------------------
# CLI: print skill manifest
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("NovaFlow Customer Success FTE — Skills Manifest")
    print("=" * 60)

    for i, (key, skill) in enumerate(SKILLS.items(), 1):
        print(f"\n{'─'*60}")
        print(f"Skill {i}: {skill.name}")
        print(f"MCP Tool: {skill.mcp_tool}")
        print(f"When to use: {skill.when_to_use}")
        print(f"Inputs:  {list(skill.inputs.keys())}")
        print(f"Outputs: {list(skill.outputs.keys())}")

    print(f"\n{'='*60}")
    print("Quick test: Sentiment Analysis skill")
    result = run_skill("sentiment_analysis",
                       message="This is COMPLETELY broken! I'm very angry!")
    print(result)

    print("\nQuick test: Knowledge Retrieval skill")
    result = run_skill("knowledge_retrieval", query="how do I reset my password")
    print(f"Found: {result['found']} | {result['summary']}")

    print("\nQuick test: Customer Identification skill")
    result = run_skill("customer_identification", message_metadata={
        "customer_email": "user@example.com",
        "channel": "email",
        "customer_name": "Test User",
    })
    print(result)
