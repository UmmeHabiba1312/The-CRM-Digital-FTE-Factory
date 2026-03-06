# Escalation Rules — NovaFlow Customer Success FTE

## Hard Escalation Triggers (IMMEDIATE — no agent response first)

These conditions MUST trigger escalation before the agent sends any reply.

| Trigger | Detection Method | Escalation Reason Code |
|---------|-----------------|------------------------|
| Customer mentions "lawyer", "legal", "sue", "attorney", "litigation" | Keyword match | `legal_threat` |
| Customer mentions "refund", "money back", "chargeback", "dispute" | Keyword match | `refund_request` |
| Pricing negotiation ("can you do a deal", "discount", "cheaper", "lower price") | Keyword match | `pricing_negotiation` |
| Customer uses profanity or aggressive language | Sentiment < 0.25 OR keyword | `abusive_language` |
| Customer explicitly says "speak to a human", "real person", "live agent", "manager" | Keyword match | `human_requested` |
| WhatsApp: customer sends "human", "agent", "representative", "help" alone | Exact match | `human_requested` |
| Data breach suspicion ("my account was hacked", "unauthorized access", "someone logged in") | Keyword match | `security_incident` |
| Compliance/regulatory question ("GDPR", "HIPAA", "SOC 2 audit", "data deletion request") | Keyword match | `compliance_inquiry` |

## Soft Escalation Triggers (Escalate after 1 failed attempt)

These conditions trigger escalation if the agent cannot resolve after one try.

| Trigger | Condition | Escalation Reason Code |
|---------|-----------|------------------------|
| Knowledge base miss | No relevant docs found after 2 searches | `knowledge_gap` |
| Repeated contact | Same issue raised 3+ times by same customer | `repeat_contact` |
| Sentiment degradation | Sentiment drops below 0.3 during conversation | `negative_sentiment` |
| Bug report | Customer describes reproducible product bug | `bug_report` |
| Enterprise customer | Customer is on Enterprise plan | `enterprise_priority` |
| SLA breach risk | Growth/Business customer, no response in 20+ hours | `sla_risk` |

## Escalation Procedure

1. Agent MUST call `escalate_to_human(ticket_id, reason, urgency)` tool
2. Urgency levels:
   - `critical`: Legal, security, enterprise + SLA breach
   - `high`: Refund, abuse, compliance
   - `normal`: Knowledge gap, repeat contact, negative sentiment
3. Agent MUST acknowledge the customer AFTER escalating:
   - Email: "I've escalated your case to our specialist team. You'll hear back within [SLA] hours."
   - WhatsApp: "Connecting you to our team now. Ref: [ticket_id]"
   - Web Form: "Your case has been escalated. We'll email you shortly."
4. Do NOT attempt to resolve the issue after escalating — hand off completely.

## SLA by Plan (for escalation urgency calculation)

| Plan       | First Response SLA | Escalation SLA |
|------------|-------------------|----------------|
| Starter    | 72 hours          | 48 hours       |
| Growth     | 24 hours          | 12 hours       |
| Business   | 4 hours           | 2 hours        |
| Enterprise | 1 hour            | 30 minutes     |

## Out of Scope (Always Escalate — Never Attempt)

- Pricing changes or custom deals
- Refunds or credits
- Contract modifications
- Legal or compliance attestations
- Access to another customer's data
- Promises about future features
- Competitor comparisons
