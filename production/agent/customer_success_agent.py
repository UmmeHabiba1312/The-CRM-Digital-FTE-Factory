"""
NovaFlow Customer Success FTE — Production Agent
OpenAI Agents SDK custom agent definition.
"""
from __future__ import annotations

from agents import Agent

from production.agent.prompts import CUSTOMER_SUCCESS_SYSTEM_PROMPT
from production.agent.tools import (
    search_knowledge_base,
    create_ticket,
    get_customer_history,
    escalate_to_human,
    send_response,
    analyse_sentiment,
)

customer_success_agent = Agent(
    name="NovaFlow Customer Success FTE",
    model="gpt-4o",
    instructions=CUSTOMER_SUCCESS_SYSTEM_PROMPT,
    tools=[
        create_ticket,
        get_customer_history,
        analyse_sentiment,
        search_knowledge_base,
        escalate_to_human,
        send_response,
    ],
)
