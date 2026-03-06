"""
Locust load test suite — NovaFlow Customer Success FTE
Validates: p95 latency < 3 s under 100+ concurrent users (Constitution Principle V & VII)

Run:
    locust -f production/tests/load_test.py --host http://localhost:8000 \
           --users 100 --spawn-rate 10 --run-time 2m --headless \
           --html load-test-report.html
"""
import random
import string
import json
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def random_email() -> str:
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    return f"load-test-{suffix}@example.com"


def random_name() -> str:
    first = random.choice(["Alice", "Bob", "Carlos", "Diana", "Emre", "Fatima"])
    last = random.choice(["Smith", "Jones", "Patel", "Kim", "Müller", "Garcia"])
    return f"{first} {last}"


CATEGORIES = ["billing", "technical", "account", "general", "integration"]
PRIORITIES = ["low", "medium", "high"]

SAMPLE_MESSAGES = [
    "I cannot connect my Slack integration. It says 'Invalid OAuth token' every time.",
    "How do I add a new team member to my workspace?",
    "My workflow is not triggering automatically even though I set it up correctly.",
    "Where can I find my invoice for last month?",
    "I need help setting up my first automation workflow.",
    "The API is returning a 500 error when I call the /workflows endpoint.",
    "Can you explain how the conditional branching feature works?",
    "I upgraded to Pro but I still cannot access advanced analytics.",
    "How do I export my workflow data to CSV?",
    "I have been trying to reset my password for 30 minutes but the email never arrives.",
]

WHATSAPP_MESSAGES = [
    "hi i need help with my account",
    "my workflow isnt working",
    "how do i add team members",
    "i cant login",
    "billing question",
]


# ---------------------------------------------------------------------------
# Web Form user (heaviest traffic — ~60% of load)
# ---------------------------------------------------------------------------

class WebFormUser(HttpUser):
    weight = 6
    wait_time = between(0.5, 2.0)

    @task(10)
    def submit_support_form(self):
        payload = {
            "name": random_name(),
            "email": random_email(),
            "category": random.choice(CATEGORIES),
            "priority": random.choice(PRIORITIES),
            "subject": random.choice([
                "Integration issue",
                "Billing question",
                "How-to guidance needed",
                "Feature request",
                "Account access problem",
            ]),
            "message": random.choice(SAMPLE_MESSAGES),
        }
        with self.client.post(
            "/support",
            json=payload,
            catch_response=True,
            name="POST /support",
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if "ticket_id" not in data:
                    resp.failure("Response missing ticket_id")
            elif resp.status_code == 422:
                resp.failure(f"Validation error: {resp.text[:200]}")
            else:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(3)
    def check_ticket_status(self):
        # Use a fake ticket ID — we expect 404 but the endpoint must respond fast
        fake_id = f"TKT-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
        with self.client.get(
            f"/support/{fake_id}/status",
            catch_response=True,
            name="GET /support/{id}/status",
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(1)
    def health_check(self):
        with self.client.get("/health", catch_response=True, name="GET /health") as resp:
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                resp.success()
            else:
                resp.failure("Health check failed")


# ---------------------------------------------------------------------------
# API metrics user (~20% of load — monitoring / dashboard queries)
# ---------------------------------------------------------------------------

class MetricsUser(HttpUser):
    weight = 2
    wait_time = between(5.0, 15.0)

    @task(5)
    def get_channel_metrics(self):
        with self.client.get(
            "/metrics/channels",
            catch_response=True,
            name="GET /metrics/channels",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Metrics endpoint returned {resp.status_code}")

    @task(2)
    def health_check(self):
        self.client.get("/health", name="GET /health")


# ---------------------------------------------------------------------------
# Webhook simulation user (~20% of load)
# ---------------------------------------------------------------------------

class WebhookUser(HttpUser):
    weight = 2
    wait_time = between(1.0, 5.0)

    @task(5)
    def whatsapp_status_callback(self):
        """Status callbacks must always return 200 quickly."""
        import uuid
        form_data = {
            "MessageSid": f"SM{uuid.uuid4().hex[:32]}",
            "MessageStatus": random.choice(["sent", "delivered", "read"]),
            "To": "whatsapp:+15005550006",
            "AccountSid": "AC_load_test",
        }
        with self.client.post(
            "/webhooks/whatsapp/status",
            data=form_data,
            catch_response=True,
            name="POST /webhooks/whatsapp/status",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status callback returned {resp.status_code}")

    @task(2)
    def customer_lookup(self):
        with self.client.get(
            f"/customers/lookup?email={random_email()}",
            catch_response=True,
            name="GET /customers/lookup",
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")


# ---------------------------------------------------------------------------
# Locust event hooks — SLO validation
# ---------------------------------------------------------------------------

@events.quitting.add_listener
def validate_slo(environment, **kwargs):
    """Fail the load test run if p95 latency exceeds 3000 ms."""
    stats = environment.runner.stats.total
    if stats.num_requests == 0:
        print("⚠️  No requests completed — cannot validate SLO")
        return

    p95_ms = stats.get_response_time_percentile(0.95)
    failure_rate = stats.fail_ratio * 100
    rps = stats.current_rps

    print("\n" + "=" * 60)
    print("LOAD TEST SLO VALIDATION")
    print("=" * 60)
    print(f"  Total requests : {stats.num_requests}")
    print(f"  Failure rate   : {failure_rate:.2f}%")
    print(f"  p95 latency    : {p95_ms:.0f} ms  (target: < 3000 ms)")
    print(f"  Current RPS    : {rps:.1f}")

    violations = []

    if p95_ms > 3000:
        violations.append(f"p95 latency {p95_ms:.0f}ms exceeds 3000ms SLO")

    if failure_rate > 1.0:
        violations.append(f"Failure rate {failure_rate:.2f}% exceeds 1% SLO")

    if violations:
        print("\n❌ SLO VIOLATIONS:")
        for v in violations:
            print(f"   • {v}")
        environment.process_exit_code = 1
    else:
        print("\n✅ All SLOs PASSED")
    print("=" * 60)
