---
id: "001"
title: "CRM Digital FTE Factory Constitution"
stage: constitution
date: 2026-03-05
surface: agent
model: claude-sonnet-4-6
feature: none
branch: master
user: FC
command: "analyze the project and write constitution"
labels: ["constitution","agent-maturity-model","channel-first","crm","kafka","kubernetes","openai-agents-sdk"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - .specify/memory/constitution.md
  - .specify/templates/plan-template.md
  - history/prompts/constitution/001-crm-fte-factory-constitution.constitution.prompt.md
tests:
  - N/A (constitution authoring — no tests run)
---

## Prompt

analyze the project and write constitution of this [full hackathon 5 brief provided — CRM Digital FTE
Factory, 48-72 hour hackathon, build a 24/7 Customer Success AI employee using Agent Maturity Model:
Incubation Phase (Claude Code + MCP prototype) → Specialization Phase (OpenAI Agents SDK + FastAPI +
PostgreSQL + Kafka + Kubernetes). Multi-channel: Gmail, WhatsApp, Web Form. PostgreSQL as CRM.
Target cost < $1,000/year vs $75,000/year human FTE.]

## Response snapshot

Authored the initial constitution (v1.0.0) at `.specify/memory/constitution.md` with 10 principles:

I.   Agent Maturity Model (NON-NEGOTIABLE) — Incubation before production; Claude Code as factory.
II.  Channel-First Design (NON-NEGOTIABLE) — All three channels explicit in every feature.
III. PostgreSQL Is the CRM — No external CRM; schema is the contract; asyncpg required.
IV.  Event-Driven by Default — Kafka for all ticket intake; DLQ mandatory; no silent drops.
V.   Test-First at Every Stage — TDD across incubation, transition, and specialization.
VI.  Security & Secrets (NON-NEGOTIABLE) — No hardcoded credentials; Twilio sig validation.
VII. 24/7 Operational Readiness — K8s probes + HPA; uptime > 99.9%; p95 < 3 s.
VIII. Cross-Channel Customer Identity — customer_identifiers table; history across channels.
IX.  Structured Observability — No print(); structured logs; metrics endpoint.
X.   Smallest Viable Change — YAGNI; no speculative features or infrastructure.

Also added Technology Stack & Constraints table, mandatory deliverables list, phase gates, and
governance amendment procedure. Updated `plan-template.md` Constitution Check with 10 explicit
checkboxes mapping to the principles.

## Outcome

- ✅ Impact: Project has an authoritative constitution governing all development decisions for
  Hackathon 5. Both incubation and specialization phases now have clear gate criteria.
- 🧪 Tests: No tests (constitution authoring).
- 📁 Files: .specify/memory/constitution.md (new v1.0.0), .specify/templates/plan-template.md (updated)
- 🔁 Next prompts: `/sp.specify` for customer-success-fte feature spec, then `/sp.plan`, `/sp.tasks`
- 🧠 Reflection: Constitution covers all 10 scoring rubric dimensions from the hackathon brief.
  Phase gates map directly to the deliverables checklist. Stack table eliminates ambiguity.

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): Run `/sp.specify` with customer-success-fte
  feature description to begin formal spec authoring.
