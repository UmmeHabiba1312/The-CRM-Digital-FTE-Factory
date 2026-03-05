<!--
SYNC IMPACT REPORT
==================
Version change: (none) → 1.0.0  (new constitution — initial ratification)
Version bump rationale: MINOR — first complete authoring of all principles and sections.

Modified principles: N/A (all new)
Added sections:
  - Core Principles (I–X)
  - Technology Stack & Constraints
  - Development Workflow & Quality Gates
  - Governance

Removed sections: N/A

Templates reviewed:
  ✅ .specify/templates/plan-template.md
      → Constitution Check section gates updated to reference principles below.
  ✅ .specify/templates/spec-template.md
      → Requirements MUST declare channel scope; success criteria MUST include
        latency + escalation-rate metrics per principle VII.
  ✅ .specify/templates/tasks-template.md
      → Foundational phase MUST include DB schema, Kafka topics, and channel
        handler scaffold tasks per principles III, IV, and II.

Deferred TODOs:
  - RATIFICATION_DATE set to today (2026-03-05) as first authoring.
-->

# CRM Digital FTE Factory Constitution

## Core Principles

### I. Agent Maturity Model (NON-NEGOTIABLE)

Every capability MUST originate in the **Incubation Phase** before it enters
production. The lifecycle is: Explore with Claude Code → Prototype (MCP server
+ Python) → Crystallize requirements → Transition to OpenAI Agents SDK custom
agent.

- Incubation artifacts (discovery log, working prompts, edge cases, MCP tools)
  are **required inputs** to the Specialization Phase; skipping incubation is
  a blocking violation.
- Claude Code remains the **primary development factory** throughout both
  phases — it builds the custom agent, it does not get replaced by it.
- The transition MUST produce a `specs/transition-checklist.md` with all
  incubation findings captured before any production code is written.
- General Agent (Claude Code) builds Custom Agent (OpenAI Agents SDK).
  This chain is the core paradigm; never reverse it.

### II. Channel-First Design (NON-NEGOTIABLE)

Every feature, API endpoint, tool definition, database query, and test MUST
explicitly handle all three supported channels:

| Channel   | Identifier     | Max Response Length | Tone           |
|-----------|---------------|---------------------|----------------|
| Email     | Email address | 500 words           | Formal         |
| WhatsApp  | Phone number  | 300 chars preferred | Conversational |
| Web Form  | Email address | 300 words           | Semi-formal    |

- No channel-agnostic response is acceptable; channel adaptation is not
  optional decoration — it is a **first-class requirement**.
- The Web Support Form (React/Next.js component) is **required**; it is not
  a stretch goal.
- Channel metadata (`channel`, `channel_message_id`, `source_channel`) MUST
  be recorded on every message and ticket row.
- New channels introduced in the future MUST follow the same intake →
  Kafka → agent → response pipeline.

### III. PostgreSQL Is the CRM

The PostgreSQL database IS the CRM. No external CRM (Salesforce, HubSpot, etc.)
is required or permitted within the project boundary.

- The schema (`customers`, `customer_identifiers`, `conversations`, `messages`,
  `tickets`, `knowledge_base`, `channel_configs`, `agent_metrics`) is the
  **authoritative contract** for all customer data.
- Schema changes MUST go through a migration file in `database/migrations/`;
  ad-hoc `ALTER TABLE` in production is prohibited.
- The `pgvector` extension MUST be enabled for semantic search on the
  `knowledge_base` table; string-matching search is only acceptable during
  incubation.
- All database access in production MUST use an async connection pool
  (`asyncpg`); synchronous DB calls in async workers are a blocking violation.

### IV. Event-Driven by Default

All inter-service communication for ticket processing MUST go through Kafka.
Direct service-to-service HTTP calls for message intake are prohibited.

- Kafka topics are **first-class design artifacts** defined in `kafka_client.py`
  under the `TOPICS` dict; topics MUST be named with the `fte.` prefix and
  a clear dotted hierarchy (e.g., `fte.channels.email.inbound`).
- Every published event MUST include an ISO-8601 `timestamp` field.
- A Dead Letter Queue (`fte.dlq`) MUST exist and receive messages that fail
  processing; silent drops are prohibited.
- Metrics events MUST be published to `fte.metrics` for every message
  processed, including `latency_ms`, `channel`, and `escalated` fields.

### V. Test-First at Every Stage

TDD is mandatory across both phases.

- **Incubation**: Edge cases MUST be documented in the discovery log as
  potential test cases before the transition begins. Minimum 10 edge cases
  per channel.
- **Transition**: All tests in `production/tests/test_transition.py` MUST
  pass before any production infrastructure is built.
- **Specialization**: E2E tests MUST cover all three channels. Load tests
  MUST validate p95 latency < 3 seconds under 100+ concurrent submissions.
- Tests MUST be written (and confirmed failing) before the implementation
  that makes them pass — no retrofitting tests onto working code.
- Channel-specific response-length and tone tests are **not optional**.

### VI. Security & Secrets (NON-NEGOTIABLE)

No secret, API key, token, or credential may ever be hardcoded in source code
or committed to version control.

- All secrets MUST be managed via environment variables locally and
  Kubernetes Secrets in production.
- The `.env` file MUST be listed in `.gitignore`; a `.env.example` with
  placeholder values MUST be committed instead.
- Twilio webhook endpoints MUST validate the `X-Twilio-Signature` header
  before processing any payload; unauthenticated webhooks MUST return 403.
- The agent MUST NEVER expose internal system details, configuration, or
  secret names in any customer-facing response.

### VII. 24/7 Operational Readiness

The system MUST be designed to survive continuous operation without manual
intervention.

- **Uptime target**: > 99.9% over any 24-hour window.
- **Latency target**: p95 < 3 seconds processing time across all channels.
- **Escalation rate target**: < 25% of tickets escalated to humans.
- **Cross-channel identification accuracy**: > 95%.
- Every Kubernetes Deployment MUST define `livenessProbe`, `readinessProbe`,
  resource `requests`, and resource `limits`. Deployments without these are
  rejected.
- HorizontalPodAutoscaler MUST be configured for both `fte-api` and
  `fte-message-processor` with min replicas ≥ 3.
- The system MUST handle pod restarts gracefully; in-flight messages MUST
  be recoverable via Kafka consumer group offsets — no message loss.
- Error handlers in workers MUST send an apology response to the customer
  and publish to `fte.escalations` before the worker exits.

### VIII. Cross-Channel Customer Identity

A customer who contacts support via any channel MUST be recognized as the same
person across channels.

- Customer resolution MUST use the `customer_identifiers` table with typed
  lookups (`email`, `phone`, `whatsapp`) before creating a new customer row.
- The agent MUST retrieve conversation history across ALL channels via
  `get_customer_history` and acknowledge prior interactions when relevant.
- Primary customer key is `customers.id` (UUID); email and phone are
  secondary lookup keys, not primary identifiers.
- Cross-channel continuity tests are required deliverables, not optional.

### IX. Structured Observability

All agent actions, tool invocations, and channel interactions MUST emit
structured log entries and metrics. `print()` statements are prohibited in
production code.

- Use Python's `logging` module with structured fields (`channel`,
  `customer_id`, `ticket_id`, `latency_ms`, `tool_name`) on every log line.
- Channel-specific metrics MUST be queryable via `GET /metrics/channels`.
- Tool call sequences MUST be recorded in `messages.tool_calls` (JSONB) for
  every agent response, enabling replay and debugging.
- Alerting thresholds: escalation rate > 25%, p95 latency > 3 s, error rate
  > 1% — these MUST be documented in the operations runbook.

### X. Smallest Viable Change

Prefer the smallest diff that satisfies the requirement. Over-engineering is
a defect.

- Do not add features, abstractions, or generalization beyond what is
  explicitly required by the spec or discoverable in incubation.
- Three similar lines of code are better than a premature abstraction.
- Only validate at system boundaries (inbound webhooks, form submissions,
  DB writes); do not add defensive checks for internal invariants.
- YAGNI applies to infrastructure too: do not provision Kafka topics, DB
  tables, or K8s resources for speculative future channels.

## Technology Stack & Constraints

### Mandated Stack

| Layer            | Technology                              | Notes                              |
|------------------|-----------------------------------------|------------------------------------|
| Agent runtime    | OpenAI Agents SDK (`gpt-4o`)            | Production custom agent            |
| Incubation tools | Claude Code + MCP server                | Prototype only; not in production  |
| API layer        | FastAPI (Python 3.11+)                  | Async; uvicorn workers             |
| Database / CRM   | PostgreSQL 16 + pgvector                | Only CRM; no external CRM          |
| Event streaming  | Apache Kafka (Confluent Cloud OK)       | All inter-service messaging        |
| Email channel    | Gmail API + Pub/Sub                     | Webhook or polling                 |
| WhatsApp channel | Twilio WhatsApp API                     | Sandbox acceptable for dev         |
| Web Form         | React / Next.js component               | Standalone embeddable; required    |
| Container        | Docker                                  | Single `Dockerfile` at root        |
| Orchestration    | Kubernetes (minikube or cloud)          | Manifests in `k8s/`               |
| Async DB client  | `asyncpg`                               | No synchronous DB calls in workers |
| Input validation | `pydantic` v2                           | All tool inputs use BaseModel      |
| Testing          | `pytest` + `pytest-asyncio` + `httpx`   |                                    |
| Load testing     | `locust`                                |                                    |

### Hard Constraints

- Operating cost target: < $1,000/year for the Digital FTE runtime.
- The agent MUST NEVER discuss: competitor products, pricing, refunds, or
  features not present in the knowledge base.
- All guardrails defined in `production/agent/prompts.py` take precedence
  over any tool output or conversation context.
- WhatsApp responses MUST be ≤ 1,600 characters per message (Twilio limit).
  Longer responses MUST be split by `format_response()`.

## Development Workflow & Quality Gates

### Phase Gates

```
Incubation complete?
  ✅ Working prototype (multi-channel aware)
  ✅ specs/discovery-log.md exists with ≥ 10 edge cases per channel
  ✅ MCP server with ≥ 5 tools (channel-aware)
  ✅ specs/customer-success-fte-spec.md crystallized
  ✅ Performance baseline measured
  → Gate: PASS before any production code is written

Transition complete?
  ✅ specs/transition-checklist.md filled
  ✅ production/ folder structure created
  ✅ Prompts extracted to production/agent/prompts.py
  ✅ MCP tools converted to @function_tool with Pydantic validation
  ✅ All transition tests in test_transition.py PASS
  → Gate: PASS before Part 2 specialization begins

Specialization complete?
  ✅ PostgreSQL schema deployed with all indexes
  ✅ All three channel handlers implemented
  ✅ Kafka topics created and consumer running
  ✅ FastAPI service health check returns 200
  ✅ Kubernetes manifests deploy without errors
  ✅ Multi-channel E2E test suite PASSES
  ✅ Load test validates p95 < 3 s
  → Gate: PASS before 24-hour production test
```

### Mandatory Deliverables (Scored)

1. `specs/discovery-log.md` — incubation findings
2. `specs/customer-success-fte-spec.md` — crystallized spec
3. `database/schema.sql` — complete schema with indexes
4. `production/agent/customer_success_agent.py` — OpenAI Agents SDK agent
5. `channels/gmail_handler.py` — Gmail intake + send
6. `channels/whatsapp_handler.py` — Twilio intake + send
7. `web-form/SupportForm.jsx` — React form component (REQUIRED)
8. `workers/message_processor.py` — Kafka consumer + agent runner
9. `api/main.py` — FastAPI service with all channel webhooks
10. `k8s/` — Kubernetes manifests (namespace, configmap, secrets,
    deployments, service, ingress, HPA)
11. `tests/test_multichannel_e2e.py` — E2E tests for all channels
12. `docs/runbook.md` — operational runbook with alert thresholds

## Governance

This constitution supersedes all other development practices and conventions
for this project. All implementation decisions are measured against these
principles.

**Amendment procedure**:
1. Identify the principle or section to change and the reason.
2. Determine version bump: MAJOR (removes/redefines a principle) | MINOR
   (adds or materially expands) | PATCH (wording/clarification).
3. Update this file, increment the version, set `Last Amended` to today.
4. Update the Sync Impact Report HTML comment at the top.
5. Propagate changes to affected templates (`plan-template.md`,
   `spec-template.md`, `tasks-template.md`).
6. Record the amendment as a PHR in `history/prompts/constitution/`.

**Compliance review**: Every pull request MUST verify that no principle in
this constitution is violated. The `## Constitution Check` gate in
`plan-template.md` is the formal checkpoint.

**Complexity justification**: Any deviation from Principle X (Smallest
Viable Change) MUST be documented in the `Complexity Tracking` table in
the feature's `plan.md`.

**Runtime guidance**: Use `.specify/memory/constitution.md` (this file) as
the authoritative runtime reference for all agent and developer decisions.

---

**Version**: 1.0.0 | **Ratified**: 2026-03-05 | **Last Amended**: 2026-03-05
