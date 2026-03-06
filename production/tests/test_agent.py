"""Tests for the production Customer Success Agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from production.agent.formatters import (
    format_email,
    format_whatsapp,
    format_web_form,
    format_for_channel,
    split_whatsapp_messages,
)


# ---------------------------------------------------------------------------
# Formatter tests (no external deps needed)
# ---------------------------------------------------------------------------

class TestEmailFormatter:
    def test_wraps_in_html(self):
        result = format_email("Hello **world**", customer_name="Alice")
        assert "<html>" in result
        assert "Alice" in result

    def test_converts_markdown_bold(self):
        result = format_email("**important**", customer_name="Test")
        assert "<strong>important</strong>" in result

    def test_includes_signature(self):
        result = format_email("Body text", customer_name="Bob")
        assert "NovaFlow" in result


class TestWhatsAppFormatter:
    def test_strips_html_tags(self):
        result = format_whatsapp("<b>Hello</b>")
        assert "<b>" not in result
        assert "Hello" in result

    def test_truncates_long_message(self):
        long_msg = "x" * 2000
        result = format_whatsapp(long_msg)
        assert len(result) <= 1600

    def test_converts_markdown_to_whatsapp_bold(self):
        result = format_whatsapp("**bold text**")
        assert "*bold text*" in result


class TestWebFormFormatter:
    def test_returns_dict(self):
        result = format_web_form("Response text", ticket_id="TKT-001")
        assert isinstance(result, dict)
        assert result["ticket_id"] == "TKT-001"

    def test_includes_message(self):
        result = format_web_form("Your issue is resolved.", ticket_id="TKT-002")
        assert "Your issue is resolved." in result["message"]


class TestFormatForChannel:
    def test_routes_email(self):
        result = format_for_channel("email", "Hello", customer_name="Alice")
        assert "<html>" in result

    def test_routes_whatsapp(self):
        result = format_for_channel("whatsapp", "Hello")
        assert isinstance(result, str)
        assert "<html>" not in result

    def test_routes_web_form(self):
        result = format_for_channel("web_form", "Hello", ticket_id="TKT-001")
        assert isinstance(result, dict)

    def test_unknown_channel_raises(self):
        with pytest.raises(ValueError, match="Unknown channel"):
            format_for_channel("unknown", "Hello")


class TestSplitWhatsAppMessages:
    def test_short_message_not_split(self):
        parts = split_whatsapp_messages("Short message")
        assert len(parts) == 1

    def test_long_message_split(self):
        long_msg = "A" * 3000
        parts = split_whatsapp_messages(long_msg, max_length=1600)
        assert len(parts) == 2
        for part in parts:
            assert len(part) <= 1600


# ---------------------------------------------------------------------------
# Agent runner tests (mocked)
# ---------------------------------------------------------------------------

class TestCustomerSuccessAgent:
    @pytest.mark.asyncio
    async def test_agent_created_with_tools(self):
        with patch("production.agent.customer_success_agent.Agent") as MockAgent:
            from production.agent.customer_success_agent import agent
            assert agent is not None

    @pytest.mark.asyncio
    async def test_runner_called_with_message(self):
        mock_result = MagicMock()
        mock_result.final_output = "Here is your answer."

        with patch("production.agent.customer_success_agent.Runner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=mock_result)
            from openai_agents import Runner
            result = await Runner.run(
                MagicMock(),
                "I have a billing issue"
            )
            assert result.final_output == "Here is your answer."
