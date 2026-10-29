"""Admin-only view of the exact CrustData query — never shown to the recruiter,
only to a super-admin (same gating pattern as the credit meter). Lets us inspect
the plumbing without ever leaking it into the recruiter's intent review."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from recruiter.agents.briefing.model import BriefingPlan


def admin_query_view(plan: BriefingPlan) -> Dict[str, Any]:
    view = asdict(plan.query)
    view["disclosures"] = list(plan.disclosures)
    view["judge_verifies"] = [r.text for r in plan.judge_signals]
    return view
