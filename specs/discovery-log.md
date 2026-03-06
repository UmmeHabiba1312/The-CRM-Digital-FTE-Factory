# Discovery Log — NovaFlow Customer Success FTE

**Phase**: Incubation (Exercise 1.1)
**Date**: 2026-03-05
**Analyst**: Claude Code (Agent Factory)

---

## 1. Ticket Pattern Analysis (from sample-tickets.json)

### Volume by Channel
| Channel   | Tickets | % of Total |
|-----------|---------|------------|
| Email     | 21      | 40%        |
| WhatsApp  | 17      | 33%        |
| Web Form  | 14      | 27%        |

### Volume by Category
| Category            | Count | Key Channels         |
|---------------------|-------|----------------------|
| Integration issues  | 10    | Email, WhatsApp      |
| Billing/payments    | 7     | WhatsApp, Web Form   |
| How-to questions    | 7     | Web Form, Email      |
| Bug reports         | 6     | Email, Web Form      |
| Compliance/legal    | 6     | Email, Web Form      |
| Feedback (positive) | 3     | WhatsApp             |
| Security            | 2     | WhatsApp, Email      |
| Onboarding          | 2     | Email                |
| Unclear/edge cases  | 7     | All channels         |

### Escalation Rate from Sample Data
- **Hard escalations** (legal, refund, pricing, compliance, security): 14/52 = **27%**
- **Soft escalations** (bugs, repeat contact, enterprise): 5/52 = **10%**
- **Self-serviceable**: 33/52 = **63%**

---

## 2. Channel-Specific Patterns Discovered

### Email Channel Patterns
- Messages are **longer** (avg 80–250 words) and more detailed
- Customers provide context, steps they tried, plan details
- Formal tone expected in both directions
- Customers often include subject lines that reveal the category
- **Follow-up emails** reference previous tickets or WhatsApp conversations
  → Cross-channel continuity is critical (T052 discovered this)
- Non-English emails exist (T029 — Spanish) → language detection needed or
  respond in English with apology
- Thread IDs matter: email replies must attach to the original thread

### WhatsApp Channel Patterns
- Messages are **very short** (avg 3–15 words)
- Highly conversational, abbreviations, no punctuation
- Single-word triggers: "human", "help", "???" need special handling
- International phone numbers (T011 Ireland, T019 South Africa, T035 Japan)
- Non-English messages (T041 — Portuguese "quero cancelar meu plano")
- Positive feedback delivered via WhatsApp more than other channels
- Max response: 300 chars preferred, 1600 chars absolute Twilio limit
- WhatsApp customers expect fast acknowledgement (< 60 seconds)

### Web Form Patterns
- Structured submissions with subject + category + priority
- Customers are more patient (async expectation)
- Longer, more thoughtful messages than WhatsApp
- T036 (very long multi-issue message): agent must triage and prioritise
- Response goes to email (not back to form) — dual channel interaction
- Form validation catches bad data before agent sees it

---

## 3. Edge Cases Discovered

### Email Edge Cases
| # | Edge Case | Handling Strategy |
|---|-----------|-------------------|
| E1 | Empty message body (T027) | Ask for clarification — don't crash |
| E2 | Non-English message — Spanish (T029) | Respond in English with apology note |
| E3 | Very long message with 5+ issues (T036) | Triage top issue; acknowledge others |
| E4 | Follow-up referencing WhatsApp (T052) | Cross-channel history lookup required |
| E5 | Positive feedback only (no question) | Thank + offer further help |
| E6 | Re: Re: Re: old thread (T037) | Check if already resolved; confirm |
| E7 | Legal threat + data loss claim (T043) | Hard escalate immediately, no KB search |
| E8 | Enterprise compliance audit (T033) | Escalate; do not attempt to answer |

### WhatsApp Edge Cases
| # | Edge Case | Handling Strategy |
|---|-----------|-------------------|
| W1 | Single word "human" (T014) | Immediate escalation, no KB search |
| W2 | "???" unclear message (T028) | Ask: "Could you describe your issue?" |
| W3 | Empty / blank message | Ask for clarification |
| W4 | Non-English — Portuguese (T041) | Respond in English; note language barrier |
| W5 | "Account hacked" security (T016) | Hard escalate, security urgency |
| W6 | Positive feedback (T044, T050) | Thank graciously, offer further help |
| W7 | Price/refund question (T005) | Hard escalate, do not discuss pricing |
| W8 | International phone numbers | Normalise to E.164; use as customer_id |

### Web Form Edge Cases
| # | Edge Case | Handling Strategy |
|---|-----------|-------------------|
| F1 | Test submission (T039) | Respond normally; don't block tests |
| F2 | Multi-issue message (T036) | Address top issue; list others acknowledged |
| F3 | GDPR deletion request (T023) | Hard escalate — legal/compliance |
| F4 | HIPAA BAA request (T045) | Hard escalate — compliance_inquiry |
| F5 | Nonprofit discount request (T042) | Escalate — pricing_negotiation |
| F6 | Enterprise SSO issue (T051) | Escalate — enterprise_priority |
| F7 | Feature request (T024) | Acknowledge; log; do not promise roadmap |
| F8 | Invoice copy needed (T048) | Direct to Settings → Billing; resolve |

---

## 4. Cross-Channel Patterns

- **T052** (Laura Kim): Emailed to follow up on a WhatsApp message — same issue,
  different channels. Without cross-channel history, agent would treat as new.
  **Requirement confirmed**: unified `customer_identifiers` table essential.

- **Customer phone ≠ customer email**: WhatsApp customers may have no email on
  file until they submit a web form or email ticket.
  **Requirement confirmed**: customer resolution must support partial identity
  (phone-only, email-only, or both).

- Sentiment can change between channels: a calm email followed by an angry
  WhatsApp means context from prior channel must be loaded.

---

## 5. Response Style Discoveries

### What worked well (Email)
- Acknowledging frustration BEFORE solving the problem → higher CSAT
- Numbered steps for how-to questions → clear and scannable
- "Let me know if you have any other questions" close → reduces follow-ups

### What worked well (WhatsApp)
- Short 2–3 line responses → no truncation, reads naturally
- Emoji used once (✅ or 📱) → friendly but professional
- Ending with "type 'human' for live support" → clear escape hatch

### What worked well (Web Form)
- Structured response with headers for multi-step answers
- Ticket reference in footer → customer can track status
- Estimated response time in confirmation → sets expectations

---

## 6. Performance Baseline (Prototype)

| Metric                     | Prototype Result      | Production Target |
|----------------------------|-----------------------|-------------------|
| Avg response time          | < 50ms (no LLM call)  | < 3s (with GPT-4o)|
| Accuracy on 52-ticket set  | ~60% (rule-based KB)  | > 85%             |
| Escalation rate            | 37% (over-escalates)  | < 25%             |
| Cross-channel ID accuracy  | 70% (email-only)      | > 95%             |
| Empty message handling     | ✅ handled            | ✅ required        |
| Non-English handling       | Partial (no detection)| Detect + respond  |

**Root cause of over-escalation**: Rule-based keyword matching triggers on
partial matches (e.g., "legally" triggers `legal_threat`). Production must
use LLM-based intent classification.

---

## 7. Architectural Decisions Surfaced

1. **Knowledge base must use vector search in production** — keyword matching
   misses semantically similar queries (e.g., "can't log in" misses "password
   reset" section).

2. **Kafka is required** — prototype processes messages synchronously. Under
   100+ concurrent messages, blocking is inevitable. Kafka decouples intake
   from processing.

3. **Customer identity resolution must be DB-driven** — in-memory dict is
   insufficient for cross-channel matching (phone → email linking).

4. **System prompt constraints must be explicit** — LLM without hard constraints
   will attempt to answer pricing/legal questions. Guardrails must be
   non-negotiable strings in the system prompt, not soft suggestions.

5. **Channel formatters must be tested independently** — WhatsApp truncation
   at 1600 chars must be a tested function, not an afterthought.

---

## 8. Escalation Rules Validated Against Sample Data

| Rule                             | Sample Evidence        | Validated? |
|----------------------------------|------------------------|------------|
| Legal keywords → escalate        | T004, T043             | ✅         |
| Refund request → escalate        | T005                   | ✅         |
| Security incident → escalate     | T016                   | ✅         |
| Compliance inquiry → escalate    | T012, T023, T033, T045 | ✅         |
| WhatsApp "human" → escalate      | T014                   | ✅         |
| Pricing negotiation → escalate   | T030, T042             | ✅         |
| Sentiment < 0.25 → escalate      | T004, T043             | ✅         |
| Repeat contact → escalate        | T021                   | ✅         |
| Bug report → soft escalate       | T031, T034             | ✅         |
| Enterprise priority → escalate   | T051                   | ✅         |
| No KB results → soft escalate    | Compliance tickets     | ✅         |

All 11 escalation rules validated against the sample ticket set.
