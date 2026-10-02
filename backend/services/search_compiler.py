"""Phase 3 — the deterministic Hiring-Intent Compiler.

Input:  StructuredHiringIntent  +  capability map  +  role-family taxonomy
Output: a provider filter tree (hard filters only) + a per-constraint audit
        record (routing/provenance) + warnings.

No LLM. No provider call. Boring and deterministic: for each signal it looks up
the capability, applies the one approved transformation, and records how it was
routed. It NEVER broadens a filter, relaxes a requirement, invents a title, or
"simplifies" the recruiter's logic. A required constraint whose field is not
hard-filterable is routed to the judge or disclosed — never silently dropped and
never forced into an unverified hard filter.

Extraction preserves meaning; the compiler expands REPRESENTATION, never meaning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.models.structured_intent import StructuredHiringIntent
from backend.services import crustdata_capabilities as cap
from backend.services import role_family_taxonomy as tax

# Field sets for keyword skill retrieval by temporal relationship.
_CURRENT_SKILL_FIELDS = ["experience.employment_details.current.description", "basic_profile.headline", "basic_profile.summary"]
_PAST_SKILL_FIELDS = ["experience.employment_details.past.description", "experience.employment_details.past.title"]
_ANY_SKILL_FIELDS = ["experience.employment_details.description", "basic_profile.headline", "basic_profile.summary"]

_CUR_TITLE = "experience.employment_details.current.title"
_CUR_COMPANY = "experience.employment_details.current.company_name"
_PAST_COMPANY = "experience.employment_details.past.company_name"
_ANY_COMPANY = "experience.employment_details.company_name"
_HEADCOUNT = "experience.employment_details.current.company_headcount_latest"
_DEGREE = "education.schools.degree"
_STREAM = "education.schools.field_of_study"

_HARD_ROUTES = {"enforce", "enforce_with_warning", "enforce_but_not_verifiable"}


@dataclass
class CompiledConstraint:
    source: str
    strength: str
    route: str
    provider_fields: List[str] = field(default_factory=list)
    temporal: Optional[str] = None
    capability: Optional[str] = None
    note: str = ""


@dataclass
class CompiledPlan:
    filter_tree: Dict[str, Any]
    audit: List[CompiledConstraint]
    retrieval_title_family: List[str]
    taxonomy_version: str
    warnings: List[str] = field(default_factory=list)


def _leaf(f: str, t: str, v: Any) -> Dict[str, Any]:
    return {"field": f, "type": t, "value": v}


def _or(conds: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    conds = [c for c in conds if c]
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    return {"op": "or", "conditions": conds}


def _skill_fields(temporal: str) -> List[str]:
    return {"current": _CURRENT_SKILL_FIELDS, "past": _PAST_SKILL_FIELDS}.get(temporal, _ANY_SKILL_FIELDS)


def compile_intent(intent: StructuredHiringIntent) -> CompiledPlan:
    conditions: List[Dict[str, Any]] = []
    audit: List[CompiledConstraint] = []
    warnings: List[str] = []

    def hard_ok(field_name: str, strength: str) -> str:
        return cap.recommend_routing(field_name, strength)

    # --- location (single "City, State, Country" entry -> AND of country/state/city) ---
    if intent.location and intent.location.entries:
        entries = intent.location.entries
        if len(entries) == 1:
            parts = [p.strip() for p in entries[0].split(",") if p.strip()]
            if len(parts) == 3:
                city, state, country = parts
                conditions += [
                    _leaf("basic_profile.location.country", "in", [country]),
                    _leaf("basic_profile.location.state", "in", [state]),
                    _leaf("basic_profile.location.city", "in", [city]),
                ]
            else:  # fall back to city-level match on whatever was given
                conditions.append(_leaf("basic_profile.location.city", "in", [parts[0]]))
        else:
            cities = [e.split(",")[0].strip() for e in entries]
            conditions.append(_leaf("basic_profile.location.city", "in", cities))
        audit.append(CompiledConstraint("location", intent.location.strength, "provider_hard_filter",
                                        ["basic_profile.location.*"], note=f"entries={entries}"))

    # --- experience ---
    if intent.experience:
        if intent.experience.minimum_years is not None:
            conditions.append(_leaf("years_of_experience_raw", "=>", intent.experience.minimum_years))
        if intent.experience.maximum_years is not None:
            conditions.append(_leaf("years_of_experience_raw", "=<", intent.experience.maximum_years))
        audit.append(CompiledConstraint("experience", intent.experience.strength, "provider_hard_filter",
                                        ["years_of_experience_raw"]))

    # --- role family: expand source -> approved retrieval titles (taxonomy) ---
    retrieval_titles, used_tax, prov_notes = tax.expand_retrieval_titles(intent.role_family)
    title_group = _or([_leaf(_CUR_TITLE, "(.)", t) for t in retrieval_titles])
    if title_group:
        conditions.append(title_group)
    audit.append(CompiledConstraint("role_family", "required", "provider_hard_filter", [_CUR_TITLE],
                                    note="; ".join(prov_notes)))

    # --- seniority: handled at admission (level_fit), not a provider filter ---
    if intent.seniority:
        audit.append(CompiledConstraint("seniority", intent.seniority.strength, "admission_level_fit",
                                        [], note=f"value={intent.seniority.value}; enforced by Phase-1a admission gate"))

    # --- skills ---
    for s in intent.skills:
        fields = _skill_fields(s.relationship)
        probe = fields[0]
        route = hard_ok(probe, s.strength)
        if route in _HARD_ROUTES:
            grp = _or([_leaf(f, "(.)", s.name) for f in fields])
            if grp:
                conditions.append(grp)
            if route == "enforce_but_not_verifiable":
                warnings.append(f"skill {s.name!r}: filtered on response-gated text; not displayable from the provider")
            audit.append(CompiledConstraint(f"skill:{s.name}", s.strength, "provider_hard_filter",
                                            fields, temporal=s.relationship, capability=route))
        else:
            audit.append(CompiledConstraint(f"skill:{s.name}", s.strength, "downstream_evidence",
                                            fields, temporal=s.relationship, capability=route,
                                            note="preferred/unverified -> judge/context, no hard filter"))

    # --- skill_any_of groups ---
    for g in intent.skill_any_of:
        fields = _skill_fields(g.relationship)
        route = hard_ok(fields[0], g.strength)
        if route in _HARD_ROUTES:
            grp = _or([_leaf(f, "(.)", term) for term in g.any_of for f in fields])
            if grp:
                conditions.append(grp)
            audit.append(CompiledConstraint(f"skill_any_of:{'|'.join(g.any_of)}", g.strength,
                                            "provider_hard_filter", fields, temporal=g.relationship, capability=route))
        else:
            audit.append(CompiledConstraint(f"skill_any_of:{'|'.join(g.any_of)}", g.strength,
                                            "downstream_evidence", fields, temporal=g.relationship, capability=route))

    # --- company scale ---
    if intent.company_scale:
        cs = intent.company_scale
        field_name = _HEADCOUNT if cs.relationship == "current" else _HEADCOUNT  # only current headcount verified
        route = hard_ok(field_name, cs.strength)
        if route in _HARD_ROUTES:
            conditions.append(_leaf(field_name, "=>", cs.minimum_employees))
            allowed, warn = cap.can_hard_filter(field_name)
            if warn:
                warnings.append(warn)
            audit.append(CompiledConstraint("company_scale", cs.strength, "provider_hard_filter",
                                            [field_name], temporal=cs.relationship, capability=route,
                                            note="completeness unestablished; verify downstream where possible"))
        else:
            audit.append(CompiledConstraint("company_scale", cs.strength, "downstream_evidence",
                                            [field_name], temporal=cs.relationship, capability=route))

    # --- education ---
    if intent.education:
        if intent.education.degrees:
            route = hard_ok(_DEGREE, intent.education.strength)
            if route in _HARD_ROUTES:
                grp = _or([_leaf(_DEGREE, "(.)", d) for d in intent.education.degrees])
                if grp:
                    conditions.append(grp)
                audit.append(CompiledConstraint("education.degrees", intent.education.strength,
                                                "provider_hard_filter", [_DEGREE], capability=route))
        if intent.education.streams:
            route = hard_ok(_STREAM, intent.education.strength)
            if route in _HARD_ROUTES:
                grp = _or([_leaf(_STREAM, "(.)", s) for s in intent.education.streams])
                if grp:
                    conditions.append(grp)
                if route == "enforce_but_not_verifiable":
                    warnings.append("education stream: filterable but response-gated (not displayable); verify via Harvest if needed")
                audit.append(CompiledConstraint("education.streams", intent.education.strength,
                                                "provider_hard_filter", [_STREAM], capability=route))

    # --- companies (named) ---
    for c in intent.companies:
        field_name = {"current": _CUR_COMPANY, "past": _PAST_COMPANY}.get(c.relationship, _ANY_COMPANY)
        route = hard_ok(field_name, c.strength)
        if route in _HARD_ROUTES:
            conditions.append(_leaf(field_name, "in", [c.name]))
            audit.append(CompiledConstraint(f"company:{c.name}", c.strength, "provider_hard_filter",
                                            [field_name], temporal=c.relationship, capability=route))
        else:
            audit.append(CompiledConstraint(f"company:{c.name}", c.strength, "context_or_evidence",
                                            [field_name], temporal=c.relationship, capability=route,
                                            note="no verified provider preference mechanism -> context/evidence, not a filter"))

    # --- exclusions ---
    for x in intent.exclusions:
        if x.kind == "current_company":
            conditions.append(_leaf(_CUR_COMPANY, "not_in", [x.value]))
            audit.append(CompiledConstraint(f"exclude_current_company:{x.value}", "required",
                                            "provider_hard_filter", [_CUR_COMPANY]))
        elif x.kind == "title":
            conditions.append(_leaf(_CUR_TITLE, "(!)", x.value))
            audit.append(CompiledConstraint(f"exclude_title:{x.value}", "required",
                                            "provider_hard_filter", [_CUR_TITLE]))

    # --- evidence signals -> judge ---
    for e in intent.evidence_signals:
        audit.append(CompiledConstraint(f"evidence:{e.name}", e.strength, "downstream_evidence",
                                        [], note="verified by RequirementJudge; never a provider filter"))

    tree = {"op": "and", "conditions": conditions}
    return CompiledPlan(filter_tree=tree, audit=audit, retrieval_title_family=retrieval_titles,
                        taxonomy_version=tax.TAXONOMY_VERSION, warnings=warnings)


def canonicalize(tree: Dict[str, Any]) -> Any:
    """Order-insensitive canonical form of a boolean filter tree, so semantic
    equality can be asserted regardless of condition ordering."""
    if isinstance(tree, dict) and "op" in tree:
        children = sorted((canonicalize(c) for c in tree["conditions"]), key=lambda x: repr(x))
        return (tree["op"], tuple(children))
    return ("leaf", tree.get("field"), tree.get("type"), repr(tree.get("value")))


def semantic_diff(old_tree: Dict[str, Any], new_tree: Dict[str, Any]) -> List[str]:
    """Compare two provider filter trees at the leaf level and report what
    changed, in plain language — for shadow-mode review."""
    def leaves(tree, acc):
        if isinstance(tree, dict) and "op" in tree:
            for c in tree["conditions"]:
                leaves(c, acc)
        elif isinstance(tree, dict):
            acc.append((tree.get("field"), tree.get("type"), repr(tree.get("value"))))
        return acc
    old = set(leaves(old_tree, []))
    new = set(leaves(new_tree, []))
    out = []
    for f, t, v in sorted(old - new):
        out.append(f"REMOVED: {f} {t} {v}")
    for f, t, v in sorted(new - old):
        out.append(f"ADDED:   {f} {t} {v}")
    if not out:
        out.append("no leaf-level differences")
    return out
