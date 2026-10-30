"""Pure assembly: (Understanding + recruiter boundary) -> RoleModel.

No I/O, no LLM — fully unit-testable. This is where the recruiter's boundary
facts become authoritative, years are required (ask if missing), the role level
is classified, default title exclusions are applied/suppressed, the capability
group is derived, and un-filterable facts (work mode) are disclosed.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from recruiter.agents.intake.model import IntakeOutcome, Question, Understanding
from recruiter.role_model import (
    JD,
    RECRUITER,
    CapabilityGroup,
    CompanyRules,
    Location,
    Provenance,
    Requirement,
    RoleModel,
    Seniority,
    classify_role_level,
    default_title_exclusions,
    needs_years_clarification,
)


# Separators newer models append a descriptor after ("AI Architect (Agentic
# Systems)", "Sales Manager — restaurant acquisition", "Sales Manager, B2B …").
# The identity drives title-relevance scoring, so keep it title-shaped. " / " is
# NOT a separator (real compound titles like "Field Sales / BD Manager").
_IDENTITY_SEPARATORS = (" (", " — ", " – ", " - ", " | ", ", ")


def _is_specialization(token: str, requirement_texts: Tuple[str, ...]) -> bool:
    """A trailing title segment is a SPECIALIZATION (keep it) — not a descriptive
    clause (drop it) — when it's a single token the requirements corroborate.
    "Operations Analyst – eDiscovery" keeps "eDiscovery" (it's in the reqs);
    "Sales Manager — restaurant acquisition" drops the multi-word clause."""
    token = token.strip()
    if not token or len(token.split()) != 1:
        return False
    blob = " ".join(requirement_texts).lower()
    return token.lower() in blob


def normalize_identity(
    identity: Optional[str],
    posted_title: Optional[str],
    requirement_texts: Tuple[str, ...] = (),
) -> str:
    text = (identity or "").strip()
    spec: Optional[str] = None
    for sep in _IDENTITY_SEPARATORS:
        if sep in text:
            head, tail = text.split(sep, 1)
            # the " (" separator leaves the paren already consumed; strip any other.
            tail_token = re.sub(r"\s*\(.*$", "", tail).strip()
            if spec is None and _is_specialization(tail_token, requirement_texts):
                spec = tail_token
            text = head.strip()
    text = re.sub(r"\s*\(.*$", "", text).strip()   # drop any stray trailing "(...)"
    words = text.split()
    if len(words) > 6:
        text = " ".join(words[:6])
    base = text or (posted_title or (identity or "").strip())
    # Re-attach the specialization so it anchors title-relevance, the NL query,
    # and (critically) the per-org capability-memory key — a generic "Operations
    # Analyst" key would let one role's learned capability contaminate another.
    if spec and spec.lower() not in base.lower():
        base = f"{spec} {base}".strip()
    return base


def _location(boundary: Dict[str, Any]) -> Location:
    """Turn the recruiter boundary into the hard location scope. Work mode is
    NOT a filter (CrustData can't) — it decides HOW geography becomes the hard
    filter: remote -> a country/states/cities scope; onsite/hybrid -> a city
    (+ radius) scope. Work mode itself is recorded and disclosed downstream."""
    mode = (boundary.get("work_mode") or "").strip().lower() or None
    countries = tuple(c for c in ([boundary.get("country")] if boundary.get("country") else []) if c)
    preferred_cities = tuple(c for c in (boundary.get("preferred_cities") or []) if c)

    if mode == "remote":
        scope = (boundary.get("remote_scope") or "").strip().lower()
        if scope == "cities":
            cities, states = tuple(boundary.get("remote_cities") or []), ()
        elif scope == "states":
            cities, states = (), tuple(boundary.get("remote_states") or [])
        else:  # "anywhere" / unspecified -> country-wide
            cities, states = (), ()
        return Location(countries=countries, states=states, cities=cities,
                        preferred_cities=preferred_cities, work_mode=mode)

    # onsite / hybrid (or unspecified): city/cities (+ radius anchor on one city).
    cities = tuple(c for c in (boundary.get("cities") or []) if c)
    if not cities and boundary.get("city"):
        cities = (boundary["city"],)
    states = tuple(s for s in ([boundary.get("state")] if boundary.get("state") else []) if s)
    radius_miles = boundary.get("radius_miles")
    radius_place = None
    if radius_miles and len(cities) == 1:
        radius_place = ", ".join(p for p in (cities[0], boundary.get("state")) if p)
    return Location(
        countries=countries, states=states, cities=cities, preferred_cities=preferred_cities,
        radius_place=radius_place, radius_miles=radius_miles, work_mode=mode,
    )


def assemble_role_model(
    understanding: Understanding,
    boundary: Dict[str, Any],
    answers: Optional[Dict[str, Any]] = None,
    capability_groups: Tuple[CapabilityGroup, ...] = (),
) -> IntakeOutcome:
    """Pure. `capability_groups` are supplied by the agent (memory/LLM proposer);
    this function never proposes them itself, so it stays I/O-free."""
    answers = answers or {}

    # Years are the gate. Prefer a recruiter answer, then the notes. Ask if neither.
    min_years = answers.get("min_years", understanding.min_years)
    if needs_years_clarification(min_years):
        return IntakeOutcome(clarifications=(
            Question(
                id="min_years",
                prompt="The notes don't state a minimum experience. What's the minimum years of experience required?",
                kind="min_years",
                routing="filter",
                required=True,
            ),
        ))

    identity = normalize_identity(
        understanding.identity,
        understanding.posted_title,
        tuple(r.text for r in understanding.requirements),
    )
    role_level = classify_role_level(identity, understanding.posted_title)

    # Default exec exclusions (suppressed for architect/manager/director+), plus
    # any the notes stated. Recruiter can edit these on the brief.
    exclude_titles = tuple(dict.fromkeys(default_title_exclusions(role_level)))

    requirements = tuple(
        Requirement(text=r.text, tier=r.tier, provenance=Provenance(JD, r.evidence), when=r.when)
        for r in understanding.requirements
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
