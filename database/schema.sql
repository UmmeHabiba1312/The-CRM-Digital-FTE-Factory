-- =============================================================================
-- NOVAFLOW CUSTOMER SUCCESS FTE — CRM / TICKET MANAGEMENT SYSTEM
-- =============================================================================
-- PostgreSQL 16 + pgvector
-- This schema IS the CRM. No external CRM required.
-- Run: psql -d fte_db -f schema.sql
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- =============================================================================
-- CUSTOMERS — unified identity across all channels
-- =============================================================================
CREATE TABLE customers (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email        VARCHAR(255) UNIQUE,
    phone        VARCHAR(50),
    name         VARCHAR(255),
    plan         VARCHAR(50),          -- starter | growth | business | enterprise
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata     JSONB NOT NULL DEFAULT '{}'
);

-- =============================================================================
-- CUSTOMER IDENTIFIERS — cross-channel matching
-- =============================================================================
CREATE TABLE customer_identifiers (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id      UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    identifier_type  VARCHAR(50) NOT NULL,   -- email | phone | whatsapp
    identifier_value VARCHAR(255) NOT NULL,
    verified         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (identifier_type, identifier_value)
);

-- =============================================================================
-- CONVERSATIONS — one per customer session (24h window)
-- =============================================================================
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    initial_channel VARCHAR(50) NOT NULL,    -- email | whatsapp | web_form
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    status          VARCHAR(50) NOT NULL DEFAULT 'active',  -- active | resolved | escalated | closed
    sentiment_score DECIMAL(4,3),            -- final sentiment at close
    resolution_type VARCHAR(50),             -- resolved | escalated | abandoned
    escalated_to    VARCHAR(255),            -- human agent identifier
    metadata        JSONB NOT NULL DEFAULT '{}'
);

-- =============================================================================
-- MESSAGES — every inbound and outbound message with channel tracking
-- =============================================================================
CREATE TABLE messages (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id    UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    channel            VARCHAR(50) NOT NULL,     -- email | whatsapp | web_form
    direction          VARCHAR(20) NOT NULL,     -- inbound | outbound
    role               VARCHAR(20) NOT NULL,     -- customer | agent | system
    content            TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tokens_used        INTEGER,
    latency_ms         INTEGER,
    tool_calls         JSONB NOT NULL DEFAULT '[]',
    channel_message_id VARCHAR(255),             -- Gmail ID | Twilio SID | form UUID
    delivery_status    VARCHAR(50) NOT NULL DEFAULT 'pending'  -- pending | sent | delivered | failed
);

-- =============================================================================
-- TICKETS — support ticket lifecycle
-- =============================================================================
CREATE TABLE tickets (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID REFERENCES conversations(id) ON DELETE SET NULL,
    customer_id      UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    source_channel   VARCHAR(50) NOT NULL,
    subject          VARCHAR(500),
    category         VARCHAR(100),
    priority         VARCHAR(20) NOT NULL DEFAULT 'medium',  -- low | medium | high | critical
    status           VARCHAR(50) NOT NULL DEFAULT 'open',    -- open | processing | resolved | escalated
    escalation_reason VARCHAR(100),
    escalation_urgency VARCHAR(20),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at      TIMESTAMPTZ,
    resolution_notes TEXT
);

-- =============================================================================
-- KNOWLEDGE BASE — product docs with vector embeddings
-- =============================================================================
CREATE TABLE knowledge_base (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title      VARCHAR(500) NOT NULL,
    content    TEXT NOT NULL,
    category   VARCHAR(100),
    embedding  VECTOR(1536),           -- OpenAI text-embedding-3-small
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- CHANNEL CONFIGS — per-channel settings
-- =============================================================================
CREATE TABLE channel_configs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel              VARCHAR(50) UNIQUE NOT NULL,
    enabled              BOOLEAN NOT NULL DEFAULT TRUE,
    config               JSONB NOT NULL DEFAULT '{}',  -- webhook URLs, etc (no secrets here)
    response_template    TEXT,
    max_response_length  INTEGER,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed default channel configs
INSERT INTO channel_configs (channel, enabled, max_response_length) VALUES
    ('email',     TRUE, 2000),
    ('whatsapp',  TRUE, 1600),
    ('web_form',  TRUE, 1000);

-- =============================================================================
-- AGENT METRICS — performance tracking
-- =============================================================================
CREATE TABLE agent_metrics (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_name  VARCHAR(100) NOT NULL,
    metric_value DECIMAL(12,4) NOT NULL,
    channel      VARCHAR(50),
    dimensions   JSONB NOT NULL DEFAULT '{}',
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- INDEXES
-- =============================================================================

-- customers
CREATE INDEX idx_customers_email  ON customers(email);
CREATE INDEX idx_customers_phone  ON customers(phone);

-- customer_identifiers
CREATE INDEX idx_customer_identifiers_value      ON customer_identifiers(identifier_value);
CREATE INDEX idx_customer_identifiers_customer   ON customer_identifiers(customer_id);

-- conversations
CREATE INDEX idx_conversations_customer  ON conversations(customer_id);
CREATE INDEX idx_conversations_status    ON conversations(status);
CREATE INDEX idx_conversations_channel   ON conversations(initial_channel);
CREATE INDEX idx_conversations_started   ON conversations(started_at DESC);

-- messages
CREATE INDEX idx_messages_conversation  ON messages(conversation_id);
CREATE INDEX idx_messages_channel       ON messages(channel);
CREATE INDEX idx_messages_created       ON messages(created_at DESC);
CREATE INDEX idx_messages_direction     ON messages(direction);

-- tickets
CREATE INDEX idx_tickets_customer   ON tickets(customer_id);
CREATE INDEX idx_tickets_status     ON tickets(status);
CREATE INDEX idx_tickets_channel    ON tickets(source_channel);
CREATE INDEX idx_tickets_created    ON tickets(created_at DESC);

-- knowledge_base (vector index for cosine similarity search)
CREATE INDEX idx_knowledge_embedding ON knowledge_base
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- agent_metrics
CREATE INDEX idx_metrics_name       ON agent_metrics(metric_name);
CREATE INDEX idx_metrics_recorded   ON agent_metrics(recorded_at DESC);
CREATE INDEX idx_metrics_channel    ON agent_metrics(channel);
