"""Transition validation tests: Phase 1 prototype vs Phase 2 production parity."""
import pytest
import json
from pathlib import Path


SAMPLE_TICKETS_PATH = Path(__file__).parents[2] / "context" / "sample-tickets.json"


def load_sample_tickets():
    with open(SAMPLE_TICKETS_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Escalation rule coverage (14 edge cases from transition checklist)
# ---------------------------------------------------------------------------

ESCALATION_TRIGGERS = [
    "legal action",
    "sue you",
    "attorney",
    "data breach",
    "refund",
    "cancel my account",
    "executive",
    "ceo",
]

NON_ESCALATION_PHRASES = [
    "how do I reset my password",
    "what are your business hours",
    "where can I find my invoice",
    "can you help me integrate",
]


class TestEscalationRules:
    def test_escalation_triggers_present_in_rules(self):
        """Verify every hard trigger from the spec exists in escalation-rules.md."""
        rules_path = Path(__file__).parents[2] / "context" / "escalation-rules.md"
        content = rules_path.read_text(encoding="utf-8").lower()
        for trigger in ESCALATION_TRIGGERS:
            assert trigger.lower() in content, (
                f"Escalation trigger '{trigger}' missing from escalation-rules.md"
            )

    def test_non_escalation_phrases_not_in_hard_triggers(self):
        """Routine queries should not match hard escalation triggers."""
        rules_path = Path(__file__).parents[2] / "context" / "escalation-rules.md"
        content = rules_path.read_text(encoding="utf-8").lower()
        hard_section_start = content.find("hard trigger")
        hard_section = content[hard_section_start:hard_section_start + 2000]
        for phrase in NON_ESCALATION_PHRASES:
            # Each individual word may appear but the full phrase should not
            assert phrase.lower() not in hard_section, (
                f"Non-escalation phrase '{phrase}' found in hard triggers section"
            )


# ---------------------------------------------------------------------------
# Sample tickets coverage
# ---------------------------------------------------------------------------

class TestSampleTickets:
    def test_tickets_loaded(self):
        tickets = load_sample_tickets()
        assert len(tickets) >= 50, "Expected at least 50 sample tickets"

    def test_tickets_have_required_fields(self):
        tickets = load_sample_tickets()
        required = {"id", "channel", "customer_email", "message", "expected_action", "tags"}
        for ticket in tickets:
            missing = required - set(ticket.keys())
            assert not missing, f"Ticket {ticket.get('id')} missing fields: {missing}"

    def test_all_channels_represented(self):
        tickets = load_sample_tickets()
        channels = {t["channel"] for t in tickets}
        assert "email" in channels
        assert "whatsapp" in channels
        assert "web_form" in channels

    def test_sentiment_values_valid(self):
        tickets = load_sample_tickets()
        valid_sentiments = {"positive", "neutral", "negative", "frustrated"}
        for ticket in tickets:
            if "sentiment" in ticket:
                assert ticket["sentiment"] in valid_sentiments, (
                    f"Invalid sentiment '{ticket['sentiment']}' in ticket {ticket['id']}"
                )

    def test_expected_actions_valid(self):
        tickets = load_sample_tickets()
        valid_actions = {
            "resolve",
            "escalate",
            "provide_info",
            "create_ticket",
            "follow_up",
        }
        for ticket in tickets:
            action = ticket.get("expected_action", "")
            assert action in valid_actions, (
                f"Invalid expected_action '{action}' in ticket {ticket['id']}"
            )


# ---------------------------------------------------------------------------
# Spec artifact existence checks
# ---------------------------------------------------------------------------

class TestSpecArtifacts:
    BASE = Path(__file__).parents[2]

    def _exists(self, rel_path: str) -> bool:
        return (self.BASE / rel_path).exists()

    def test_constitution_exists(self):
        assert self._exists(".specify/memory/constitution.md")

    def test_crystallized_spec_exists(self):
        assert self._exists("specs/customer-success-fte-spec.md")

    def test_discovery_log_exists(self):
        assert self._exists("specs/discovery-log.md")

    def test_transition_checklist_exists(self):
        assert self._exists("specs/transition-checklist.md")

    def test_database_schema_exists(self):
        assert self._exists("database/schema.sql")

    def test_k8s_manifests_exist(self):
        k8s_files = [
            "k8s/namespace.yaml",
            "k8s/configmap.yaml",
            "k8s/secrets.yaml",
            "k8s/deployment-api.yaml",
            "k8s/deployment-worker.yaml",
            "k8s/service.yaml",
            "k8s/ingress.yaml",
            "k8s/hpa.yaml",
        ]
        for f in k8s_files:
            assert self._exists(f), f"Missing K8s manifest: {f}"

    def test_dockerfile_exists(self):
        assert self._exists("Dockerfile")

    def test_docker_compose_exists(self):
        assert self._exists("docker-compose.yml")

    def test_env_example_exists(self):
        assert self._exists(".env.example")
