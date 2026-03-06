"""
NovaFlow Customer Success FTE — Database Queries
All async via asyncpg. No synchronous DB calls in workers.
"""
from __future__ import annotations

import os
from typing import Optional
import asyncpg

_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "fte_db"),
            user=os.getenv("POSTGRES_USER", "fte_user"),
            password=os.getenv("POSTGRES_PASSWORD"),
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_db_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Customer resolution (cross-channel)
# ---------------------------------------------------------------------------

async def resolve_customer(email: str = None, phone: str = None) -> Optional[str]:
    """Return existing customer UUID or None."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if email:
            row = await conn.fetchrow(
                "SELECT id FROM customers WHERE email = $1", email
            )
            if row:
                return str(row["id"])
        if phone:
            row = await conn.fetchrow(
                """SELECT customer_id FROM customer_identifiers
                   WHERE identifier_type = 'whatsapp' AND identifier_value = $1""",
                phone,
            )
            if row:
                return str(row["customer_id"])
    return None


async def create_customer(
    email: str = None,
    phone: str = None,
    name: str = None,
    plan: str = None,
) -> str:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        customer_id = await conn.fetchval(
            """INSERT INTO customers (email, phone, name, plan)
               VALUES ($1, $2, $3, $4) RETURNING id""",
            email, phone, name, plan,
        )
        if phone:
            await conn.execute(
                """INSERT INTO customer_identifiers
                   (customer_id, identifier_type, identifier_value)
                   VALUES ($1, 'whatsapp', $2)
                   ON CONFLICT DO NOTHING""",
                customer_id, phone,
            )
        return str(customer_id)


async def get_or_create_customer(
    email: str = None, phone: str = None, name: str = None
) -> str:
    existing = await resolve_customer(email=email, phone=phone)
    if existing:
        return existing
    return await create_customer(email=email, phone=phone, name=name)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

async def get_active_conversation(customer_id: str) -> Optional[str]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id FROM conversations
               WHERE customer_id = $1 AND status = 'active'
               AND started_at > NOW() - INTERVAL '24 hours'
               ORDER BY started_at DESC LIMIT 1""",
            customer_id,
        )
        return str(row["id"]) if row else None


async def create_conversation(customer_id: str, channel: str) -> str:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        conv_id = await conn.fetchval(
            """INSERT INTO conversations (customer_id, initial_channel, status)
               VALUES ($1, $2, 'active') RETURNING id""",
            customer_id, channel,
        )
        return str(conv_id)


async def get_or_create_conversation(customer_id: str, channel: str) -> str:
    existing = await get_active_conversation(customer_id)
    if existing:
        return existing
    return await create_conversation(customer_id, channel)


async def update_conversation_status(
    conversation_id: str,
    status: str,
    sentiment_score: float = None,
    resolution_type: str = None,
) -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE conversations
               SET status = $1,
                   sentiment_score = COALESCE($2, sentiment_score),
                   resolution_type = COALESCE($3, resolution_type),
                   ended_at = CASE WHEN $1 != 'active' THEN NOW() ELSE ended_at END
               WHERE id = $4""",
            status, sentiment_score, resolution_type, conversation_id,
        )


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

async def store_message(
    conversation_id: str,
    channel: str,
    direction: str,
    role: str,
    content: str,
    latency_ms: int = None,
    tool_calls: list = None,
    channel_message_id: str = None,
    tokens_used: int = None,
) -> str:
    import json
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        msg_id = await conn.fetchval(
            """INSERT INTO messages
               (conversation_id, channel, direction, role, content,
                latency_ms, tool_calls, channel_message_id, tokens_used)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id""",
            conversation_id, channel, direction, role, content,
            latency_ms, json.dumps(tool_calls or []),
            channel_message_id, tokens_used,
        )
        return str(msg_id)


async def load_conversation_history(
    conversation_id: str, limit: int = 20
) -> list[dict]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content, channel, created_at
               FROM messages WHERE conversation_id = $1
               ORDER BY created_at ASC LIMIT $2""",
            conversation_id, limit,
        )
        return [
            {"role": r["role"], "content": r["content"],
             "channel": r["channel"],
             "timestamp": r["created_at"].isoformat()}
            for r in rows
        ]


async def update_delivery_status(
    channel_message_id: str, status: str
) -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE messages SET delivery_status = $1
               WHERE channel_message_id = $2""",
            status, channel_message_id,
        )


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

async def create_ticket(
    customer_id: str,
    conversation_id: str,
    source_channel: str,
    subject: str = None,
    category: str = None,
    priority: str = "medium",
) -> str:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        ticket_id = await conn.fetchval(
            """INSERT INTO tickets
               (customer_id, conversation_id, source_channel,
                subject, category, priority, status)
               VALUES ($1,$2,$3,$4,$5,$6,'open') RETURNING id""",
            customer_id, conversation_id, source_channel,
            subject, category, priority,
        )
        return str(ticket_id)


async def escalate_ticket(
    ticket_id: str, reason: str, urgency: str = "normal"
) -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE tickets
               SET status = 'escalated',
                   escalation_reason = $1,
                   escalation_urgency = $2
               WHERE id = $3""",
            reason, urgency, ticket_id,
        )


async def resolve_ticket(ticket_id: str, notes: str = None) -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE tickets
               SET status = 'resolved', resolved_at = NOW(),
                   resolution_notes = $1
               WHERE id = $2""",
            notes, ticket_id,
        )


async def get_ticket(ticket_id: str) -> Optional[dict]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM tickets WHERE id = $1", ticket_id
        )
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Knowledge base — vector search
# ---------------------------------------------------------------------------

async def search_knowledge_base(
    embedding: list[float], max_results: int = 5, category: str = None
) -> list[dict]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT title, content, category,
                      1 - (embedding <=> $1::vector) AS similarity
               FROM knowledge_base
               WHERE ($2::text IS NULL OR category = $2)
               ORDER BY embedding <=> $1::vector
               LIMIT $3""",
            embedding, category, max_results,
        )
        return [dict(r) for r in rows]


async def upsert_knowledge_entry(
    title: str, content: str, category: str, embedding: list[float]
) -> str:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        kb_id = await conn.fetchval(
            """INSERT INTO knowledge_base (title, content, category, embedding)
               VALUES ($1,$2,$3,$4::vector)
               ON CONFLICT DO NOTHING RETURNING id""",
            title, content, category, embedding,
        )
        return str(kb_id)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

async def record_metric(
    name: str, value: float, channel: str = None, dimensions: dict = None
) -> None:
    import json
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO agent_metrics
               (metric_name, metric_value, channel, dimensions)
               VALUES ($1,$2,$3,$4)""",
            name, value, channel, json.dumps(dimensions or {}),
        )


async def get_channel_metrics(hours: int = 24) -> list[dict]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT initial_channel AS channel,
                      COUNT(*)                                         AS total_conversations,
                      AVG(sentiment_score)                             AS avg_sentiment,
                      COUNT(*) FILTER (WHERE status = 'escalated')    AS escalations,
                      COUNT(*) FILTER (WHERE status = 'resolved')     AS resolved
               FROM conversations
               WHERE started_at > NOW() - ($1 || ' hours')::INTERVAL
               GROUP BY initial_channel""",
            str(hours),
        )
        return [dict(r) for r in rows]
