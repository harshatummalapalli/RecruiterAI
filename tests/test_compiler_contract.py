"""Compiler CONTRACT tests (offline; no model, no provider). See backend/services/COMPILER_CONTRACT.md.

    If intent means X, the compiler must enforce X, route X downstream / to context, normalize X deterministically, or declare X unresolved.
    It must never silently discard X.

Matrix A-O of the hardening brief, plus backward compatibility with the production-shaped anchors."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from backend.experiments.compiler_contract import hardened_verify, loader
from backend.experiments.compiler_contract import legacy_compiler_v1 as legacy
from backend.experiments.compiler_contract.paths import path_intent
from backend.experiments.compiler_contract.signature import leaves
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.models.structured_intent import CompanyScale, SkillAnyOf, SkillReq, StructuredHiringIntent, parse_structured_intent
from backend.services import compiler_audit as audit
from backend.services.search_compiler import FATES, _intent_records_provenance, canonicalize
from backend.services.search_compiler import compile_intent as _compile_intent
from backend.services.source_provenance import SourceTexts

# An intent that records provenance names its role in a source text; the runtime passes that text to the compiler. A legacy intent (no provenance anywhere) is compiled
# without one, exactly as before.
def _quotes(x, acc):
    if isinstance(x, dict):
        if isinstance(x.get("basis"), dict) and x["basis"].get("quote"):
            acc.append(x["basis"]["quote"])
        for v in x.values():
            _quotes(v, acc)
    elif isinstance(x, list):
        for v in x:
            _quotes(v, acc)
    return acc


def source_for(intent) -> SourceTexts:
    """A faithful source for a synthetic intent: it states the role and contains every quote the intent cites (these tests exercise mechanics; the
    verification of an unfaithful quote is tested on its own)."""
    return SourceTexts(jd="We are hiring a Probe Role at a company with 100 employees. " + " ".join(_quotes(intent.model_dump(), [])))


def compile_intent(intent):
    return _compile_intent(intent, source_for(intent) if _intent_records_provenance(intent) else None)


GOLDEN = Path(__file__).parent / "fixtures" / "structured_intent"
BASE = {"role_archetype": {"value": "hybrid", "confidence": 0.5, "rationale": "t"}, "role_family": ["Probe Role"]}


def mk(**kw) -> ExperimentalHiringIntent:
    return ExperimentalHiringIntent.model_validate({**copy.deepcopy(BASE), **kw})


# The default quote states every QUALIFIER these mechanics tests exercise (a present / past use, a depth, a distance, a work arrangement), so that a claim in an
# intent is SUPPORTED by its cited source. Qualifier support is tested on its own (tests/test_downstream_consumers.py, matrix A-F).
SUPPORTING_QUOTE = "currently and previously worked on this, hands-on and advanced, 5 to 9 years, 25 miles, remote or hybrid or onsite"


def basis(sources=("jd",), quote=SUPPORTING_QUOTE):
    return {"sources": list(sources), "quote": quote}


def L(plan):
    return leaves(plan.filter_tree)


def fields(plan):
    return {l[0] for l in L(plan)}


def atom(plan, concept, value=None, scope=None):
    out = [a for a in plan.atom_audit if a.concept == concept and (value is None or a.value == value) and (scope is None or a.scope == scope)]
    assert out, f"no atom record for {concept} {value} in {[ (a.concept, a.value) for a in plan.atom_audit]}"
    return out[0]


def row(plan, source):
    return next(c for c in plan.audit if c.source == source)


# --- A. provenance prevents invented hard filters -------------------------------------------------------------------------


def test_A_a_state_the_source_does_not_state_is_never_a_provider_filter():
    p = compile_intent(mk(location={"entries": ["Hyderabad, Telangana, India"], "strength": "required",
                                    "basis": basis(quote="Location: Hyderabad, India")}))
    f = {(l[0].split(".")[-1], l[2]) for l in L(p)}
    assert ("city", '["Hyderabad"]') in f and ("country", '["India"]') in f
    assert not any(l[0].endswith("location.state") for l in L(p))
    a = atom(p, "location.entry")
    assert a.fate == "ENFORCED"
    state = next(c for c in a.components if c["component"] == "state")
    assert state["fate"] == "DROPPED_WITH_JUSTIFICATION" and "never a provider filter" in state["justification"]


def test_A_a_state_the_source_states_is_enforced():
    p = compile_intent(mk(location={"entries": ["Hyderabad, Telangana, India"], "strength": "required",
                                    "basis": basis(quote="Location: Hyderabad, Telangana")}))
    assert any(l[0].endswith("location.state") and "Telangana" in l[2] for l in L(p))
    assert not any(l[0].endswith("location.country") for l in L(p))     # India is not in this source text


def test_A_an_intent_with_no_recorded_provenance_keeps_its_legacy_behaviour():
    p = compile_intent(mk(location={"entries": ["Hyderabad, Telangana, India"], "strength": "required"}))
    assert {l[0].split(".")[-1] for l in L(p)} == {"country", "state", "city", "title"}
    assert atom(p, "location.entry").provenance["state"] == "unrecorded"


@pytest.mark.parametrize("kw,leaf_field", [
    ({"skills": [{"name": "Rust", "strength": "required", "relationship": "current", "basis": basis(("inferred",))}]}, "description"),
    ({"skill_any_of": [{"any_of": ["A", "B"], "strength": "required", "relationship": "current", "basis": basis(("inferred",))}]}, "description"),
    ({"companies": [{"name": "Acme", "strength": "required", "relationship": "current", "basis": basis(("inferred",))}]}, "company_name"),
    ({"experience": {"minimum_years": 9, "strength": "required", "basis": basis(("inferred",))}}, "years_of_experience_raw"),
    ({"education": {"degrees": ["B.Tech"], "streams": ["CS"], "strength": "required", "basis": basis(("inferred",))}}, "education.schools.degree"),
    ({"location": {"entries": ["Pune, Maharashtra, India"], "strength": "required", "basis": basis(("inferred",))}}, "location.city"),
    ({"exclusions": [{"kind": "exclude_past_company", "value": "Acme", "basis": basis(("inferred",))}]}, "company_name"),
])
def test_A_model_only_inference_is_never_a_hard_provider_filter(kw, leaf_field):
    p = compile_intent(mk(**kw))
    assert not any(leaf_field in l[0] for l in L(p)), L(p)
    assert all(a.fate != "ENFORCED" or a.concept == "role_family" for a in p.atom_audit)
    assert hardened_verify.invented_model_only_hard_filters(mk(**kw), p) == []


def test_A_nothing_is_invented_for_a_bare_intent():
    p = compile_intent(mk())
    assert [l[0] for l in L(p)] == ["experience.employment_details.current.title"]       # no company, radius, experience, seniority or title alternative
    assert not any(c.route == "admission_level_fit" for c in p.audit)


def test_A_an_approved_normalization_is_still_applied():
    p = compile_intent(mk(location={"entries": ["Bangalore, Karnataka, India"], "strength": "required", "basis": basis(quote="Bangalore, Karnataka, India")}))
    assert any(l[2] == '["Bengaluru"]' for l in L(p)) and atom(p, "location.entry").fate == "NORMALIZED"


# --- B / C. relationship ------------------------------------------------------------------------------------------------------


def test_B_the_default_relationship_is_unspecified_not_current():
    assert SkillReq(name="SQL").relationship is None and SkillAnyOf(any_of=["A", "B"]).relationship is None and CompanyScale(minimum_employees=10).relationship is None
    s = parse_structured_intent(json.dumps({**BASE, "skills": [{"name": "SQL"}]}))
    assert s.skills[0].relationship is None
    with pytest.raises(Exception):
        SkillReq(name="SQL", relationship="sometimes")


def test_B_an_omitted_relationship_is_not_a_current_hard_filter():
    p = compile_intent(parse_structured_intent(json.dumps({**BASE, "skills": [{"name": "SQL"}], "skill_any_of": [{"any_of": ["A", "B"]}]})))
    assert [l[0] for l in L(p)] == ["experience.employment_details.current.title"]
    for src in ("skill:SQL", "skill_any_of:A|B"):
        r = row(p, src)
        assert r.route == "downstream_evidence" and r.temporal is None and r.capability == "unspecified_relationship"
    a = atom(p, "skill", "SQL")
    assert a.fate == "VERIFIED_DOWNSTREAM" and a.relationship is None and "never defaulted to current" in a.justification


def test_B_an_omitted_company_scale_relationship_is_unresolved_not_current():
    p = compile_intent(mk(company_scale={"minimum_employees": 5000, "strength": "required"}))
    assert not any("headcount" in l[0] for l in L(p))
    assert atom(p, "company_scale").fate == "UNRESOLVED"


def test_B_the_extractor_does_not_invent_current_when_it_collapses_a_group():
    from backend.services.structured_intent_extractor import _normalize
    out = _normalize({"skills": [], "skill_any_of": [{"any_of": ["Only"], "strength": "required"}]})
    assert "relationship" not in out["skills"][0]
    out = _normalize({"skills": [], "skill_any_of": [{"any_of": ["Only"], "relationship": "past"}]})
    assert out["skills"][0]["relationship"] == "past"


def test_C_an_explicit_current_still_means_current_exactly_as_before():
    it = mk(skills=[{"name": "SQL", "strength": "required", "relationship": "current"}])
    new, old = compile_intent(it), legacy.compile_intent(it)
    assert canonicalize(new.filter_tree) == canonicalize(old.filter_tree)
    assert row(new, "skill:SQL").capability == "enforce_but_not_verifiable" and atom(new, "skill", "SQL").fate == "ENFORCED"


def test_C_past_and_any_are_distinct_from_current_and_unspecified():
    p = compile_intent(mk(skills=[{"name": "A", "strength": "required", "relationship": "past"}, {"name": "B", "strength": "required", "relationship": "any"}]))
    assert atom(p, "skill", "A").fate == "ENFORCED" and any("past" in l[0] for l in L(p))
    assert atom(p, "skill", "B").fate == "VERIFIED_DOWNSTREAM" and not any(l[2] == '"B"' for l in L(p))


# --- D / E / F. strength ------------------------------------------------------------------------------------------------------

_STRENGTH_CASES = {
    "skill": lambda s: {"skills": [{"name": "X", "strength": s, "relationship": "current", "basis": basis()}]},
    "skill_any_of": lambda s: {"skill_any_of": [{"any_of": ["X", "Y"], "strength": s, "relationship": "current", "basis": basis()}]},
    "company": lambda s: {"companies": [{"name": "Acme", "strength": s, "relationship": "current", "basis": basis()}]},
    "company_scale": lambda s: {"company_scale": {"minimum_employees": 100, "strength": s, "relationship": "current"}},
    "education": lambda s: {"education": {"degrees": ["B.Tech"], "streams": ["CS"], "strength": s, "basis": basis()}},
    "experience": lambda s: {"experience": {"minimum_years": 5, "maximum_years": 9, "strength": s, "basis": basis()}},
    "location": lambda s: {"location": {"entries": ["Pune, Maharashtra, India"], "strength": s, "basis": basis(quote="Pune, Maharashtra, India")}},
}


@pytest.mark.parametrize("construct", sorted(_STRENGTH_CASES))
def test_D_required_preferred_and_context_are_distinct(construct):
    plans = {s: compile_intent(mk(**_STRENGTH_CASES[construct](s))) for s in ("required", "preferred", "context")}
    n = {s: len(L(p)) - 1 for s, p in plans.items()}               # leaves besides the title leaf
    assert n["required"] > 0 and n["preferred"] == 0 and n["context"] == 0
    for s in ("preferred", "context"):
        assert all(a.strength in (None, s) or a.concept == "role_family" for a in plans[s].atom_audit)
        assert not any(a.fate in ("ENFORCED", "NORMALIZED") for a in plans[s].atom_audit if a.concept != "role_family")


@pytest.mark.parametrize("construct", sorted(_STRENGTH_CASES))
def test_E_preferred_never_becomes_required(construct):
    p = compile_intent(mk(**_STRENGTH_CASES[construct]("preferred")))
    assert not any(a.fate == "ENFORCED" for a in p.atom_audit if a.concept != "role_family")
    assert not any(c.route == "provider_hard_filter" for c in p.audit if c.source != "role_family")
    assert all(a.fate in ("PREFERENCE_CONTEXT", "UNRESOLVED") for a in p.atom_audit if a.concept != "role_family" and a.kind == "MEANING")


@pytest.mark.parametrize("construct", sorted(_STRENGTH_CASES))
def test_F_context_never_becomes_required_or_a_candidate_filter(construct):
    p = compile_intent(mk(**_STRENGTH_CASES[construct]("context")))
    assert not any(c.route == "provider_hard_filter" for c in p.audit if c.source != "role_family")
    assert not any(a.fate == "ENFORCED" for a in p.atom_audit if a.concept != "role_family")
    assert any(a.strength == "context" for a in p.atom_audit)          # the strength is preserved, not rewritten


def test_E_a_preferred_education_is_no_longer_invisible():
    p = compile_intent(mk(**_STRENGTH_CASES["education"]("preferred")))
    r = row(p, "education")
    assert r.route == "context_or_evidence" and all(atom(p, c, v).fate == "PREFERENCE_CONTEXT" for c, v in (("education.degree", "B.Tech"), ("education.stream", "CS")))


# --- G / H. sourcing paths ----------------------------------------------------------------------------------------------------


def _paths_intent():
    return mk(
        experience={"minimum_years": 3, "strength": "required", "basis": basis(("jd",), "3+ years of experience")},
        skills=[{"name": "SQL", "strength": "required", "relationship": "any", "basis": basis(("jd", "recruiter_brief"))},
                {"name": "Power Query", "strength": "required", "relationship": "any", "basis": basis(("jd",))}],
        sourcing_paths=[
            {"id": "PATH A", "label": "domain led", "strategy": "domain_led", "location": {"countries": ["India"], "remote": "allowed", "strength": "required",
             "basis": basis(("recruiter_brief",), "India-wide, remote acceptable")},
             "skills": [{"name": "Power Query", "strength": "preferred", "relationship": "any", "basis": basis(("recruiter_brief",))}]},
            {"id": "PATH B", "label": "capability led", "strategy": "capability_led",
             "experience": {"minimum_years": 6, "strength": "required", "basis": basis(("recruiter_brief",), "6+ years")},
             "location": {"entries": ["Hyderabad, Telangana, India", "Pune, Maharashtra, India"], "strength": "required", "basis": basis(("recruiter_brief",), "Hyderabad OR Pune")}},
        ])


def test_G_sourcing_paths_compile_to_independent_plans():
    p = compile_intent(_paths_intent())
    assert [c.path_id for c in p.paths] == ["PATH A", "PATH B"] and p.filter_tree["op"] == "or" and len(p.filter_tree["conditions"]) == 2
    a, b = (leaves(c.filter_tree) for c in p.paths)
    assert a != b
    assert {c.scope for c in p.audit} == {"path:PATH A", "path:PATH B"}
    assert [x.fate for x in p.atom_audit if x.concept == "sourcing_path"] == ["ENFORCED", "ENFORCED"]
    assert [x.strategy for x in p.paths] == ["domain_led", "capability_led"]


def test_H_path_requirements_do_not_leak():
    p = compile_intent(_paths_intent())
    a, b = ({(l[0].split(".")[-1], l[1], l[2]) for l in leaves(c.filter_tree)} for c in p.paths)
    assert ("years_of_experience_raw", "=>", "6") not in a and ("years_of_experience_raw", "=>", "3") in a      # A inherits the GLOBAL 3, never B's 6
    assert ("years_of_experience_raw", "=>", "6") in b and ("years_of_experience_raw", "=>", "3") not in b       # B's 6 REPLACES the global 3
    assert not any(x[0] == "city" for x in a) and not any(x[0] == "country" and x[2] == '["India"]' for x in b)     # Path B geography is not A's, and vice versa
    assert any(x[0] == "country" and x[2] == '["India"]' for x in a) and any(x[0] == "city" and "Pune" in x[2] for x in b)


def test_H_a_path_waiver_is_per_path_in_the_checklists():
    p = compile_intent(_paths_intent())
    ca = dict((t, tier) for tier, t in audit.judge_checklist(p, "PATH A"))
    cb = dict((t, tier) for tier, t in audit.judge_checklist(p, "PATH B"))
    assert cb["Power Query"] == "core" and ca["Power Query"] == "supporting"      # waived (preferred) on A, required on B
    with pytest.raises(ValueError):
        audit.judge_checklist(p)                                                  # a multi-path plan has no single checklist


def test_H_global_atoms_overridden_in_every_path_are_justified_not_silent():
    p = compile_intent(_paths_intent())
    ex = atom(p, "experience.min", "3+ years", "global")
    assert ex.fate == "ENFORCED" and "PATH A" in ex.destination                   # inherited by A, overridden in B
    pq = atom(p, "skill", "Power Query", "global")
    assert pq.fate == "VERIFIED_DOWNSTREAM" and "PATH B" in pq.destination


def test_H_inheritance_equals_the_frozen_effective_view_on_the_real_role1_intents():
    for n in range(1, 6):
        it = loader.load_intent("R1", n)
        src = loader.sources_for("R1")
        plan = _compile_intent(it, src)
        for cp in plan.paths:
            frozen = _compile_intent(path_intent(it, cp.path_id), src)
            assert canonicalize(cp.filter_tree) == canonicalize(frozen.filter_tree), (n, cp.path_id)


def test_H_role1_path_constraints_stay_path_specific():
    for n in range(2, 6):          # run 1's intake put 6+ years in the GLOBAL intent (an extraction error); runs 2-5 state it on Path B only
        plan = compile_intent(loader.load_intent("R1", n))
        a, b = ({(l[0].split(".")[-1], l[2]) for l in leaves(c.filter_tree)} for c in plan.paths)
        assert ("years_of_experience_raw", "6") in b and ("years_of_experience_raw", "6") not in a
        assert ("city", '["Hyderabad", "Pune"]') in b and ("city", '["Hyderabad", "Pune"]') not in a
        assert ("country", '["India"]') in a and ("country", '["India"]') not in b
        pa = dict((t, tier) for tier, t in audit.judge_checklist(plan, "PATH A"))
        pb = dict((t, tier) for tier, t in audit.judge_checklist(plan, "PATH B"))
        assert pb["Power Query"] == "core" and pa.get("Power Query", "supporting") != "core"      # waived (absent, or only preferred) on A
        loc_a = atom(plan, "location.remote", scope="path:PATH A")
        assert loc_a.fate == "PREFERENCE_CONTEXT" and loc_a.value == "allowed"


# --- I. semantic exclusions ---------------------------------------------------------------------------------------------------


def test_I_semantic_exclusions_stay_semantic():
    it = mk(semantic_exclusions=[{"concept": "security operations work", "includes": ["SOC", "SIEM"], "basis": basis(("recruiter_brief",))}])
    p = compile_intent(it)
    assert not any(l[1] in ("(!)", "not_in") for l in L(p)) and [l[0] for l in L(p)] == ["experience.employment_details.current.title"]
    r = row(p, "semantic_exclusion:security operations work")
    assert r.route == "downstream_exclusion" and "never a company or title filter" in r.note
    assert audit.exclusion_checklist(p) == ["security operations work"]
    assert all("security operations" not in t for _tier, t in audit.judge_checklist(p))          # a negative is never a positive requirement
    assert atom(p, "semantic_exclusion").fate == "VERIFIED_DOWNSTREAM"
    assert audit.build_audit_record(it, p)["downstream_exclusions"] == ["security operations work"]


def test_I_an_explicit_company_exclusion_is_still_a_provider_filter_and_distinct():
    p = compile_intent(mk(exclusions=[{"kind": "exclude_past_company", "value": "Acme", "basis": basis()}]))
    assert any(l[1] == "not_in" for l in L(p)) and atom(p, "exclusion.exclude_past_company").fate == "ENFORCED"


def test_I_an_unsupported_exclusion_kind_is_unresolved_not_dropped():
    p = compile_intent(mk(exclusions=[{"kind": "exclude_industry", "value": "Gambling"}]))
    assert atom(p, "exclusion.exclude_industry").fate == "UNRESOLVED" and not any(l[1] in ("(!)", "not_in") for l in L(p))


# --- J. proficiency -----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("level,text", [("working_knowledge", "working knowledge of Power BI"), ("hands_on", "hands-on Power BI"),
                                        ("advanced", "advanced proficiency in Power BI")])
def test_J_proficiency_is_routed_verbatim_not_dropped(level, text):
    p = compile_intent(mk(skills=[{"name": "Power BI", "strength": "required", "relationship": "any", "proficiency": level, "basis": basis()}]))
    a = atom(p, "skill.proficiency")
    assert a.fate == "VERIFIED_DOWNSTREAM" and a.proficiency == level
    assert text in [t for _tier, t in audit.judge_checklist(p)]
    assert row(p, f"proficiency:Power BI={level}").route == "downstream_evidence"


def test_J_proficiency_is_not_provider_enforced_even_on_a_hard_filtered_skill():
    p = compile_intent(mk(skills=[{"name": "Python", "strength": "required", "relationship": "current", "proficiency": "advanced", "basis": basis()}]))
    assert atom(p, "skill", "Python").fate == "ENFORCED" and atom(p, "skill.proficiency").fate == "VERIFIED_DOWNSTREAM"
    assert not any("advanced" in l[2].lower() for l in L(p))


def test_J_a_preferred_skills_proficiency_is_a_preference():
    p = compile_intent(mk(skills=[{"name": "Go", "strength": "preferred", "relationship": "any", "proficiency": "hands_on"}]))
    assert atom(p, "skill.proficiency").fate == "PREFERENCE_CONTEXT"


# --- K. work mode -------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["remote", "hybrid", "onsite"])
def test_K_work_mode_is_not_silently_dropped_and_not_remapped(mode):
    p = compile_intent(mk(location={"entries": ["Hyderabad, India"], "work_mode": mode, "strength": "required", "basis": basis(quote=f"Hyderabad, India, {mode}")}))
    a = atom(p, "location.work_mode")
    assert a.fate == "UNRESOLVED" and a.value == mode and "never converted to another mode" in a.justification
    r = row(p, "location.work_mode")
    assert r.route == "disclose" and f"work_mode={mode}" in r.note
    assert any("work_mode" in w and mode in w for w in p.warnings)
    others = {"remote", "hybrid", "onsite"} - {mode}
    assert not any(f"work_mode={o}" in r.note for o in others)


def test_K_work_mode_is_separate_from_geography():
    a = compile_intent(mk(location={"entries": ["Hyderabad, India"], "strength": "required", "basis": basis(quote="Hyderabad, India")}))
    b = compile_intent(mk(location={"entries": ["Hyderabad, India"], "work_mode": "hybrid", "strength": "required", "basis": basis(quote="Hyderabad, India")}))
    assert L(a) == L(b)


def test_K_a_preferred_work_mode_is_context():
    p = compile_intent(mk(location={"work_mode": "hybrid", "strength": "preferred"}))
    assert atom(p, "location.work_mode").fate == "PREFERENCE_CONTEXT"


# --- L. seniority -------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["Staff", "Senior Manager", "Principal Engineer", "Head of Finance"])
def test_L_an_unknown_level_is_preserved_and_unresolved_never_remapped(level):
    p = compile_intent(mk(seniority={"value": level, "strength": "required"}))
    a = atom(p, "seniority.value")
    assert a.fate == "UNRESOLVED" and a.value == level and "never remapped" in a.justification
    r = row(p, "seniority")
    assert r.route == "admission_level_fit" and f"value={level};" in r.note
    assert [l[0] for l in L(p)] == ["experience.employment_details.current.title"]


@pytest.mark.parametrize("level", ["Senior", "Lead", "Junior", "Mid"])
def test_L_a_known_level_is_verified_downstream(level):
    assert atom(compile_intent(mk(seniority={"value": level, "strength": "required"})), "seniority.value").fate == "VERIFIED_DOWNSTREAM"


def test_L_alternatives_and_leadership_are_routed():
    p = compile_intent(mk(seniority={"value": "Lead", "strength": "required", "alternatives": ["Senior", "Staff"], "leadership": ["people", "technical"]}))
    assert atom(p, "seniority.alternatives", "Senior").fate == "VERIFIED_DOWNSTREAM" and atom(p, "seniority.alternatives", "Staff").fate == "UNRESOLVED"
    assert {a.value for a in p.atom_audit if a.concept == "seniority.leadership"} == {"people", "technical"}
    assert "People leadership or technical leadership" in [t for _tier, t in audit.judge_checklist(p)]


# --- M. reconciliation --------------------------------------------------------------------------------------------------------

JDQ = "Working knowledge of Power Query for data transformation and reporting."


def _recon_intent(action="waived", path_id=None, sources=("jd",), strength="required", topic="Power Query requirement"):
    return mk(
        skills=[{"name": "Power Query", "strength": strength, "relationship": "any", "basis": basis(sources, JDQ)}],
        sourcing_paths=[{"id": "PATH A", "label": "a", "strategy": "domain_led"}, {"id": "PATH B", "label": "b", "strategy": "capability_led"}],
        reconciliations=[{"topic": topic, "action": action, "jd_quote": JDQ, "brief_quote": "Path A does NOT require Power Query.",
                          "result": "not required on Path A", "path_id": path_id}])


def test_M_a_waived_requirement_does_not_stay_active_in_its_path():
    p = compile_intent(_recon_intent(path_id="PATH A"))
    assert "Power Query" not in dict((t, 1) for _tier, t in audit.judge_checklist(p, "PATH A"))
    assert "Power Query" in dict((t, 1) for _tier, t in audit.judge_checklist(p, "PATH B"))      # still required on B
    g = atom(p, "skill", "Power Query", "global")
    assert g.fate == "VERIFIED_DOWNSTREAM" and "retired by reconciliation in: PATH A" in g.justification
    rec = atom(p, "reconciliation")
    assert rec.fate == "DROPPED_WITH_JUSTIFICATION" and rec.kind == "RECORD" and "not required on Path A" in rec.justification


def test_M_a_global_waiver_retires_the_requirement_everywhere_with_a_justification():
    p = compile_intent(_recon_intent(path_id=None))
    g = atom(p, "skill", "Power Query", "global")
    assert g.fate == "DROPPED_WITH_JUSTIFICATION" and "retired by reconciliation" in g.justification
    assert all("Power Query" not in [t for _tier, t in audit.judge_checklist(p, pid)] for pid in ("PATH A", "PATH B"))


def test_M_a_waived_hard_filter_leaves_no_provider_leaf():
    it = mk(skills=[{"name": "Power Query", "strength": "required", "relationship": "current", "basis": basis(("jd",), JDQ)}],
            reconciliations=[{"topic": "Power Query requirement", "action": "waived", "jd_quote": JDQ, "result": "waived"}])
    p = compile_intent(it)
    assert not any("Power Query" in l[2] for l in L(p)) and atom(p, "skill", "Power Query").fate == "DROPPED_WITH_JUSTIFICATION"


def test_M_an_unresolved_conflict_is_surfaced_and_enforced_on_neither_side():
    it = mk(skills=[{"name": "Power Query", "strength": "required", "relationship": "current", "basis": basis(("jd",), JDQ)}],
            reconciliations=[{"topic": "Power Query requirement", "action": "unresolved", "jd_quote": JDQ, "result": "conflict"}])
    p = compile_intent(it)
    assert atom(p, "skill", "Power Query").fate == "UNRESOLVED" and atom(p, "reconciliation").fate == "UNRESOLVED"
    assert not any("Power Query" in l[2] for l in L(p)) and any("UNRESOLVED" in w for w in p.warnings)


@pytest.mark.parametrize("kw", [
    {"sources": ("jd", "recruiter_brief")},          # the brief also supports it: it IS the reconciled meaning
    {"strength": "preferred"},                        # a lower strength: the downgraded form survives
    {"topic": "Something else entirely"},             # the reconciliation does not name this atom (a shared JD sentence)
])
def test_M_only_the_atom_a_reconciliation_names_is_retired(kw):
    p = compile_intent(_recon_intent(path_id=None, **kw))
    assert atom(p, "skill", "Power Query", "global").fate != "DROPPED_WITH_JUSTIFICATION"


def test_M_the_role1_reconciliations_retire_nothing_the_brief_kept():
    for n in range(1, 6):
        plan = compile_intent(loader.load_intent("R1", n))
        assert not [a for a in plan.atom_audit if a.kind == "MEANING" and "retired by reconciliation" in a.justification]
        assert len([a for a in plan.atom_audit if a.concept == "reconciliation"]) == len(loader.load_intent("R1", n).reconciliations)


# --- N / O. every atom has a fate; silent drops are zero ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def verified():
    return {k: hardened_verify.verify_intent(it) | {"intent": it} for k, it in loader.load_all().items()}


def test_N_every_atom_record_has_exactly_one_closed_set_fate_and_a_justification(verified):
    for k, v in verified.items():
        assert v["bad_fates"] == [] and v["duplicate_atom_ids"] == [] and v["records_without_justification"] == [], k
        for a in v["plan"].atom_audit:
            assert a.fate in FATES and a.destination and a.justification and a.provenance and a.scope, (k, a)


def test_N_the_audit_shows_the_fields_the_brief_requires():
    it = loader.load_intent("R3", 2)
    rec = audit.build_audit_record(it, _compile_intent(it, loader.sources_for("R3")))
    a = next(x for x in rec["atom_audit"] if x["concept"] == "skill.proficiency")
    for key in ("concept", "scope", "provenance", "strength", "proficiency", "relationship", "fate", "destination", "justification", "value"):
        assert key in a
    assert a["proficiency"] == "advanced" and a["provenance"]["sources"] == ["jd"] and a["scope"] == "global"


def test_O_the_silent_drop_count_is_zero_over_every_frozen_intent(verified):
    silent = [(k, a["concept"], a["value"]) for k, v in verified.items() for a in v["atoms"] if a["silent"]]
    assert silent == []
    assert sum(len(v["atoms"]) for v in verified.values()) == 1137


def test_O_every_declared_fate_is_consistent_with_what_the_output_actually_depends_on(verified):
    bad = [(k, a["concept"], a["value"], a["why"]) for k, v in verified.items() for a in v["atoms"] if not a["silent"] and not a["consistent"]]
    assert bad == []


def test_O_no_invented_model_only_hard_filters_over_every_frozen_intent(verified):
    assert sum(len(hardened_verify.invented_model_only_hard_filters(v["intent"], v["plan"])) for v in verified.values()) == 0


def test_O_the_verifier_really_detects_a_planted_silent_drop(monkeypatch):
    """Test the test: a compiler that forgets one extension concept must be caught as silent drops by the independent ablation."""
    real = hardened_verify.compile_intent

    def forgetful(intent):
        d = intent.model_dump()
        d["domain"] = []
        d["semantic_exclusions"] = []
        return real(ExperimentalHiringIntent.model_validate(d))

    monkeypatch.setattr(hardened_verify, "compile_intent", forgetful)
    res = hardened_verify.verify_intent(loader.load_intent("R3", 1))
    dropped = {a["concept"] for a in res["atoms"] if a["silent"]}
    assert {"domain", "semantic_exclusion"} <= dropped


# --- backward compatibility ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["python_backend_hyderabad", "epiq_product_owner"])
def test_production_shaped_anchors_compile_exactly_as_before(name):
    it = parse_structured_intent((GOLDEN / f"{name}.expected.json").read_text(encoding="utf-8"))
    new, old = compile_intent(it), legacy.compile_intent(it)
    assert canonicalize(new.filter_tree) == canonicalize(old.filter_tree)
    assert [(c.source, c.strength, c.route, c.temporal, c.capability) for c in new.audit] == [(c.source, c.strength, c.route, c.temporal, c.capability) for c in old.audit]
    assert new.retrieval_title_family == old.retrieval_title_family and new.warnings == old.warnings and new.paths == []
    assert audit.judge_checklist(new) == audit.judge_checklist(old)


def test_a_plain_structured_hiring_intent_gets_atom_records_too():
    it = parse_structured_intent((GOLDEN / "epiq_product_owner.expected.json").read_text(encoding="utf-8"))
    p = compile_intent(it)
    assert p.atom_audit and all(a.fate in FATES for a in p.atom_audit)
    assert atom(p, "company", "Arete").fate == "PREFERENCE_CONTEXT" and atom(p, "location.entry").fate == "ENFORCED"
    assert p.contract_version == "compiler-contract-1"


def test_the_compiler_is_deterministic_including_the_atom_audit():
    for k in (("R1", 3), ("R2", 1), ("R3", 4)):
        it = loader.load_intent(*k)
        a, b = compile_intent(it), compile_intent(it)
        assert json.dumps(audit.atom_audit_records(a), sort_keys=True) == json.dumps(audit.atom_audit_records(b), sort_keys=True)
        assert audit.plan_hash(a) == audit.plan_hash(b)


# --- a future schema field cannot become a silent drop --------------------------------------------------------------------------


def test_every_schema_field_belongs_to_a_covered_concept():
    from backend.experiments.compiler_contract.atoms import concept_of
    from backend.experiments.compiler_contract.signature import schema_paths
    unclassified = sorted(p for p in schema_paths(ExperimentalHiringIntent) if concept_of(p) is None)
    assert unclassified == [], f"route these new schema fields through the compiler contract (COMPILER_CONTRACT.md): {unclassified}"


def test_every_concept_the_enumerator_produces_has_a_record_in_the_compiler(verified):
    seen = {(k, a["concept"]) for k, v in verified.items() for a in v["atoms"]}
    for k, v in verified.items():
        have = {r.concept for r in v["plan"].atom_audit}
        for a in v["atoms"]:
            if a["concept"] != "provenance.basis":
                assert a["concept"] in have, (k, a["concept"])
    assert seen


def test_the_hardening_report_is_generated_from_the_measurements_and_is_current():
    from backend.experiments.compiler_contract import build_hardening_report
    path = Path(__file__).resolve().parents[1] / "backend" / "experiments" / "compiler_contract" / "RESULTS_COMPILER_HARDENING.md"
    before = path.read_text(encoding="utf-8")
    assert build_hardening_report.build() == before and "{{" not in before


def test_the_committed_hardened_measurements_are_what_the_live_compiler_produces(verified):
    summary = json.loads((Path(__file__).resolve().parents[1] / "backend/experiments/compiler_contract/results/hardened_summary.json").read_text(encoding="utf-8"))
    for k, v in verified.items():
        assert summary["runs"][f"{k[0]}/{k[1]}"]["atoms"] == len(v["atoms"]) and summary["runs"][f"{k[0]}/{k[1]}"]["silently_dropped"] == 0
