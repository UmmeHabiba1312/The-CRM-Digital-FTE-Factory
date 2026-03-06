# Transition Checklist: General Agent → Custom Agent

**Date**: 2026-03-06 | **From**: Phase 1 Incubation | **To**: Phase 2 Specialization

---

## 1. Discovered Requirements

All requirements found during incubation (discovery-log.md):

- [x] R01: Normalise incoming messages from all 3 channels into a unified schema
- [x] R02: Create a ticket (with channel tag) before ANY other action
- [x] R03: Retrieve cross-channel customer history on every message
- [x] R04: Analyse sentiment on every inbound message (score 0.0–1.0)
- [x] R05: 11 escalation rules must trigger before KB search (hard) or after (soft)
- [x] R06: WhatsApp single-word triggers ("human", "agent") → immediate escalation
- [x] R07: Response length limits: Email 500 words, WhatsApp 300 chars, Web 300 words
- [x] R08: Channel-appropriate formatting (greeting/signature for email; emoji CTA for WA)
- [x] R09: Cross-channel customer identity via `customer_identifiers` table
- [x] R10: Vector search (pgvector) for KB — keyword matching insufficient
- [x] R11: Empty / unclear messages → ask for clarification, never crash
- [x] R12: Non-English messages → respond in English with language acknowledgement
- [x] R13: Very long multi-issue messages → triage top issue; acknowledge rest
- [x] R14: Bug reports → soft escalate to engineering (do not attempt to fix)
- [x] R15: Positive feedback → thank graciously; offer further help
- [x] R16: Kafka required — blocking sync processing fails at scale
- [x] R17: All secrets via env vars / K8s Secrets — never hardcoded
- [x] R18: Twilio webhook signature validation (403 on failure)
- [x] R19: DLQ topic for failed message processing — no silent drops
- [x] R20: Tool calls stored in `messages.tool_calls` JSONB for observability

---

## 2. Working System Prompt (Extracted from Incubation)

```
You are a Customer Success agent for NovaFlow SaaS.

## Your Purpose
Handle routine customer support queries with speed, accuracy, and empathy
across Email, WhatsApp, and Web Form.

## Channel Awareness
- Email:     Formal, detailed. Greeting + numbered steps + signature.
- WhatsApp:  Concise (≤300 chars). No markdown. Emoji CTA at end.
- Web Form:  Semi-formal. Ticket reference in footer.

## Required Workflow (ALWAYS in this order)
1. create_ticket        — FIRST, always, with channel tag
2. get_customer_history — check ALL channels for prior context
3. analyse_sentiment    — score before responding
4. escalation check     — hard triggers before KB search
5. search_knowledge_base — max 2 attempts
6. send_response        — LAST, always, never skip

## Hard Constraints
- NEVER discuss pricing → escalate: pricing_negotiation
- NEVER process refunds → escalate: refund_request
- NEVER discuss legal matters → escalate: legal_threat
- NEVER share internal system details
- NEVER respond without send_response tool
- NEVER exceed: Email=500 words, WhatsApp=1600 chars, Web=300 words

## Escalation Triggers
- "lawyer", "legal", "sue", "attorney" → legal_threat (critical)
- "refund", "chargeback", "money back" → refund_request (high)
- Profanity or sentiment < 0.25 → abusive_language (high)
- "human", "live agent", "manager" → human_requested (normal)
- WhatsApp: "human" alone → human_requested (normal)
- "hacked", "unauthorized" → security_incident (critical)
- "GDPR", "HIPAA", "SOC 2", "BAA" → compliance_inquiry (high)
- No KB result after 2 searches → knowledge_gap (normal)
- Sentiment < 0.3 → negative_sentiment (high)
```

---

## 3. Edge Cases → Test Cases

| # | Edge Case | Channel | Expected Behaviour | Test Needed |
|---|-----------|---------|-------------------|-------------|
| 1 | Empty message | All | Ask for clarification | ✅ |
| 2 | Pricing question | All | Escalate pricing_negotiation | ✅ |
| 3 | "I'll sue you" | Email | Escalate legal_threat critical | ✅ |
| 4 | Angry ALL CAPS | Email | Escalate negative_sentiment | ✅ |
| 5 | "human" alone | WhatsApp | Escalate human_requested | ✅ |
| 6 | "???" unclear | WhatsApp | Ask for clarification | ✅ |
| 7 | GDPR deletion | Web Form | Escalate compliance_inquiry | ✅ |
| 8 | No KB results | Any | Escalate knowledge_gap | ✅ |
| 9 | Multi-issue email | Email | Address top; acknowledge rest | ✅ |
| 10 | Cross-channel follow-up | Email | Load WhatsApp history | ✅ |
| 11 | Password reset | Email | Resolve with steps | ✅ |
| 12 | Positive feedback | WhatsApp | Thank + offer help | ✅ |
| 13 | Tool order violation | Any | create_ticket must be first | ✅ |
| 14 | WA response > 300 chars | WhatsApp | Truncate + offer more | ✅ |

---

## 4. Response Patterns by Channel

| Channel | Style | Key Rules |
|---------|-------|-----------|
| Email | Formal | "Hi {name}," + steps + "Best regards, NovaFlow Support" |
| WhatsApp | Conversational | Short + 1 emoji max + "type 'human' for live support" |
| Web Form | Semi-formal | Answer + ticket ref + support portal link |

---

## 5. Escalation Rules (Finalized — 11 rules)

| Trigger Type | Rule | Reason Code | Urgency |
|-------------|------|-------------|---------|
| Hard | legal keywords | legal_threat | critical |
| Hard | refund keywords | refund_request | high |
| Hard | pricing negotiation | pricing_negotiation | normal |
| Hard | profanity / sentiment < 0.25 | abusive_language | high |
| Hard | human request keywords | human_requested | normal |
| Hard | WA "human" alone | human_requested | normal |
| Hard | security incident keywords | security_incident | critical |
| Hard | compliance keywords | compliance_inquiry | high |
| Soft | no KB after 2 searches | knowledge_gap | normal |
| Soft | sentiment < 0.3 mid-conv | negative_sentiment | high |
| Soft | bug report | bug_report | high |

---

## 6. Performance Baseline

| Metric | Prototype | Production Target |
|--------|-----------|-------------------|
| Response time | <50ms (no LLM) | <3s (GPT-4o) |
| Accuracy | ~60% (rule-based) | >85% (pgvector) |
| Escalation rate | 37% | <25% |
| Cross-channel ID | 70% | >95% |

---

## Transition Steps Checklist

### From Incubation (All Complete ✅)
- [x] Working prototype (multi-channel aware)
- [x] 24 edge cases documented
- [x] Working system prompt extracted
- [x] MCP tools defined and tested
- [x] Channel-specific response patterns identified
- [x] Escalation rules finalized (11 rules)
- [x] Performance baseline measured

### Production Build Steps
- [x] Production folder structure created (`production/`)
- [ ] Prompts extracted → `production/agent/prompts.py`
- [ ] MCP tools → `@function_tool` with Pydantic validation
- [ ] Error handling on all tools
- [ ] Transition test suite written + passing
- [ ] PostgreSQL schema designed
- [ ] Kafka topics defined
- [ ] Channel handlers outlined
- [ ] K8s resource requirements estimated
- [ ] API endpoints listed
