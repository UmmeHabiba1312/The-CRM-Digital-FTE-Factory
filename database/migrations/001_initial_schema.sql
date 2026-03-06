-- =============================================================================
-- Migration 001 — Initial Schema
-- Applied by: database/migrate.py
-- Description: Full initial schema — customers, identifiers, conversations,
--              messages, tickets, knowledge_base, channel_configs, agent_metrics
-- =============================================================================

-- ============================================================
-- UP
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE customers (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email        VARCHAR(255) UNIQUE,
    phone        VARCHAR(50),
    name         VARCHAR(255),
    plan         VARCHAR(50),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata     JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE customer_identifiers (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id      UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    identifier_type  VARCHAR(50) NOT NULL,
    identifier_value VARCHAR(255) NOT NULL,
    verified         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (identifier_type, identifier_value)
);

CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    initial_channel VARCHAR(50) NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    status          VARCHAR(50) NOT NULL DEFAULT 'active',
    sentiment_score DECIMAL(4,3),
    resolution_type VARCHAR(50),
    escalated_to    VARCHAR(255),
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE messages (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id    UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    channel            VARCHAR(50) NOT NULL,
    direction          VARCHAR(20) NOT NULL,
    role               VARCHAR(20) NOT NULL,
    content            TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tokens_used        INTEGER,
    latency_ms         INTEGER,
    tool_calls         JSONB NOT NULL DEFAULT '[]',
    channel_message_id VARCHAR(255),
    delivery_status    VARCHAR(50) NOT NULL DEFAULT 'pending'
);

CREATE TABLE tickets (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id    UUID REFERENCES conversations(id) ON DELETE SET NULL,
    customer_id        UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    source_channel     VARCHAR(50) NOT NULL,
    subject            VARCHAR(500),
    category           VARCHAR(100),
    priority           VARCHAR(20) NOT NULL DEFAULT 'medium',
    status             VARCHAR(50) NOT NULL DEFAULT 'open',
    escalation_reason  VARCHAR(100),
    escalation_urgency VARCHAR(20),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at        TIMESTAMPTZ,
    resolution_notes   TEXT
);

CREATE TABLE knowledge_base (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title      VARCHAR(500) NOT NULL,
    content    TEXT NOT NULL,
    category   VARCHAR(100),
    embedding  VECTOR(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE channel_configs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel              VARCHAR(50) UNIQUE NOT NULL,
    enabled              BOOLEAN NOT NULL DEFAULT TRUE,
    config               JSONB NOT NULL DEFAULT '{}',
    response_template    TEXT,
    max_response_length  INTEGER,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO channel_configs (channel, enabled, max_response_length) VALUES
    ('email',     TRUE, 2000),
    ('whatsapp',  TRUE, 1600),
    ('web_form',  TRUE, 1000);

CREATE TABLE agent_metrics (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_name  VARCHAR(100) NOT NULL,
    metric_value DECIMAL(12,4) NOT NULL,
    channel      VARCHAR(50),
    dimensions   JSONB NOT NULL DEFAULT '{}',
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_customers_email               ON customers(email);
CREATE INDEX idx_customers_phone               ON customers(phone);
CREATE INDEX idx_customer_identifiers_value    ON customer_identifiers(identifier_value);
CREATE INDEX idx_customer_identifiers_customer ON customer_identifiers(customer_id);
CREATE INDEX idx_conversations_customer        ON conversations(customer_id);
CREATE INDEX idx_conversations_status          ON conversations(status);
CREATE INDEX idx_conversations_channel         ON conversations(initial_channel);
CREATE INDEX idx_conversations_started         ON conversations(started_at DESC);
CREATE INDEX idx_messages_conversation         ON messages(conversation_id);
CREATE INDEX idx_messages_channel              ON messages(channel);
CREATE INDEX idx_messages_created              ON messages(created_at DESC);
CREATE INDEX idx_messages_direction            ON messages(direction);
CREATE INDEX idx_tickets_customer              ON tickets(customer_id);
CREATE INDEX idx_tickets_status                ON tickets(status);
CREATE INDEX idx_tickets_channel               ON tickets(source_channel);
CREATE INDEX idx_tickets_created               ON tickets(created_at DESC);
CREATE INDEX idx_knowledge_embedding           ON knowledge_base
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_metrics_name                  ON agent_metrics(metric_name);
CREATE INDEX idx_metrics_recorded              ON agent_metrics(recorded_at DESC);
CREATE INDEX idx_metrics_channel               ON agent_metrics(channel);

-- ============================================================
-- DOWN  (run with: python database/migrate.py down --steps 1)
-- ============================================================
-- DROP TABLE IF EXISTS agent_metrics CASCADE;
-- DROP TABLE IF EXISTS channel_configs CASCADE;
-- DROP TABLE IF EXISTS knowledge_base CASCADE;
-- DROP TABLE IF EXISTS tickets CASCADE;
-- DROP TABLE IF EXISTS messages CASCADE;
-- DROP TABLE IF EXISTS conversations CASCADE;
-- DROP TABLE IF EXISTS customer_identifiers CASCADE;
-- DROP TABLE IF EXISTS customers CASCADE;
