"""Synthetic probes of the UNCHANGED compiler (offline; the only inputs are minimal hand-built intents or labelled overlays on frozen intents).

Every probe is a measurement: what does the compiler do with strength x relationship x omission, a multi-entry location, an unknown level, an
analogy title. Nothing here is a fix, and nothing here is an extraction result."""

from __future__ import annotations

import copy
import itertools
from typing import Any, Dict, List

from backend.experiments.compiler_contract import loader, signature as S
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.models.structured_intent import (CompanyReq, CompanyScale, SkillAnyOf, SkillReq, StructuredHiringIntent)
from backend.services import compiler_audit, crustdata_capabilities as cap
from backend.services.search_compiler import compile_intent

BASE: Dict[str, Any] = {"role_archetype": {"value": "hybrid", "confidence": 0.5, "rationale": "probe"}, "role_family": ["Probe Role"]}
STRENGTHS = ("required", "preferred", "context")
RELATIONSHIPS = ("current", "past", "any")


def mk(**kw) -> ExperimentalHiringIntent:
    return ExperimentalHiringIntent.model_validate({**copy.deepcopy(BASE), **kw})


def summarize(intent: StructuredHiringIntent) -> Dict[str, Any]:
    plan = compile_intent(intent)
    return {
        "leaves": [[f.split(".")[-1] if f.count(".") > 2 else f, t, v] for f, t, v in sorted(S.leaves(plan.filter_tree))],
        "leaf_count": len(S.leaves(plan.filter_tree)),
        "audit": [[c.source, c.strength, c.route, c.temporal, c.capability] for c in plan.audit],
        "warnings": plan.warnings,
        "normalizations": [n["normalization"] for n in plan.normalizations],
        "titles": plan.retrieval_title_family,
    }


def _hard(plan_summary: Dict[str, Any], extra_leaves_over_title: int = 1) -> int:
    """Provider leaves other than the one title leaf every probe has."""
    return plan_summary["leaf_count"] - extra_leaves_over_title


def strength_relationship_sweep() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for st, rel in itertools.product(STRENGTHS, RELATIONSHIPS):
        s = summarize(mk(skills=[{"name": "ProbeSkill", "strength": st, "relationship": rel}]))
        out.append({"construct": "skill", "strength": st, "relationship": rel, "hard_leaves": _hard(s), "audit": s["audit"][-1]})
        s = summarize(mk(skill_any_of=[{"any_of": ["ProbeA", "ProbeB"], "strength": st, "relationship": rel}]))
        out.append({"construct": "skill_any_of", "strength": st, "relationship": rel, "hard_leaves": _hard(s), "audit": s["audit"][-1]})
        s = summarize(mk(companies=[{"name": "ProbeCo", "strength": st, "relationship": rel}]))
        out.append({"construct": "company", "strength": st, "relationship": rel, "hard_leaves": _hard(s), "audit": s["audit"][-1]})
        s = summarize(mk(company_scale={"minimum_employees": 1000, "strength": st, "relationship": rel}))
        out.append({"construct": "company_scale", "strength": st, "relationship": rel, "hard_leaves": _hard(s), "audit": s["audit"][-1]})
    for st in STRENGTHS:
        s = summarize(mk(experience={"minimum_years": 5, "maximum_years": 9, "strength": st}))
        out.append({"construct": "experience", "strength": st, "relationship": None, "hard_leaves": _hard(s), "audit": s["audit"][-1] if len(s["audit"]) > 1 else None})
        s = summarize(mk(location={"entries": ["Hyderabad, Telangana, India"], "strength": st}))
        out.append({"construct": "location", "strength": st, "relationship": None, "hard_leaves": _hard(s), "audit": s["audit"][-1] if len(s["audit"]) > 1 else None})
        s = summarize(mk(seniority={"value": "Senior", "strength": st}))
        out.append({"construct": "seniority", "strength": st, "relationship": None, "hard_leaves": _hard(s), "audit": s["audit"][-1]})
        s = summarize(mk(education={"degrees": ["Bachelor's degree"], "streams": ["Finance"], "strength": st}))
        out.append({"construct": "education(degree+stream)", "strength": st, "relationship": None, "hard_leaves": _hard(s),
                    "audit": next((a for a in s["audit"] if a[0] == "education"), None)})
        s = summarize(mk(education={"degrees": ["Bachelor's degree"], "strength": st}))
        out.append({"construct": "education(degree only)", "strength": st, "relationship": None, "hard_leaves": _hard(s),
                    "audit": next((a for a in s["audit"] if a[0] == "education"), None)})
        s = summarize(mk(evidence_signals=[{"name": "probe signal", "strength": st}]))
        out.append({"construct": "evidence_signal", "strength": st, "relationship": None, "hard_leaves": _hard(s), "audit": s["audit"][-1]})
    return out


def relationship_omission() -> Dict[str, Any]:
    """Questions A-E of the brief, answered with the production models and the unchanged compiler."""
    omitted = SkillReq(name="SQL")
    explicit = SkillReq(name="SQL", relationship="current")
    any_ = SkillReq(name="SQL", relationship="any")

    def base_with(sk):
        return StructuredHiringIntent.model_validate({**BASE, "skills": [sk.model_dump()]})

    s_omit, s_exp, s_any = (summarize(base_with(x)) for x in (omitted, explicit, any_))
    scale_omit = CompanyScale(minimum_employees=1000)
    group_omit = SkillAnyOf(any_of=["A", "B"])
    company_omit = CompanyReq(name="Acme")
    # exercise the experimental subclass too
    xo = ExperimentalHiringIntent.model_validate({**BASE, "skills": [{"name": "SQL"}]})
    xe = ExperimentalHiringIntent.model_validate({**BASE, "skills": [{"name": "SQL", "relationship": "current"}]})
    return {
        "defaults": {"SkillReq": omitted.relationship, "SkillAnyOf": group_omit.relationship, "CompanyReq": company_omit.relationship,
                     "CompanyScale": scale_omit.relationship},
        "model_fields_set_omitted": sorted(omitted.model_fields_set),
        "model_fields_set_explicit_current": sorted(explicit.model_fields_set),
        "omitted_equals_explicit_current_after_validation": omitted.model_dump() == explicit.model_dump(),
        "compiled_output_identical_omitted_vs_explicit_current": (s_omit["leaves"], s_omit["audit"]) == (s_exp["leaves"], s_exp["audit"]),
        "intent_hash_identical_omitted_vs_explicit_current": compiler_audit.intent_hash(xo) == compiler_audit.intent_hash(xe),
        "A_explicit_current_required": {"hard_leaves": _hard(s_exp), "audit": s_exp["audit"][-1], "fields": [l[0] for l in s_exp["leaves"][:4]]},
        "B_explicit_any_required": {"hard_leaves": _hard(s_any), "audit": s_any["audit"][-1]},
        "C_D_omitted_required": {"hard_leaves": _hard(s_omit), "audit": s_omit["audit"][-1]},
        "E_omitted_required_creates_hard_filter": _hard(s_omit) > 0,
        "compiler_can_distinguish_omitted_from_explicit_current": False,
    }


def seniority_probes() -> List[Dict[str, Any]]:
    from backend.services import candidate_evidence_builder as ceb
    import json
    from pathlib import Path
    known = json.loads((Path(cap.__file__).resolve().parents[1] / "knowledge" / "seniority.json").read_text(encoding="utf-8"))
    out = []
    for v in ("Staff", "Senior Manager", "Principal Engineer", "Lead", "Senior", "Head of Finance"):
        s = summarize(mk(seniority={"value": v, "strength": "required"}))
        row = next(a for a in s["audit"] if a[0] == "seniority")
        marker = ceb._level_marker(v)  # read-only call of the downstream consumer's level reader
        out.append({"value": v, "compiler_carries_value_verbatim": f"value={v};" in (next(c.note for c in compile_intent(mk(seniority={"value": v, "strength": "required"})).audit if c.source == "seniority")),
                    "audit_route": row[2], "downstream_level_marker": list(marker) if marker else None,
                    "in_seniority_json": any(v.lower() == k or v.lower() in [x.lower() for x in vs] for k, vs in known.items())})
    return out


def title_probes() -> List[Dict[str, Any]]:
    out = []
    for titles in (["Data Analyst"], ["Software Engineer"], ["Solution Architect"], ["FP&A and Business Finance Manager"],
                   ["Software Engineer", "Solution Architect", "Forward Deployed Engineer"]):
        i = mk(role_family=titles)
        p = compile_intent(i)
        out.append({"role_family": titles, "retrieval_titles": p.retrieval_title_family, "title_leaf_count": len(p.retrieval_title_family),
                    "audit_note": next(c.note for c in p.audit if c.source == "role_family")})
    return out


def location_probes() -> List[Dict[str, Any]]:
    cases = {
        "one_entry_3part": {"entries": ["Hyderabad, Telangana, India"]},
        "one_entry_2part": {"entries": ["Hyderabad, India"]},
        "one_entry_city_only": {"entries": ["Hyderabad"]},
        "two_entries_3part": {"entries": ["Hyderabad, Telangana, India", "Pune, Maharashtra, India"]},
        "alias_entry": {"entries": ["Bangalore, Karnataka, India"]},
        "countries_only": {"countries": ["India"]},
        "countries_plus_remote_allowed": {"countries": ["India"], "remote": "allowed"},
        "work_mode_only": {"work_mode": "hybrid"},
        "entry_plus_hybrid": {"entries": ["Hyderabad, Telangana, India"], "work_mode": "hybrid"},
    }
    out = []
    for name, loc in cases.items():
        s = summarize(mk(location={"strength": "required", **loc}))
        out.append({"case": name, "location": loc, "leaves": [[l[0], l[1], l[2]] for l in s["leaves"] if "location" in l[0] or l[0] in ("city", "state", "country")],
                    "audit_sources": [a[0] for a in s["audit"]], "normalizations": s["normalizations"]})
    return out


def exclusion_probes() -> Dict[str, Any]:
    sem = summarize(mk(semantic_exclusions=[{"concept": "security operations work", "includes": ["SOC", "SIEM"]}]))
    ctl = summarize(mk(exclusions=[{"kind": "exclude_title", "value": "Security Analyst"}, {"kind": "exclude_past_company", "value": "Acme"}]))
    return {"semantic_exclusion_leaves_beyond_title": _hard(sem), "semantic_exclusion_audit_rows": [a[0] for a in sem["audit"]],
            "semantic_exclusion_creates_negative_leaf": any(l[1] in ("(!)", "not_in") for l in sem["leaves"]),
            "control_explicit_exclusions_leaves": [[l[1], l[2]] for l in ctl["leaves"] if l[1] in ("(!)", "not_in")]}


def descriptive_term_probe() -> Dict[str, Any]:
    """A group term that DESCRIBES a class ('Similar BI/reporting platform') becomes a literal whole-word phrase if the group routes to the provider."""
    s = summarize(mk(skill_any_of=[{"any_of": ["Power BI", "Similar business intelligence/reporting platform"], "strength": "required", "relationship": "current"}]))
    return {"literal_phrase_leaves": [l[2] for l in s["leaves"] if "Similar" in l[2]], "leaf_count": s["leaf_count"]}


def capability_notes() -> Dict[str, Any]:
    any_fields = ["experience.employment_details.description", "basic_profile.headline", "basic_profile.summary"]
    return {f: {"filter_status": cap.get(f).filter_status, "in_map": f in cap._MAP, "downstream_verifiable": cap.get(f).downstream_verifiable,
                "route_required": cap.recommend_routing(f, "required")} for f in any_fields + ["work_mode",
            "experience.employment_details.current.description"]}


def role2_overlay(n: int = 1) -> Dict[str, Any]:
    """LABELLED SYNTHETIC OVERLAY, not an extraction result: the stored Role 2 intent plus the three facts `ROLE2_GROUND_TRUTH.md` states and the
    stored (pre-`advanced`, pre-`work_mode`) schema could not carry: Python/Java `advanced`, Hybrid, seniority Staff."""
    d = loader.load_intent("R2", n).model_dump()
    for s in d["skills"]:
        if s["name"].strip().lower() in ("python", "java"):
            s["proficiency"] = "advanced"
    d["location"]["work_mode"] = "hybrid"
    d["seniority"] = {"value": "Staff", "strength": "required", "basis": None, "leadership": [], "alternatives": []}
    ov = ExperimentalHiringIntent.model_validate(d)
    return {"overlay": ["Python/Java proficiency=advanced", "location.work_mode=hybrid", "seniority=Staff"], "intent": ov}
