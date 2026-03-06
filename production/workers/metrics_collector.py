"""
Metrics Collector Worker
Aggregates agent_metrics from PostgreSQL and exposes channel-level KPIs.
Runs as a background task consumed by the /metrics/channels endpoint.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


class MetricsCollector:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # ------------------------------------------------------------------
    # Channel-level aggregates
    # ------------------------------------------------------------------

    async def get_channel_metrics(
        self,
        since_hours: int = 24,
    ) -> dict[str, Any]:
        """Return per-channel KPIs for the last N hours."""
        since = datetime.utcnow() - timedelta(hours=since_hours)

        query = """
            SELECT
                channel,
                COUNT(*)                                         AS total_messages,
                COUNT(*) FILTER (WHERE escalated = TRUE)         AS escalations,
                AVG(response_time_ms)                            AS avg_response_ms,
                ROUND(
                    100.0 * COUNT(*) FILTER (WHERE escalated = FALSE)
                    / NULLIF(COUNT(*), 0), 2
                )                                                AS resolution_rate_pct,
                AVG(sentiment_score)                             AS avg_sentiment
            FROM agent_metrics
            WHERE recorded_at >= $1
            GROUP BY channel
            ORDER BY channel;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, since)

        return {
            "window_hours": since_hours,
            "generated_at": datetime.utcnow().isoformat(),
            "channels": [dict(row) for row in rows],
        }

    # ------------------------------------------------------------------
    # Global aggregates
    # ------------------------------------------------------------------

    async def get_global_metrics(self, since_hours: int = 24) -> dict[str, Any]:
        """Return system-wide KPIs."""
        since = datetime.utcnow() - timedelta(hours=since_hours)

        query = """
            SELECT
                COUNT(*)                                         AS total_messages,
                COUNT(*) FILTER (WHERE escalated = TRUE)         AS total_escalations,
                AVG(response_time_ms)                            AS avg_response_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP
                    (ORDER BY response_time_ms)                  AS p95_response_ms,
                ROUND(
                    100.0 * COUNT(*) FILTER (WHERE escalated = FALSE)
                    / NULLIF(COUNT(*), 0), 2
                )                                                AS resolution_rate_pct
            FROM agent_metrics
            WHERE recorded_at >= $1;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, since)

        return {
            "window_hours": since_hours,
            "generated_at": datetime.utcnow().isoformat(),
            "global": dict(row) if row else {},
        }

    # ------------------------------------------------------------------
    # Hourly trend (for dashboards)
    # ------------------------------------------------------------------

    async def get_hourly_trend(self, hours: int = 24) -> dict[str, Any]:
        """Return message volume bucketed by hour."""
        since = datetime.utcnow() - timedelta(hours=hours)

        query = """
            SELECT
                DATE_TRUNC('hour', recorded_at)  AS hour,
                channel,
                COUNT(*)                          AS message_count,
                COUNT(*) FILTER (WHERE escalated) AS escalation_count
            FROM agent_metrics
            WHERE recorded_at >= $1
            GROUP BY 1, 2
            ORDER BY 1, 2;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, since)

        trend: list[dict] = []
        for row in rows:
            trend.append({
                "hour": row["hour"].isoformat(),
                "channel": row["channel"],
                "message_count": row["message_count"],
                "escalation_count": row["escalation_count"],
            })

        return {"window_hours": hours, "trend": trend}

    # ------------------------------------------------------------------
    # Continuous collection loop (called from worker entrypoint)
    # ------------------------------------------------------------------

    async def run_forever(self, interval_seconds: int = 60) -> None:
        """Periodically log aggregated metrics. Runs until cancelled."""
        logger.info("MetricsCollector started (interval=%ds)", interval_seconds)
        while True:
            try:
                global_metrics = await self.get_global_metrics(since_hours=1)
                g = global_metrics.get("global", {})
                logger.info(
                    "1h metrics | messages=%s escalations=%s "
                    "avg_response_ms=%s resolution_rate=%s%%",
                    g.get("total_messages"),
                    g.get("total_escalations"),
                    round(g.get("avg_response_ms") or 0, 1),
                    g.get("resolution_rate_pct"),
                )
            except Exception as exc:
                logger.error("MetricsCollector error: %s", exc, exc_info=True)

            await asyncio.sleep(interval_seconds)


# ------------------------------------------------------------------
# Standalone entrypoint
# ------------------------------------------------------------------

async def main() -> None:
    import os
    pool = await asyncpg.create_pool(dsn=os.environ["DATABASE_URL"], min_size=1, max_size=3)
    collector = MetricsCollector(pool)
    await collector.run_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
