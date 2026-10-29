"""Agent 2 — Briefing. Turns the RoleModel into the CrustData query."""

from recruiter.agents.briefing.agent import BriefingAgent
from recruiter.agents.briefing.model import BriefingPlan, ProviderQuery
from recruiter.agents.briefing.query import build_nl_query

__all__ = ["BriefingAgent", "BriefingPlan", "ProviderQuery", "build_nl_query"]
