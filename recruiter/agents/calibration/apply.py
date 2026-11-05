"""Apply the recruiter's refinement answers back into the RoleModel.

Pure: a new RoleModel out, never mutating the input. `answers` is keyed by
question id; `questions` is passed so structured payloads (the domain name)
are available.
  capability   : "keep" | "remove"  -> drop the capability group to widen
  retier       : {text: tier}       -> move a requirement between core/supporting/
                                       differentiator (the recruiter's call overrides
                                       the reader's guess — Option A editable brief)
  dealbreakers : [core texts]       -> mark those requirements hard (must-pass)
  priority     : [core texts]       -> reorder cores (top matters most)
  domain       : required|preferred|irrelevant -> industry filter / soft / drop
  disqualifiers: free text          -> model.disqualifiers (Judge negative evidence)
  specialization: a label           -> add as a SOFT core requirement (shapes
                                       judge/ranking toward e.g. Backend); never a
                                       hard keyword gate — that over-narrows on
                                       generic craft terms (the stack axis, a precise
                                       language, is where a hard filter belongs)
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Tuple

from recruiter.agents.intake.model import Question
from recruiter.agents.intake.specialization import is_any_stack, stack_terms
from recruiter.role_model import CapabilityGroup, Provenance, RECRUITER, Requirement, RoleModel
from recruiter.role_model.levels import off_track_titles

_TIERS = ("core", "supporting", "differentiator")


def apply_answers(model: RoleModel, answers: Dict[str, Any], questions: Tuple[Question, ...] = ()) -> RoleModel:
    requirements = list(model.requirements)
    capability_groups = model.capability_groups
    industries = list(model.industries)
    disqualifiers = list(model.disqualifiers)
    exclude_titles = list(model.exclude_titles)

    if answers.get("capability") == "remove":
        capability_groups = ()

    # Recruiter tier overrides FIRST, so dealbreakers/priority below see the final
    # tiers (e.g. a requirement moved into Core can then be ranked or made hard).
    retier = answers.get("retier") or {}
    if isinstance(retier, dict) and retier:
        requirements = [
            replace(r, tier=retier[r.text]) if r.text in retier and retier[r.text] in _TIERS else r
            for r in requirements
        ]

    dealbreakers = set(answers.get("dealbreakers") or [])
    if dealbreakers:
        requirements = [replace(r, hard=True) if r.text in dealbreakers else r for r in requirements]

    priority = answers.get("priority")
    if priority:
        order = {text: i for i, text in enumerate(priority)}
        cores = [r for r in requirements if r.tier == "core"]
        rest = [r for r in requirements if r.tier != "core"]
        cores.sort(key=lambda r: order.get(r.text, len(order)))
        requirements = cores + rest

    domain_answer = answers.get("domain")
    if domain_answer:
        domain_name = next((q.payload for q in questions if q.id == "domain" and q.payload), None)
        if domain_name:
            if domain_answer == "required" and domain_name not in industries:
                industries.append(domain_name)
            elif domain_answer == "preferred":
                requirements.append(
                    Requirement(f"{domain_name} domain", "differentiator", Provenance(RECRUITER))
                )

    specialization = answers.get("specialization")
    if specialization and str(specialization).strip():
        text = str(specialization).strip()
        if not any(r.text == text for r in requirements):
            requirements.append(Requirement(text, "core", Provenance(RECRUITER)))

    # A chosen stack is a PRECISE hard filter (verified whole-word keyword mechanism);
    # "Any stack is fine" filters nothing — silence never becomes a filter.
    stack = answers.get("stack")
    if stack and str(stack).strip() and not is_any_stack(stack):
        label = str(stack).strip()
        if not any(g.label == label for g in capability_groups):
            terms = stack_terms(label) or (label,)
            capability_groups = capability_groups + (
                CapabilityGroup(label, terms, "stack",
                                f"{label} named as the required stack — enforced as an any-of keyword filter."),
            )

    # (track) opt-in level tightening: add off-track titles to the exclude filter.
    track = answers.get("track")
    if track and str(track).lower().startswith("tighten"):
        for t in off_track_titles(model.role_level or ""):
            if t not in exclude_titles:
                exclude_titles.append(t)

    dq = answers.get("disqualifiers")
    if dq:
        items = dq if isinstance(dq, (list, tuple)) else [dq]
        disqualifiers.extend(str(i).strip() for i in items if str(i).strip())

    return replace(
        model,
        requirements=tuple(requirements),
        capability_groups=capability_groups,
        industries=tuple(industries),
        disqualifiers=tuple(disqualifiers),
        exclude_titles=tuple(exclude_titles),
    )
