"""Apply a recruiter's STRUCTURED refine deltas to a confirmed RoleModel.

Like `apply_answers` (which it reuses for the tier/dealbreaker/disqualifier/
capability edits), but for the full refine panel: hard non-negotiables (years,
work mode, location cascade), company include/exclude, title excludes, industries,
the current/ever tense of a requirement, and new must-haves chosen from
suggestions. Pure: a NEW immutable RoleModel out, provenance RECRUITER, never
mutating the input. No free text is interpreted here — every delta is a typed,
capability-grounded field.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict

from recruiter.agents.calibration.apply import apply_answers
from recruiter.role_model import Provenance, RECRUITER, Requirement, RoleModel

_TIERS = ("core", "supporting", "differentiator")
_WHEN = ("past", "current", "any")
# The answer-style edits apply_answers already owns — passed straight through.
_ANSWER_KEYS = ("retier", "dealbreakers", "disqualifiers", "capability", "priority")


def _merge(existing, additions) -> tuple:
    """Order-preserving union of two string tuples, de-duplicated."""
    out = list(existing)
    for item in additions or ():
        item = (item or "").strip()
        if item and item not in out:
            out.append(item)
    return tuple(out)


def refine_model(model: RoleModel, deltas: Dict[str, Any]) -> RoleModel:
    deltas = deltas or {}

    # 1. The tier / dealbreaker / disqualifier / capability edits apply_answers owns.
    answers = {key: deltas[key] for key in _ANSWER_KEYS if key in deltas}
    if answers:
        model = apply_answers(model, answers)

    # 2. Years — the gate. Seniority is frozen; a change is recruiter-authored.
    sen = model.seniority
    min_years = deltas.get("min_years", sen.min_years)
    max_years = deltas.get("max_years", sen.max_years)
    if (min_years, max_years) != (sen.min_years, sen.max_years):
        sen = replace(sen, min_years=min_years, max_years=max_years, provenance=Provenance(RECRUITER))

    # 3. Location cascade + work mode.
    loc = model.location
    locd = deltas.get("location") or {}
    loc = replace(
        loc,
        countries=tuple(locd.get("countries", loc.countries)),
        states=tuple(locd.get("states", loc.states)),
        cities=tuple(locd.get("cities", loc.cities)),
        preferred_cities=tuple(locd.get("preferred_cities", loc.preferred_cities)),
        radius_place=locd.get("radius_place", loc.radius_place),
        radius_miles=locd.get("radius_miles", loc.radius_miles),
        work_mode=deltas.get("work_mode", loc.work_mode),
    )

    # 4. Companies — exclude (current / ever) and "only from" / prefer (ever).
    comp = model.companies
    comp = replace(
        comp,
        exclude_current=_merge(comp.exclude_current, deltas.get("exclude_companies_current")),
        exclude_ever=_merge(comp.exclude_ever, deltas.get("exclude_companies_ever")),
        prefer_ever=_merge(comp.prefer_ever, deltas.get("only_companies") or deltas.get("prefer_companies_ever")),
    )

    # 5. Title excludes, 6. industries (added; a verified hard filter).
    exclude_titles = _merge(model.exclude_titles, deltas.get("exclude_titles"))
    industries = _merge(model.industries, deltas.get("industries"))

    # 7. Tense (Currently vs Ever held) on existing requirements.
    when = deltas.get("when") or {}
    requirements = [
        replace(r, when=when[r.text]) if r.text in when and when[r.text] in _WHEN else r
        for r in model.requirements
    ]

    # 8. New must-haves — only ones chosen from suggestions (typed, never free text).
    for add in deltas.get("add_requirements") or ():
        text = (add.get("text") or "").strip()
        tier = add.get("tier") if add.get("tier") in _TIERS else "core"
        if text and all(r.text != text for r in requirements):
            requirements.append(Requirement(text, tier, Provenance(RECRUITER), hard=bool(add.get("hard"))))

    return replace(
        model, seniority=sen, location=loc, companies=comp,
        exclude_titles=exclude_titles, industries=industries, requirements=tuple(requirements),
    )
