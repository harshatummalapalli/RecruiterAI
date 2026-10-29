"""The LLM reader: hiring notes -> Understanding.

Thin adapter over the keeper two-task intake reasoner (validated Task A/B +
deterministic contradiction backstops). Runs boundary-blind — the boundary is
applied later in assemble.py, keeping the two readings independent. The keeper
import is lazy so tests that inject a fake reader never touch backend/ or OpenAI.

This is the one I/O module in Intake; everything else is pure.
"""

from __future__ import annotations

from typing import Optional

from recruiter.agents.intake.model import ReadRequirement, Understanding


def keeper_reader(notes: str, posted_title: Optional[str] = None) -> Understanding:
    from backend.services.intake_reasoning import IntakeReasoner  # keeper (to be migrated in)

    result = IntakeReasoner().run(notes, posted_title=posted_title)
    ru = result.role_understanding
    fsi = result.decision.final_search_intent
    evidence = fsi.evidence or {}

    def _reqs(texts, tier):
        return [ReadRequirement(text=t, tier=tier, evidence=evidence.get(t)) for t in texts]

    requirements = (
        _reqs(fsi.hard_requirements, "core")
        + _reqs(fsi.strong_signals, "supporting")
        + _reqs(fsi.preferred_differentiators, "differentiator")
    )
    constraints = ru.explicit_constraints
    return Understanding(
        identity=ru.primary_candidate_identity.value or (posted_title or ""),
        requirements=tuple(requirements),
        posted_title=ru.posted_title,
        posted_title_source=ru.posted_title_source,
        min_years=constraints.experience_minimum_years,
        max_years=constraints.experience_maximum_years,
        employment_type=constraints.employment_type,
        work_mode_in_notes=constraints.work_mode,
    )
