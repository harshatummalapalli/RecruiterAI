"""Build the recruiter-facing intent review — plain language, from the
RoleModel. It validates that we understood the role; it never shows the NL
query, keyword groups, or filter fields (those live in the admin view only).
"""

from __future__ import annotations

from typing import List, Tuple

from recruiter.agents.calibration.model import ReviewLine, ReviewPackage
from recruiter.agents.intake.model import Question
from recruiter.role_model import RoleModel

_LEVEL_WORDS = {
    "ic": "an individual-contributor role",
    "architect": "an architect (IC-track) role",
    "manager": "a manager role",
    "director+": "a director-level-or-above role",
}


def _location_sentence(model: RoleModel) -> str:
    loc = model.location
    if loc.radius_place and loc.radius_miles:
        scope = f"within {int(loc.radius_miles)} miles of {loc.radius_place}"
        return scope + (f" (in {', '.join(loc.countries)})" if loc.countries else "")
    if loc.cities:
        scope = ", ".join(loc.cities)
    elif loc.states:
        scope = ", ".join(loc.states)
    else:
        scope = ", ".join(loc.countries) or "anywhere"
    if loc.preferred_cities and not loc.cities:
        scope += f" (preferring {', '.join(loc.preferred_cities)}, not excluding the rest)"
    return scope


def build_review(model: RoleModel, disclosures: Tuple[str, ...], questions: Tuple[Question, ...]) -> ReviewPackage:
    lines: List[ReviewLine] = []
    lines.append(ReviewLine("Role", f"{model.identity} — {_LEVEL_WORDS.get(model.role_level, model.role_level or 'a role')}"))

    if model.seniority.min_years is not None:
        yrs = f"{model.seniority.min_years}+ years"
        if model.seniority.max_years:
            yrs = f"{model.seniority.min_years}–{model.seniority.max_years} years"
        lines.append(ReviewLine("Experience", yrs))

    lines.append(ReviewLine("Location", _location_sentence(model)))

    current = [r.text for r in model.core if r.when != "past"]
    past = [r.text for r in model.core if r.when == "past"]
    if current:
        lines.append(ReviewLine("Must have now", ", ".join(current)))
    if past:
        lines.append(ReviewLine("Background (nice, not required)", ", ".join(past)))

    supporting = [r.text for r in model.tier("supporting")]
    if supporting:
        lines.append(ReviewLine("Strong signals", ", ".join(supporting)))

    for group in model.capability_groups:
        lines.append(ReviewLine("Specialisation required", f"genuine {group.label} experience"))

    if model.companies.prefer_ever:
        lines.append(ReviewLine("Only from", f"people who worked at {', '.join(model.companies.prefer_ever)}"))
    if model.companies.exclude_current:
        lines.append(ReviewLine("Excluding", f"people currently at {', '.join(model.companies.exclude_current)}"))
    if model.industries:
        lines.append(ReviewLine("Industry", ", ".join(model.industries)))
    if model.role_level in ("architect", "manager", "director+"):
        lines.append(ReviewLine("Seniority titles", "kept eligible (this is a senior/leadership role)"))

    return ReviewPackage(summary=tuple(lines), limits=tuple(disclosures), questions=tuple(questions))
