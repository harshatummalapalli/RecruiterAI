"""Pure assembly: (Understanding + recruiter boundary) -> RoleModel.

No I/O, no LLM — fully unit-testable. This is where the recruiter's boundary
facts become authoritative, years are required (ask if missing), the role level
is classified, default title exclusions are applied/suppressed, the capability
group is derived, and un-filterable facts (work mode) are disclosed.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from recruiter.agents.intake.model import IntakeOutcome, Question, Understanding
from recruiter.role_model import (
    BACKSTOP,
    JD,
    RECRUITER,
    CompanyRules,
    Location,
    Provenance,
    Requirement,
    RoleModel,
    Seniority,
    classify_role_level,
    default_title_exclusions,
    derive_capability_groups,
    needs_years_clarification,
)


def _location(boundary: Dict[str, Any]) -> Location:
    mode = (boundary.get("work_mode") or "").strip().lower() or None
    cities = tuple(c for c in (boundary.get("cities") or []) if c)
    if not cities and boundary.get("city"):
        cities = (boundary["city"],)
    states = tuple(s for s in ([boundary.get("state")] if boundary.get("state") else []) if s)
    countries = tuple(c for c in ([boundary.get("country")] if boundary.get("country") else []) if c)
    radius_miles = boundary.get("radius_miles") if mode in ("onsite", "hybrid") else None
    radius_place = None
    if radius_miles and len(cities) == 1:
        radius_place = ", ".join(p for p in (cities[0], boundary.get("state")) if p)
    return Location(
        countries=countries, states=states, cities=cities,
        radius_place=radius_place, radius_miles=radius_miles, work_mode=mode,
    )


def assemble_role_model(
    understanding: Understanding,
    boundary: Dict[str, Any],
    answers: Optional[Dict[str, Any]] = None,
) -> IntakeOutcome:
    answers = answers or {}

    # Years are the gate. Prefer a recruiter answer, then the notes. Ask if neither.
    min_years = answers.get("min_years", understanding.min_years)
    if needs_years_clarification(min_years):
        return IntakeOutcome(clarifications=(
            Question(
                id="min_years",
                prompt="The notes don't state a minimum experience. What's the minimum years of experience required?",
                kind="min_years",
            ),
        ))

    identity = understanding.identity
    role_level = classify_role_level(identity, understanding.posted_title)

    # Default exec exclusions (suppressed for architect/manager/director+), plus
    # any the notes stated. Recruiter can edit these on the brief.
    exclude_titles = tuple(dict.fromkeys(default_title_exclusions(role_level)))

    requirements = tuple(
        Requirement(text=r.text, tier=r.tier, provenance=Provenance(JD, r.evidence))
        for r in understanding.requirements
    )
    capability_groups = derive_capability_groups(
        identity, understanding.posted_title, [r.text for r in understanding.requirements]
    )

    limitations = ()
    loc = _location(boundary)
    if loc.work_mode:
        limitations = (
            f"Work mode ({loc.work_mode}) is recorded for context; the search cannot filter candidates by work mode.",
        )

    hiring_company = (boundary.get("hiring_company") or "").strip() or None

    model = RoleModel(
        identity=identity,
        seniority=Seniority(
            min_years=min_years,
            max_years=answers.get("max_years", understanding.max_years),
            provenance=Provenance(RECRUITER if "min_years" in answers else JD),
        ),
        role_level=role_level,
        location=loc,
        requirements=requirements,
        capability_groups=capability_groups,
        companies=CompanyRules(exclude_current=(hiring_company,) if hiring_company else ()),
        exclude_titles=exclude_titles,
        posted_title=understanding.posted_title,
        posted_title_source=understanding.posted_title_source,
        employment_type=understanding.employment_type,
        hiring_company=hiring_company,
        limitations=limitations,
    )
    return IntakeOutcome(model=model)
