# NovaFlow Customer Success FTE — Operations Runbook

**Service**: `fte-api` + `fte-message-processor`
**Namespace**: `customer-success-fte`
**Owner**: Customer Success Engineering
**Last Updated**: 2026-03-06

---

## Table of Contents

1. [Alert Thresholds & On-Call Response](#1-alert-thresholds--on-call-response)
2. [High P95 Latency](#2-high-p95-latency)
3. [High Error Rate](#3-high-error-rate)
4. [High Escalation Rate](#4-high-escalation-rate)
5. [DLQ Drain](#5-dlq-drain)
6. [Deployment & Rollback](#6-deployment--rollback)
7. [Database Migration](#7-database-migration)
8. [Scaling & HPA](#8-scaling--hpa)
9. [Kafka Consumer Lag](#9-kafka-consumer-lag)
10. [Common Debugging Commands](#10-common-debugging-commands)

---

## 1. Alert Thresholds & On-Call Response

All thresholds defined in `k8s/prometheus-rules.yaml`. Summary:

| Alert | Threshold | Severity | Response Time |
|---|---|---|---|
| `HighP95Latency` | p95 > 3 s for 2 min | warning | 30 min |
| `CriticalP95Latency` | p95 > 10 s for 1 min | critical | 5 min |
| `HighErrorRate` | 5xx > 1% for 2 min | warning | 30 min |
| `CriticalErrorRate` | 5xx > 5% for 1 min | critical | 5 min |
| `HighEscalationRate` | escalation > 25% for 5 min | warning | 1 hour |
| `APIPodsLow` | available pods < 2 for 1 min | critical | 5 min |
| `WorkerPodsLow` | available pods < 2 for 1 min | critical | 5 min |
| `DLQGrowing` | DLQ lag +5 in 10 min | warning | 1 hour |

**On-call flow**:
1. Acknowledge alert in PagerDuty within response time above.
2. Check Grafana dashboard for visual context.
3. Follow the relevant runbook section below.
4. Post status update in `#cs-fte-incidents` Slack channel every 15 min during critical incidents.

---

## 2. High P95 Latency

**Alert**: `HighP95Latency` / `CriticalP95Latency`

### Step 1 — Identify the slow endpoint
```bash
# Check per-endpoint p95 in Grafana or via Prometheus
kubectl -n customer-success-fte port-forward svc/prometheus 9090:9090

# Query:
# histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="fte-api"}[5m])) by (le, handler))
```

### Step 2 — Check agent response times
```bash
kubectl -n customer-success-fte logs -l app=fte-api --tail=100 | grep "latency_ms"
```

### Step 3 — Check DB pool saturation
```bash
kubectl -n customer-success-fte exec -it deploy/fte-api -- \
  python -c "import asyncpg, asyncio, os; \
  async def check(): \
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL']); \
    print(pool.get_size(), pool.get_idle_size()); \
  asyncio.run(check())"
```

### Step 4 — Scale out if pool exhausted
```bash
kubectl -n customer-success-fte scale deployment fte-api --replicas=10
```

### Step 5 — If OpenAI API is slow, check status
```bash
curl https://status.openai.com/api/v2/status.json | jq '.status.description'
```

**Root cause candidates**: OpenAI API latency spike, DB connection pool exhaustion, Kafka producer backpressure, pgvector index not loaded (cold start).

---

## 3. High Error Rate

**Alert**: `HighErrorRate` / `CriticalErrorRate`

### Step 1 — Identify failing endpoints
```bash
kubectl -n customer-success-fte logs -l app=fte-api --tail=200 | grep "ERROR"
```

### Step 2 — Check for recent deployment
```bash
kubectl -n customer-success-fte rollout history deployment/fte-api
```

If a recent deployment correlates with the error spike → **rollback immediately** (see [Section 6](#6-deployment--rollback)).

### Step 3 — Check DLQ for failed worker messages
```bash
# See Section 5 — DLQ Drain
```

### Step 4 — Check DB connectivity
```bash
kubectl -n customer-success-fte exec -it deploy/fte-api -- \
  python -c "import asyncpg, asyncio, os; \
  async def check(): \
    conn = await asyncpg.connect(os.environ['DATABASE_URL']); \
    print(await conn.fetchval('SELECT 1')); \
  asyncio.run(check())"
```

### Step 5 — Check Kafka broker health
```bash
kubectl -n customer-success-fte exec -it deploy/fte-api -- \
  python -c "from kafka_client import TOPICS; print(list(TOPICS.values()))"
```

---

## 4. High Escalation Rate

**Alert**: `HighEscalationRate` (> 25% over 1 hour)

This usually indicates a **knowledge base gap** or a **prompt regression**, not an infrastructure problem.

### Step 1 — Identify top escalation reason codes
```bash
kubectl -n customer-success-fte exec -it deploy/fte-api -- psql $DATABASE_URL -c "
  SELECT escalation_reason, COUNT(*) as count
  FROM tickets
  WHERE escalated = TRUE
    AND created_at > NOW() - INTERVAL '2 hours'
  GROUP BY escalation_reason
  ORDER BY count DESC
  LIMIT 10;
"
```

### Step 2 — Check for knowledge base gaps
If `knowledge_gap` is the top reason code, the KB needs new articles:
```bash
kubectl -n customer-success-fte exec -it deploy/fte-api -- psql $DATABASE_URL -c "
  SELECT m.content
  FROM messages m
  JOIN tickets t ON t.conversation_id = m.conversation_id
  WHERE t.escalation_reason = 'knowledge_gap'
    AND m.role = 'user'
    AND m.created_at > NOW() - INTERVAL '2 hours'
  LIMIT 20;
"
```

### Step 3 — Check for prompt regression
Compare current system prompt hash against last known good:
```bash
kubectl -n customer-success-fte exec -it deploy/fte-api -- \
  python -c "from production.agent.prompts import CUSTOMER_SUCCESS_SYSTEM_PROMPT; \
  import hashlib; print(hashlib.md5(CUSTOMER_SUCCESS_SYSTEM_PROMPT.encode()).hexdigest())"
```

If hash differs from expected → roll back the agent deployment.

---

## 5. DLQ Drain

**Alert**: `DLQGrowing`

The Dead Letter Queue (`fte.dlq`) receives messages that failed processing after the worker's error handler ran. **Never silently drop DLQ messages.**

### Step 1 — Inspect DLQ messages
```bash
kubectl -n customer-success-fte exec -it deploy/fte-message-processor -- \
  python - <<'EOF'
import asyncio
from kafka_client import FTEKafkaConsumer, TOPICS

async def drain():
    consumer = FTEKafkaConsumer(topics=[TOPICS["dlq"]], group_id="dlq-inspector")
    await consumer.start()
    count = 0
    async for msg in consumer.consumer:
        print(f"[{count}] key={msg.key} value={msg.value[:200]}")
        count += 1
        if count >= 20:
            break
    await consumer.stop()

asyncio.run(drain())
EOF
```

### Step 2 — Classify failures
Common causes:
- `OpenAIError` — OpenAI API quota or outage → retry after resolution
- `asyncpg.PostgresConnectionError` — DB connectivity → fix DB first
- `ValidationError` — malformed message payload → inspect and fix producer

### Step 3 — Replay DLQ messages (after root cause fixed)
```bash
# Re-publish DLQ messages to the original inbound topic
kubectl -n customer-success-fte exec -it deploy/fte-message-processor -- \
  python - <<'EOF'
import asyncio, json
from kafka_client import FTEKafkaConsumer, get_producer, TOPICS

async def replay():
    consumer = FTEKafkaConsumer(topics=[TOPICS["dlq"]], group_id="dlq-replayer")
    producer = await get_producer()
    await consumer.start()
    replayed = 0
    async for msg in consumer.consumer:
        payload = json.loads(msg.value)
        original_topic = payload.get("original_topic", TOPICS["tickets_incoming"])
        await producer.publish(original_topic, payload)
        replayed += 1
    await consumer.stop()
    print(f"Replayed {replayed} messages")

asyncio.run(replay())
EOF
```

---

## 6. Deployment & Rollback

### Standard Deployment
```bash
# Build and push new image
docker build -t ghcr.io/ummehabiba1312/fte-api:${VERSION} .
docker push ghcr.io/ummehabiba1312/fte-api:${VERSION}

# Update deployment image
kubectl -n customer-success-fte set image \
  deployment/fte-api fte-api=ghcr.io/ummehabiba1312/fte-api:${VERSION}

# Monitor rollout
kubectl -n customer-success-fte rollout status deployment/fte-api --timeout=5m
```

### Canary Deployment (Phase 3)
```bash
# Deploy canary (10% traffic) — see k8s/deployment-api-canary.yaml
kubectl apply -f k8s/deployment-api-canary.yaml

# Monitor canary error rate for 10 minutes before promoting
# Promote: update main deployment
kubectl -n customer-success-fte set image \
  deployment/fte-api fte-api=ghcr.io/ummehabiba1312/fte-api:${VERSION}

# Remove canary
kubectl -n customer-success-fte delete deployment fte-api-canary
```

### Rollback
```bash
# Immediate rollback to previous revision
kubectl -n customer-success-fte rollout undo deployment/fte-api

# Rollback to specific revision
kubectl -n customer-success-fte rollout undo deployment/fte-api --to-revision=3

# Verify rollback
kubectl -n customer-success-fte rollout status deployment/fte-api
```

---

## 7. Database Migration

**Rule**: All schema changes MUST go through `database/migrations/`. Ad-hoc `ALTER TABLE` in production is prohibited (Constitution Principle III).

### Apply a migration
```bash
# From the project root, with DATABASE_URL set:
python database/migrate.py up

# Check migration status
python database/migrate.py status
```

### Rollback a migration
```bash
python database/migrate.py down --steps 1
```

### Create a new migration
```bash
# Copy the template
cp database/migrations/001_initial_schema.sql \
   database/migrations/002_your_migration_name.sql

# Edit the file — add UP and DOWN sections
# Apply it
python database/migrate.py up
```

### Emergency: Check applied migrations
```bash
kubectl -n customer-success-fte exec -it deploy/fte-api -- psql $DATABASE_URL -c \
  "SELECT id, name, applied_at FROM schema_migrations ORDER BY id;"
```

---

## 8. Scaling & HPA

### Current HPA configuration
| Deployment | Min | Max | CPU trigger |
|---|---|---|---|
| `fte-api` | 3 | 20 | 70% |
| `fte-message-processor` | 3 | 30 | 70% |

### Check HPA status
```bash
kubectl -n customer-success-fte get hpa
```

### Manual scale (emergency override)
```bash
# Temporarily override HPA minimum (reverts when HPA reconciles)
kubectl -n customer-success-fte patch hpa fte-api-hpa \
  -p '{"spec":{"minReplicas":5}}'
```

### Scale down after incident
```bash
kubectl -n customer-success-fte patch hpa fte-api-hpa \
  -p '{"spec":{"minReplicas":3}}'
```

---

## 9. Kafka Consumer Lag

### Check consumer group lag
```bash
kubectl -n customer-success-fte exec -it deploy/fte-message-processor -- \
  python - <<'EOF'
from aiokafka.admin import AIOKafkaAdminClient
import asyncio, os

async def check_lag():
    client = AIOKafkaAdminClient(bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"])
    await client.start()
    offsets = await client.list_consumer_group_offsets("fte-worker-group")
    for tp, offset in offsets.items():
        print(f"  {tp.topic}[{tp.partition}] offset={offset.offset}")
    await client.close()

asyncio.run(check_lag())
EOF
```

### If lag is growing — scale workers
```bash
kubectl -n customer-success-fte scale deployment fte-message-processor --replicas=10
```

---

## 10. Common Debugging Commands

```bash
# Tail API logs (all pods)
kubectl -n customer-success-fte logs -l app=fte-api -f --max-log-requests=10

# Tail worker logs
kubectl -n customer-success-fte logs -l app=fte-message-processor -f --max-log-requests=10

# Describe a crashlooping pod
kubectl -n customer-success-fte describe pod <pod-name>

# Get events (last 1 hour)
kubectl -n customer-success-fte get events --sort-by='.lastTimestamp' | tail -30

# Port-forward API for local testing
kubectl -n customer-success-fte port-forward svc/fte-api 8000:80

# Check secret values (base64 decoded)
kubectl -n customer-success-fte get secret fte-secrets -o jsonpath='{.data.OPENAI_API_KEY}' | base64 -d

# Run load test against live cluster
locust -f production/tests/load_test.py \
  --host https://support-api.yourdomain.com \
  --users 100 --spawn-rate 10 --run-time 2m --headless \
  --html load-test-report.html

# Check DB table sizes
kubectl -n customer-success-fte exec -it deploy/fte-api -- psql $DATABASE_URL -c "
  SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
  FROM pg_catalog.pg_statio_user_tables
  ORDER BY pg_total_relation_size(relid) DESC;
"
```

---

## SLO Summary (Constitution Principle VII)

| SLO | Target | Alert |
|---|---|---|
| Uptime | > 99.9% / 24h | `APIPodsLow` |
| p95 Processing Latency | < 3 s | `HighP95Latency` |
| Escalation Rate | < 25% | `HighEscalationRate` |
| Error Rate | < 1% | `HighErrorRate` |
| Cross-channel ID Accuracy | > 95% | (manual review) |
| Cost / Year | < $1,000 | (billing alert) |
