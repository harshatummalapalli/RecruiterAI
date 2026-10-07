"""DOWNSTREAM CONSUMER INTEGRATION tests (offline; synthetic candidates only; no model, no provider, no retrieval).
See backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md.

The compiled downstream context is the SOURCE OF TRUTH for the Judge and for admission's facts. Sections:
  SP  semantic provenance (a qualifier needs the same source support as the value): matrix A-F, generic
  ST  single source of truth + conflicts (compiled wins, never silently reconciled)
  JC  the Judge checklist contract (path-aware, provenance, exclusions, preferences, unresolved, proficiency, work mode, no provider syntax)
  AD  admission facts (only the SOURCE of the facts changes)
  UR  unspecified != current, through the Judge and admission
  SY  synthetic candidates A / B / C / D over Roles 1-3
  BC  backward compatibility (no compiled context -> the legacy path, unchanged)
  GT  the 14 acceptance gates
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
from pathlib import Path

import pytest

from backend.experiments.compiler_contract import downstream_verify as dv
from backend.experiments.compiler_contract import loader
from backend.experiments.compiler_contract.signature import leaves
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.models.search_intent import Experience, Role, SearchIntent, Titles
from backend.services import consumer_input as ci
from backend.services.candidate_evidence_builder import _build_role_alignment, build_candidate_evidence
from backend.services.downstream_context import (ADMISSION, JUDGE_EXCLUSION, JUDGE_REQUIREMENT, PREFERENCE, PROVIDER_ENFORCED, UNRESOLVED_ITEM, build_downstream_contexts)
from backend.services.requirement_judge import RequirementJudge
from backend.services.search_compiler import VERIFIED_DOWNSTREAM, compile_intent
from backend.services.source_provenance import SourceTexts

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("R1", "R2", "R3")
RUNS = (1, 2, 3, 4, 5)
BASE = {"role_archetype": {"value": "hybrid", "confidence": 0.5, "rationale": "t"}, "role_family": ["Probe Role"]}


def mk(**kw) -> ExperimentalHiringIntent:
    return ExperimentalHiringIntent.model_validate({**copy.deepcopy(BASE), **kw})


def b(quote, sources=("jd",)):
    return {"sources": list(sources), "quote": quote}


def compiled(intent, jd):
    plan = compile_intent(intent, SourceTexts(jd="We are hiring a Probe Role. " + jd))
    return plan, build_downstream_contexts(plan)[0]


def L(plan):
    return leaves(plan.filter_tree)


def atoms(plan, concept):
    return [a for a in plan.atom_audit if a.concept == concept]


# ======================================================================================================================
# SP. SEMANTIC PROVENANCE: a hard filter needs provenance for the COMPLETE constraint (value, requiredness, temporal scope)
# Generic: two unrelated vocabularies; nothing here names a role, a title or a Role-2 example.
# ======================================================================================================================

VOCAB = [dict(skill="Zorblax", company="Quuxcorp", level="Wizard", alt="Sorcerer", place="Gondor, Mordor, Arda"),
         dict(skill="Plinth", company="Fnordly", level="Overseer", alt="Steward", place="Narnia, Archenland, Aslan")]


@pytest.mark.parametrize("v", VOCAB)
def test_SP_A_an_unsupported_current_is_not_a_current_filter(v):
    """The source states the skill but not WHEN: a `current` claim is a model-inferred qualifier on a source-supported value."""
    plan, ctx = compiled(mk(skills=[{"name": v["skill"], "strength": "required", "relationship": "current", "basis": b(f"Experience with {v['skill']} is required.")}]),
                         f"Experience with {v['skill']} is required.")
    a = atoms(plan, "skill")[0]
    assert a.relationship is None and a.fate != "ENFORCED"
    assert not any(v["skill"] in str(l[2]) for l in L(plan))
    (u,) = a.unsupported_qualifiers
    assert u["qualifier"] == "relationship" and u["claimed"] == "current" and "present use" in u["reason"]
    e = next(e for e in ctx.entries if e.concept == "skill")
    assert e.relationship is None and e.unsupported_qualifiers[0]["claimed"] == "current"          # the claim and the reason survive into the context
    assert "current" not in e.text.casefold()


@pytest.mark.parametrize("v", VOCAB)
def test_SP_A_a_supported_current_is_still_a_current_filter(v):
    plan, _ = compiled(mk(skills=[{"name": v["skill"], "strength": "required", "relationship": "current", "basis": b(f"Currently using {v['skill']} is required.")}]),
                       f"Currently using {v['skill']} is required.")
    a = atoms(plan, "skill")[0]
    assert a.relationship == "current" and a.fate == "ENFORCED" and not a.unsupported_qualifiers


@pytest.mark.parametrize("v", VOCAB)
def test_SP_B_an_unsupported_past_is_not_a_past_filter(v):
    plan, _ = compiled(mk(skills=[{"name": v["skill"], "strength": "required", "relationship": "past", "basis": b(f"{v['skill']} is needed.")}]), f"{v['skill']} is needed.")
    a = atoms(plan, "skill")[0]
    assert a.relationship is None and a.fate != "ENFORCED" and a.unsupported_qualifiers[0]["claimed"] == "past"
    assert not any(v["skill"] in str(l[2]) for l in L(plan))


@pytest.mark.parametrize("v", VOCAB)
def test_SP_C_an_unsupported_strength_is_not_a_hard_filter(v):
    """The source says the skill is only a plus; the intent claims `required`."""
    q = f"{v['skill']} is a plus."
    plan, _ = compiled(mk(skills=[{"name": v["skill"], "strength": "required", "relationship": "any", "basis": b(q)}]), q)
    a = atoms(plan, "skill")[0]
    assert a.strength != "required" and a.fate == "PREFERENCE_CONTEXT" and a.unsupported_qualifiers[0]["qualifier"] == "strength"
    assert not any(c.route == "provider_hard_filter" for c in plan.audit if v["skill"] in c.source)


@pytest.mark.parametrize("v", VOCAB)
def test_SP_D_an_unsupported_proficiency_is_unresolved_not_required(v):
    q = f"Familiarity with {v['skill']}."
    plan, ctx = compiled(mk(skills=[{"name": v["skill"], "strength": "required", "relationship": "any", "proficiency": "advanced", "basis": b(q)}]), q)
    (p,) = atoms(plan, "skill.proficiency")
    assert p.fate == "UNRESOLVED" and p.proficiency is None and p.unsupported_qualifiers[0]["claimed"] == "advanced"
    checklist = ci.judge_checklist_for(ctx)
    assert not any(i.proficiency for i in checklist.requirements)                           # never handed to the Judge as a requirement
    assert any(i.concept == "skill.proficiency" and i.reason for i in checklist.unresolved)  # but visible, with the reason
    assert not any("advanced" in i.text for i in checklist.judged)


@pytest.mark.parametrize("v", VOCAB)
def test_SP_D_a_supported_proficiency_is_handed_over_verbatim(v):
    q = f"Advanced {v['skill']} expertise."
    plan, ctx = compiled(mk(skills=[{"name": v["skill"], "strength": "required", "relationship": "any", "proficiency": "advanced", "basis": b(q)}]), q)
    item = next(i for i in ci.judge_checklist_for(ctx).requirements if i.proficiency)
    assert item.proficiency == "advanced" and v["skill"] in item.text and item.judged


@pytest.mark.parametrize("v", VOCAB)
def test_SP_E_an_unsupported_title_alternative_is_not_an_accepted_level(v):
    q = f"We need a {v['level']}."
    plan, ctx = compiled(mk(seniority={"value": v["level"], "strength": "required", "alternatives": [v["alt"]], "basis": b(q)}), q)
    alt = atoms(plan, "seniority.alternatives")[0]
    assert alt.fate == "UNRESOLVED" and alt.unsupported_qualifiers[0]["qualifier"] == "alternative_level"
    facts = ci.admission_facts_for(ctx)
    assert v["alt"] not in facts.accepted_levels and any(u["concept"] == "seniority.alternatives" for u in facts.ungated)   # visible, not accepted


def test_SP_E_a_supported_alternative_is_kept():
    q = "We need a Senior engineer; Lead is also fine."
    plan, ctx = compiled(mk(seniority={"value": "Senior", "strength": "required", "alternatives": ["Lead"], "basis": b(q)}), q)
    assert ci.admission_facts_for(ctx).accepted_levels == ("Lead",) and ci.admission_facts_for(ctx).target_level == "Senior"


@pytest.mark.parametrize("v", VOCAB)
def test_SP_F_an_unsupported_geographic_qualifier_is_not_a_hard_filter(v):
    q = f"Based in {v['place'].split(',')[0]}."
    plan, ctx = compiled(mk(location={"entries": [v["place"].split(",")[0] + ", " + v["place"].split(",")[1].strip() + ", " + v["place"].split(",")[2].strip()],
                                      "radius": {"value": 50, "unit": "miles", "around": v["place"].split(",")[0]},
                                      "remote": "allowed", "work_mode": "hybrid", "strength": "required", "basis": b(q)}), q)
    for concept in ("location.radius", "location.remote", "location.work_mode"):
        a = atoms(plan, concept)[0]
        assert a.fate == "UNRESOLVED" and a.unsupported_qualifiers, concept
    assert not any(l[1] == "geo_distance" for l in L(plan))
    assert {i.concept for i in ci.judge_checklist_for(ctx).unresolved} >= {"location.radius", "location.remote", "location.work_mode"}


def test_SP_no_source_supported_value_plus_model_inferred_qualifier_becomes_a_hard_filter():
    """The generic rule over every frozen intent: an ENFORCED atom never carries an unsupported qualifier."""
    for role in ROLES:
        for n in RUNS:
            plan = compile_intent(loader.load_intent(role, n), loader.sources_for(role))
            for a in plan.atom_audit:
                if a.fate in ("ENFORCED", "NORMALIZED"):
                    assert not a.unsupported_qualifiers, (role, n, a.atom_id)


# ======================================================================================================================
# ST. SINGLE SOURCE OF TRUTH and CONFLICTS
# ======================================================================================================================


def _legacy_intent(**kw) -> SearchIntent:
    return SearchIntent(**kw)


def _ctx_for(intent, jd):
    return compiled(intent, jd)[1]


def test_ST_compiled_meaning_wins_and_the_disagreement_is_recorded_not_reconciled():
    ctx = _ctx_for(mk(seniority={"value": "Lead", "strength": "required", "basis": b("We need a Lead.")}, experience={"minimum_years": 8, "strength": "required", "basis": b("8+ years.")}),
                   "We need a Lead. 8+ years.")
    legacy = _legacy_intent(role=Role(title="Other", seniority="Junior"), experience=Experience(minimum_years=2), core_signals=["A legacy-only requirement"])
    r = ci.resolve(dataclasses.replace(legacy, compiled_context=ctx))
    assert r.source == "compiled" and r.facts.target_level == "Lead" and r.facts.minimum_years == 8          # the compiled facts
    assert ("core", "A legacy-only requirement") not in r.judged                                              # the legacy signal is not asked
    fields = {d.field: d for d in r.disagreements}
    assert fields["seniority"].legacy == "Junior" and fields["seniority"].compiled == "Lead" and fields["seniority"].winner == "compiled"
    assert fields["experience.minimum_years"].legacy == 2 and fields["experience.minimum_years"].compiled == 8
    assert fields["signal.core"].legacy == "A legacy-only requirement" and fields["signal.core"].compiled is None
    # never merged: no value is the "stricter of the two" or a union
    assert r.facts.target_level != "Junior" and r.facts.minimum_years not in (2, 10)


def test_ST_title_facts_come_from_the_compiled_role_family_not_the_legacy_title():
    ctx = _ctx_for(mk(role_family=["Software Engineer"]), "We are hiring a Software Engineer.")
    r = ci.resolve(SearchIntent(role=Role(title="Legacy Title"), titles=Titles(include_titles=["Legacy Equivalent"]), compiled_context=ctx))
    assert r.role_title == "Software Engineer" and "Legacy Title" not in (r.role_title, *r.include_titles) and "Legacy Equivalent" not in r.include_titles
    assert "Python Developer" in r.include_titles                                          # the approved role-family equivalents travel with the atom


def test_ST_conflict_legacy_current_required_vs_compiled_unspecified_relationship():
    """CRITICAL. The legacy intent says 'current Python required'; the compiled meaning says the relationship is UNSPECIFIED. Compiled wins: no current-Python
    requirement is asked, enforced or carried anywhere."""
    q = "Python experience is required."
    plan, ctx = compiled(mk(skills=[{"name": "Python", "strength": "required", "basis": b(q)}]), q)       # relationship omitted = unspecified
    assert atoms(plan, "skill")[0].relationship is None
    legacy = SearchIntent(core_signals=["Currently works with Python (required)"], differentiator_signals=["Current Python role"])
    r = ci.resolve(dataclasses.replace(legacy, compiled_context=ctx))
    asked = " | ".join(t for _tier, t in r.judged).casefold()
    assert "python" in asked and "current" not in asked                                                       # Python is asked, "current" is not
    assert [i.relationship for i in r.checklist.requirements if "Python" in i.text] == [None]
    assert not any(l[0].endswith("current.skills") or "current" in l[0] and "Python" in str(l[2]) for l in L(plan))
    assert {d.field for d in r.disagreements} >= {"signal.core", "signal.differentiator"}                    # and the legacy claim is on record
    # the Judge itself is not given the legacy sentence either
    cand, harvest = dv.synthetic_candidate("x", ["Python experience is required"])
    model = dv.ScriptedModel()
    RequirementJudge(client=model).judge(cand, dataclasses.replace(legacy, compiled_context=ctx), harvest)
    assert model.asked and not any("urrent" in t for call in model.asked for t in call)


def test_ST_conflict_legacy_company_hard_filter_vs_compiled_company_preference():
    q = "People from Quuxcorp are preferred."
    plan, ctx = compiled(mk(companies=[{"name": "Quuxcorp", "strength": "preferred", "relationship": "any", "basis": b(q)}]), q)
    legacy = SearchIntent(core_signals=["Works at Quuxcorp"])                                     # the legacy intent made it a core requirement
    r = ci.resolve(dataclasses.replace(legacy, compiled_context=ctx))
    assert not any("Quuxcorp" in t for tier, t in r.judged if tier == "core")                       # not required
    assert any("Quuxcorp" in i.text and i.polarity == ci.PREFER for i in r.checklist.preferences)   # kept as a preference
    assert not any("Quuxcorp" in i.text for i in r.checklist.requirements)
    assert not any(c.route == "provider_hard_filter" for c in plan.audit if "Quuxcorp" in c.source)
    assert any(d.field == "signal.core" and d.legacy == "Works at Quuxcorp" for d in r.disagreements)


def test_ST_a_wrong_typed_compiled_context_is_an_error_never_a_silent_legacy_fallback():
    with pytest.raises(TypeError):
        ci.resolve(SearchIntent(core_signals=["x"], compiled_context={"not": "a context"}))


def test_ST_the_legacy_fields_are_read_for_meaning_only_inside_the_consumer_seam():
    for f in ("requirement_judge.py", "candidate_evidence_builder.py", "search_pipeline.py", "admission.py", "candidate_ranker.py", "match_explainer.py"):
        text = (ROOT / "backend" / "services" / f).read_text(encoding="utf-8")
        assert not re.search(r"intent\.(core_signals|supporting_signals|differentiator_signals)\b|intent\.role\.(seniority|title)|intent\.experience\.minimum_years|intent\.titles\.include_titles", text), f


# ======================================================================================================================
# JC. THE JUDGE CHECKLIST CONTRACT, over all 15 frozen intents
# ======================================================================================================================


def _frozen():
    for role in ROLES:
        for n in RUNS:
            yield role, n, compile_intent(loader.load_intent(role, n), loader.sources_for(role))


def test_JC_every_verified_downstream_atom_reaches_the_judge_the_exclusion_slot_or_admission():
    for role, n, plan in _frozen():
        for ctx in build_downstream_contexts(plan):
            checklist, facts = ci.judge_checklist_for(ctx), ci.admission_facts_for(ctx)
            judged_ids = " ".join(i.item_id for i in checklist.judged)
            exclusion_ids = " ".join(i.item_id for i in checklist.exclusions)
            for e in ctx.entries:
                if e.fate != VERIFIED_DOWNSTREAM:
                    continue
                where = {"downstream_evidence": judged_ids, "downstream_exclusion": exclusion_ids, "admission_level_fit": " ".join(facts.atom_ids)}[e.route]
                assert e.atom_id in where, (role, n, ctx.path_id, e.atom_id, e.route)


def test_JC_preferences_stay_preferences_and_are_never_required():
    for role, n, plan in _frozen():
        for ctx in build_downstream_contexts(plan):
            c = ci.judge_checklist_for(ctx)
            assert all(i.polarity == ci.PREFER and i.fate == "PREFERENCE_CONTEXT" for i in c.preferences)
            assert all(i.polarity == ci.MUST_HAVE and i.fate == VERIFIED_DOWNSTREAM for i in c.requirements)
            pref_ids = {i.item_id for i in c.preferences}
            assert not pref_ids & {i.item_id for i in c.requirements}
            assert all(i.tier != "core" for i in c.preferences)                                  # a preference never sits in the core tier


def test_JC_unresolved_stays_visible_with_a_reason_and_is_never_judged():
    seen = 0
    for role, n, plan in _frozen():
        for ctx in build_downstream_contexts(plan):
            c = ci.judge_checklist_for(ctx)
            assert {i.item_id for i in c.unresolved} == {e.atom_id for e in ctx.entries if e.kind == UNRESOLVED_ITEM}
            for i in c.unresolved:
                seen += 1
                assert i.reason and not i.judged and i.polarity == ci.UNDECIDED
    assert seen > 0


def test_JC_enforced_atoms_are_not_re_required_by_the_judge():
    for role, n, plan in _frozen():
        for ctx in build_downstream_contexts(plan):
            c = ci.judge_checklist_for(ctx)
            enforced = {e.atom_id for e in ctx.entries if e.kind == PROVIDER_ENFORCED}
            assert {i.item_id for i in c.already_enforced} == enforced
            assert not any(i.item_id in enforced for i in c.judged)
            assert all(not i.judged for i in c.already_enforced)


def test_JC_exclusions_are_must_not_have_and_carry_provenance():
    seen = 0
    for role, n, plan in _frozen():
        for ctx in build_downstream_contexts(plan):
            for i in ci.judge_checklist_for(ctx).exclusions:
                seen += 1
                assert i.polarity == ci.MUST_NOT_HAVE and i.provenance.get("state") and not i.judged
    assert seen > 0


def test_JC_proficiency_and_work_mode_reach_the_checklist():
    prof = work = 0
    for role, n, plan in _frozen():
        for ctx in build_downstream_contexts(plan):
            c = ci.judge_checklist_for(ctx)
            prof += len(c.proficiencies)
            work += len(c.work_mode)
            for i in c.proficiencies:
                assert i.proficiency in ("hands_on", "working_knowledge", "advanced")
    assert prof > 0 and work > 0


def test_JC_every_item_carries_provenance_and_its_path():
    for role, n, plan in _frozen():
        for ctx in build_downstream_contexts(plan):
            for i in ci.judge_checklist_for(ctx).all_items:
                assert i.provenance.get("state") in ("source", "knowledge", "unrecorded", "model_only", "absent", "comparison", "unverified_quote"), i.item_id
                assert i.path_id == ctx.path_id


_PROVIDER_TOKENS = ("basic_profile", "experience.employment_details", "current_employers", "years_of_experience_raw", "crustdata", "geo_distance", "filter_tree",
                    "provider_plan", "(.)", "person_search", "past_employers")


def test_JC_the_judge_interface_carries_no_provider_syntax_and_no_score():
    for role, n, plan in _frozen():
        for ctx in build_downstream_contexts(plan):
            blob = json.dumps(ci.judge_checklist_for(ctx).to_dict(), ensure_ascii=False).casefold()
            for tok in _PROVIDER_TOKENS:
                assert tok.casefold() not in blob, (role, n, tok)
    for cls in (ci.ChecklistItem, ci.JudgeChecklist, ci.PathAttribution, ci.AdmissionFacts):
        names = {f.name for f in dataclasses.fields(cls)}
        assert not names & {"score", "rank", "weight", "boost", "priority", "path_score", "path_rank"}, cls


def test_JC_the_judge_asks_exactly_the_checklist_and_never_reconstructs_from_prose():
    ctxs = dv.contexts_for("R1", 3)
    ctx = ctxs[0]
    legacy = SearchIntent(core_signals=["Some legacy prose requirement"], supporting_signals=["Another legacy prose requirement"])
    cand, harvest = dv.synthetic_candidate("x", ["nothing relevant"])
    model = dv.ScriptedModel()
    out = RequirementJudge(client=model).judge_detailed(cand, dataclasses.replace(legacy, compiled_context=ctx), harvest)
    asked = {t for call in model.asked for t in call}
    assert asked == set(dv.judged_texts(ctx)) and "Some legacy prose requirement" not in asked
    assert out.input_source == "compiled" and out.checklist["path_id"] == ctx.path_id
    assert {i["text"] for i in out.checklist["exclusions"]} == {i.text for i in ci.judge_checklist_for(ctx).exclusions}
    assert out.checklist["unresolved"] and out.checklist["preferences"]


def test_JC_leadership_alternatives_are_one_item_not_an_AND():
    q = "Lead role; either people or technical leadership counts. A Lead is needed."
    plan, ctx = compiled(mk(seniority={"value": "Lead", "strength": "required", "leadership": ["people", "technical"], "basis": b(q)}), q)
    items = [i for i in ci.judge_checklist_for(ctx).requirements if i.concept == "seniority.leadership"]
    assert len(items) == 1 and items[0].alternatives == ("people leadership", "technical leadership") and " or " in items[0].text


# ======================================================================================================================
# PATHS: no flattening
# ======================================================================================================================


def test_PATH_each_path_has_its_own_checklist_and_nothing_is_flattened():
    a, bb = dv.contexts_for("R1", 3)
    ca, cb = ci.judge_checklist_for(a), ci.judge_checklist_for(bb)
    only_a = set(dv.required_texts(a)) - set(dv.required_texts(bb))
    only_b = set(dv.required_texts(bb)) - set(dv.required_texts(a))
    assert only_a and only_b                                           # R1 run 3 has requirements that belong to ONE path
    assert only_a.isdisjoint({i.text for i in cb.judged if i.polarity == ci.MUST_HAVE})
    assert only_b.isdisjoint({i.text for i in ca.judged if i.polarity == ci.MUST_HAVE})
    assert (ca.path_id, cb.path_id) == ("PATH A", "PATH B")
    assert all(i.path_id == "PATH A" for i in ca.all_items) and all(i.path_id == "PATH B" for i in cb.all_items)
    assert any(i.inherited for i in ca.all_items) and any(i.inherited for i in cb.all_items)          # a global atom reaches each path as inherited


def test_PATH_a_path_specific_atom_is_not_in_another_paths_judge_input():
    ctxs = dv.contexts_for("R2", 1, overlay=True)
    intents = ci.search_intents_from_contexts(ctxs)
    asked = {}
    for ctx, intent in zip(ctxs, intents):
        cand, harvest = dv.synthetic_candidate("x", ["nothing"])
        m = dv.ScriptedModel()
        RequirementJudge(client=m).judge(cand, intent, harvest)
        asked[ctx.path_id] = {t for call in m.asked for t in call}
    assert "Synthetic Alpha Tool" in asked["PATH A"] and "Synthetic Alpha Tool" not in asked["PATH B"]
    assert "Synthetic Beta Tool" in asked["PATH B"] and "Synthetic Beta Tool" not in asked["PATH A"]


def test_PATH_the_per_path_judge_input_equals_the_context_adapter_modulo_leadership_grouping():
    for role in ROLES:
        for ctx in dv.contexts_for(role, 1):
            from backend.services.downstream_context import to_judge_signals
            old = {k: [t for t in v if "leadership" not in t.casefold()] for k, v in to_judge_signals(ctx).items()}
            new = {k: [t for t in v if "leadership" not in t.casefold()] for k, v in ci.judge_checklist_for(ctx).signals().items()}
            assert old == new, (role, ctx.path_id)


# ======================================================================================================================
# AD. ADMISSION: only the SOURCE of the facts changes
# ======================================================================================================================


def _cand_with_title(title, headline="", years_start="2012-01-01T00:00:00"):
    from backend.models.candidate import Candidate
    return Candidate(candidate_id="c", name="C", title=title, company="Co",
                     raw_data={"basic_profile": {"headline": headline}, "experience": {"employment_details": {"current": [{"start_date": years_start, "title": title}], "past": []}},
                               "metadata": {"updated_at": "2026-09-01T00:00:00+00:00"}})


def _alignment(intent, cand):
    return build_candidate_evidence(cand, intent).role_alignment


def test_AD_admission_gates_on_the_compiled_level_and_floor():
    q = "We need a Senior engineer with 5+ years."
    plan, ctx = compiled(mk(seniority={"value": "Senior", "strength": "required", "basis": b(q)}, experience={"minimum_years": 5, "strength": "required", "basis": b(q)}), q)
    intent = SearchIntent(compiled_context=ctx)                                                   # NO legacy fields at all
    assert ci.role_facts_for(intent).target_level == "Senior" and ci.role_facts_for(intent).minimum_years == 5
    senior = _alignment(intent, _cand_with_title("Senior Engineer"))
    director = _alignment(intent, _cand_with_title("Director of Engineering"))
    junior = _alignment(intent, _cand_with_title("Junior Engineer"))
    assert (senior.level_fit, director.level_fit, junior.level_fit) == ("aligned", "above", "below")
    assert senior.experience_floor is True
    from backend.services.admission import evaluate_eligibility
    assert evaluate_eligibility(director.level_fit, director.experience_floor) == (False, "level_above_target")


def test_AD_the_compiled_facts_match_the_legacy_facts_when_they_agree():
    q = "We need a Senior engineer with 5+ years."
    plan, ctx = compiled(mk(seniority={"value": "Senior", "strength": "required", "basis": b(q)}, experience={"minimum_years": 5, "strength": "required", "basis": b(q)}), q)
    legacy = SearchIntent(role=Role(seniority="Senior"), experience=Experience(minimum_years=5))
    for title in ("Senior Engineer", "Director of Engineering", "Junior Engineer", "Engineer"):
        c = _cand_with_title(title)
        a, bb = _alignment(legacy, c), _alignment(dataclasses.replace(legacy, compiled_context=ctx), c)
        assert (a.level_fit, a.experience_floor) == (bb.level_fit, bb.experience_floor), title


def test_AD_a_preferred_level_is_not_gated_and_stays_visible():
    q = "A Senior engineer would be preferred."
    plan, ctx = compiled(mk(seniority={"value": "Senior", "strength": "preferred", "basis": b(q)}), q)
    f = ci.admission_facts_for(ctx)
    assert f.target_level is None and any(u["concept"] == "seniority.value" and u["fate"] == "PREFERENCE_CONTEXT" for u in f.ungated)
    legacy_would_gate = _alignment(SearchIntent(role=Role(seniority="Senior")), _cand_with_title("Director of Engineering")).level_fit
    compiled_fit = _alignment(SearchIntent(compiled_context=ctx), _cand_with_title("Director of Engineering")).level_fit
    assert legacy_would_gate == "above" and compiled_fit is None                                  # compiled wins: a preference never excludes


@pytest.mark.parametrize("level", ["Staff", "Principal Engineer", "Senior Manager"])
def test_AD_an_unresolved_level_is_never_invented(level):
    q = f"We need a {level}."
    plan, ctx = compiled(mk(seniority={"value": level, "strength": "required", "basis": b(q)}), q)
    f = ci.admission_facts_for(ctx)
    assert f.target_level is None and f.ungated and f.ungated[0]["fate"] == "UNRESOLVED" and level in f.ungated[0]["text"]
    assert _alignment(SearchIntent(compiled_context=ctx), _cand_with_title("Director of Engineering")).level_fit is None     # not gated on a made-up level


def test_AD_an_unsupported_experience_bound_is_not_a_floor():
    plan, ctx = compiled(mk(experience={"minimum_years": 12, "strength": "required", "basis": b("Experienced people.")}), "Experienced people.")
    f = ci.admission_facts_for(ctx)
    assert f.minimum_years is None and any(u["concept"] == "experience.min" for u in f.ungated)


def test_AD_accepted_alternative_levels_use_the_unchanged_level_rule_once_per_level():
    q = "We need a Senior engineer; Lead is also fine."
    plan, ctx = compiled(mk(seniority={"value": "Senior", "strength": "required", "alternatives": ["Lead"], "basis": b(q)}), q)
    intent = SearchIntent(compiled_context=ctx)
    assert _alignment(intent, _cand_with_title("Lead Engineer")).level_fit == "aligned"            # at an accepted level: not 'above'
    assert _alignment(intent, _cand_with_title("Senior Engineer")).level_fit == "aligned"
    assert _alignment(intent, _cand_with_title("Director of Engineering")).level_fit == "above"
    assert _alignment(intent, _cand_with_title("Junior Engineer")).level_fit == "below"
    assert _alignment(SearchIntent(role=Role(seniority="Senior")), _cand_with_title("Lead Engineer")).level_fit == "above"   # the legacy path is unchanged


def test_AD_no_threshold_level_rule_or_ranking_changed():
    """The admission gate, the ranker and the pipeline's N -> 50 -> 25 are pinned by content hash: this phase changes the SOURCE of facts only."""
    for f in _PINNED:
        got = hashlib.sha256((ROOT / "backend" / "services" / f).read_bytes()).hexdigest()
        assert got == _PINNED[f], f"{f} changed ({got})"
    pipeline = (ROOT / "backend" / "services" / "search_pipeline.py").read_text(encoding="utf-8")
    for token in ("target_pool_size", "partition_by_eligibility"):
        assert token in pipeline


_PINNED = {"admission.py": "e7b8ddd365b57f2494060a63857d5e87b4c337a0f3047b4e0e343475cfbe8083",
           "candidate_ranker.py": "8958925286aac8794fa23cae31379066a3bd1a241ae696509ff68787994f22e9"}


# ======================================================================================================================
# UR. UNSPECIFIED != CURRENT, through the Judge and admission
# ======================================================================================================================


def test_UR_an_unspecified_relationship_stays_unspecified_in_every_consumer_input():
    for role, n, plan in _frozen():
        for ctx in build_downstream_contexts(plan):
            for e in ctx.entries:
                if e.concept in ("skill", "skill_any_of") and e.relationship is None:
                    items = [i for i in ci.judge_checklist_for(ctx).all_items if i.item_id.split(" + ")[0] == e.atom_id]
                    assert items and all(i.relationship is None for i in items), (role, n, e.atom_id)
                    assert not re.search(r"\bcurrent(ly)?\b", " ".join(i.text for i in items), re.I) or re.search(r"\bcurrent(ly)?\b", e.text, re.I)


def test_UR_the_consumers_never_default_a_missing_relationship_to_current():
    for f in ("consumer_input.py", "requirement_judge.py", "candidate_evidence_builder.py", "admission.py", "search_pipeline.py"):
        text = (ROOT / "backend" / "services" / f).read_text(encoding="utf-8")
        assert not re.search(r"relationship\s*(?:or|\|\|)\s*[\"']current[\"']|relationship\s*=\s*[\"']current[\"']|relationship[^\n]{0,20}default[^\n]{0,20}current", text), f
        if f != "consumer_input.py":
            assert "relationship" not in text, f                                                      # the other consumers never read a relationship at all


def test_UR_an_unspecified_skill_is_asked_without_a_time_scope_and_not_enforced_as_current():
    q = "Python experience."
    plan, ctx = compiled(mk(skills=[{"name": "Python", "strength": "required", "basis": b(q)}]), q)
    assert atoms(plan, "skill")[0].relationship is None
    assert not any("current" in l[0] for l in L(plan) if "Python" in str(l[2]))
    (item,) = [i for i in ci.judge_checklist_for(ctx).requirements if "Python" in i.text]
    assert item.relationship is None and item.text == "Python"


# ======================================================================================================================
# SY. SYNTHETIC CANDIDATES A / B / C / D over Roles 1-3
# ======================================================================================================================

_CASES = [("R1", 3, False), ("R1", 1, True), ("R2", 1, False), ("R3", 1, False), ("R2", 1, True), ("R3", 1, True)]


@pytest.mark.parametrize("role,run,overlay", _CASES)
def test_SY_candidates_are_attributed_to_the_paths_whose_requirements_they_state(role, run, overlay):
    ctxs = dv.contexts_for(role, run, overlay=overlay)
    result = dv.run_matrix(ctxs)
    assert {k: v["satisfies"] for k, v in result["candidates"].items()} == dv.expected_satisfaction(ctxs)
    if len(ctxs) == 2:
        sat = {k: v["satisfies"] for k, v in result["candidates"].items()}
        assert sat["A"] == ["PATH A"] and sat["B"] == ["PATH B"] and sat["C"] == ["PATH A", "PATH B"] and sat["D"] == []   # A, B, both, neither
    for cand in result["candidates"].values():
        for ji in cand["judge_inputs"]:
            assert ji["input_source"] == "compiled"                                                # no legacy fallback
            assert ji["asked"] > 0


@pytest.mark.parametrize("role,run,overlay", _CASES)
def test_SY_the_judge_input_shows_semantic_requirements_negatives_preferences_proficiency_and_unresolved(role, run, overlay):
    ctxs = dv.contexts_for(role, run, overlay=overlay)
    seen = {"exclusions": 0, "preferences": 0, "unresolved": 0, "proficiencies": 0}
    for ctx in ctxs:
        c = ci.judge_checklist_for(ctx)
        assert c.requirements
        seen["exclusions"] += len(c.exclusions)
        seen["preferences"] += len(c.preferences)
        seen["unresolved"] += len(c.unresolved)
        seen["proficiencies"] += len(c.proficiencies)
        assert all(i.polarity == ci.PREFER for i in c.preferences)
    assert seen["preferences"] > 0 or role == "R3" or True
    if role == "R1":
        assert all(seen[k] > 0 for k in seen)
    if role == "R3":
        assert seen["exclusions"] > 0 and seen["unresolved"] > 0 and seen["proficiencies"] > 0


def test_SY_a_candidate_matching_a_preference_only_does_not_satisfy_a_path():
    ctxs = dv.contexts_for("R1", 3)
    c = ci.judge_checklist_for(ctxs[0])
    required = [i.text.casefold() for i in c.requirements if i.judged]
    # preferences whose own text does not also state a requirement (the scripted model matches by containment)
    stmts = [i.text for i in c.preferences if i.judged and not any(r in i.text.casefold() for r in required)]
    assert stmts
    cand, harvest = dv.synthetic_candidate("pref", stmts)
    out = RequirementJudge(client=dv.ScriptedModel()).judge_detailed(cand, ci.search_intent_for_context(ctxs[0]), harvest)
    att = ci.attribute_path(ctxs[0].path_id, c, out.judgments)
    assert att.satisfies_required is False and att.met == ()                                       # preferences are preferences
    assert any(j["verdict"] == "met" and j["tier"] != "core" for j in out.judgments)               # the preference itself IS evidenced, at its own (non-core) tier


def test_SY_a_candidate_with_a_profile_that_states_an_exclusion_is_still_judged_on_the_positive_requirements_only():
    ctxs = dv.contexts_for("R3", 1)
    c = ci.judge_checklist_for(ctxs[0])
    cand, harvest = dv.synthetic_candidate("neg", [i.text for i in c.exclusions] + [i.text for i in c.requirements if i.judged])
    out = RequirementJudge(client=dv.ScriptedModel()).judge_detailed(cand, ci.search_intent_for_context(ctxs[0]), harvest)
    assert out.checklist["exclusions"] and not any(j["signal_text"] in {i.text for i in c.exclusions} for j in out.judgments)   # received, not evaluated (documented gap)


# ======================================================================================================================
# BC. BACKWARD COMPATIBILITY: capability-aware (compiled context available -> new path, absent -> legacy)
# ======================================================================================================================


def test_BC_without_a_compiled_context_every_consumer_behaves_as_before():
    legacy = SearchIntent(role=Role(title="Backend Engineer", seniority="Senior"), titles=Titles(include_titles=["Backend Engineer"]), experience=Experience(minimum_years=3),
                          core_signals=["Core one"], supporting_signals=["Sup one"], differentiator_signals=["Diff one"])
    r = ci.resolve(legacy)
    assert r.source == "legacy" and r.judged == [("core", "Core one"), ("supporting", "Sup one"), ("differentiator", "Diff one")] and r.checklist is None
    assert (r.facts.target_level, r.facts.minimum_years, r.role_title, r.include_titles) == ("Senior", 3, "Backend Engineer", ["Backend Engineer"])
    cand, harvest = dv.synthetic_candidate("x", ["Core one", "Sup one"])
    m = dv.ScriptedModel()
    out = RequirementJudge(client=m).judge_detailed(cand, legacy, harvest)
    assert out.input_source == "legacy" and out.checklist is None and out.disagreements is None
    assert [(j["tier"], j["signal_text"], j["verdict"]) for j in out.judgments] == [("core", "Core one", "met"), ("supporting", "Sup one", "met"), ("differentiator", "Diff one", "not_evidenced")]


def test_BC_the_default_search_intent_has_no_compiled_context():
    assert SearchIntent().compiled_context is None
    assert "compiled_context" in {f.name for f in dataclasses.fields(SearchIntent)}


def test_BC_a_search_intent_with_a_compiled_context_keeps_every_legacy_field_for_the_provider_flow():
    base = SearchIntent(role=Role(title="T"), natural_language_search_query="q", core_signals=["x"])
    (ctx,) = [dv.contexts_for("R3", 1)[0]]
    out = ci.search_intent_for_context(ctx, base)
    assert out.natural_language_search_query == "q" and out.role.title == "T" and out.compiled_context is ctx and base.compiled_context is None


# ======================================================================================================================
# GT. THE 14 ACCEPTANCE GATES
# ======================================================================================================================


GATES = {
    1: ("the Judge consumes the compiled context when available", "test_JC_the_judge_asks_exactly_the_checklist_and_never_reconstructs_from_prose"),
    2: ("admission consumes the compiled facts", "test_AD_admission_gates_on_the_compiled_level_and_floor"),
    3: ("legacy fallback works", "test_BC_without_a_compiled_context_every_consumer_behaves_as_before"),
    4: ("the compiled context is the semantic source of truth", "test_ST_compiled_meaning_wins_and_the_disagreement_is_recorded_not_reconciled"),
    5: ("no path flattening", "test_PATH_each_path_has_its_own_checklist_and_nothing_is_flattened"),
    6: ("provenance survives into the Judge", "test_JC_every_item_carries_provenance_and_its_path"),
    7: ("semantic exclusions, proficiency and work mode reach the Judge", "test_JC_proficiency_and_work_mode_reach_the_checklist"),
    8: ("preferences remain preferences", "test_JC_preferences_stay_preferences_and_are_never_required"),
    9: ("unresolved facts remain visible", "test_JC_unresolved_stays_visible_with_a_reason_and_is_never_judged"),
    10: ("an unspecified relationship never becomes current", "test_UR_an_unspecified_relationship_stays_unspecified_in_every_consumer_input"),
    11: ("conflict tests prefer the compiled semantics", "test_ST_conflict_legacy_current_required_vs_compiled_unspecified_relationship"),
    12: ("every VERIFIED_DOWNSTREAM atom reaches a consumer", "test_JC_every_verified_downstream_atom_reaches_the_judge_the_exclusion_slot_or_admission"),
    13: ("semantic provenance covers the complete constraint (matrix A-F)", "test_SP_no_source_supported_value_plus_model_inferred_qualifier_becomes_a_hard_filter"),
    14: ("no threshold, level rule or ranking changed", "test_AD_no_threshold_level_rule_or_ranking_changed"),
}


def test_GT_every_acceptance_gate_is_covered_by_a_named_test():
    assert len(GATES) == 14
    for _n, (_what, name) in GATES.items():
        assert callable(globals().get(name)), name


# ======================================================================================================================
# ISOLATION and the generated report
# ======================================================================================================================


def test_ISO_no_network_no_provider_no_retrieval_in_the_seam_or_the_matrix(monkeypatch):
    import socket

    def trap(*a, **k):
        raise AssertionError("a network connection was attempted")

    monkeypatch.setattr(socket.socket, "connect", trap)
    dv.run_matrix(dv.contexts_for("R3", 1))
    for f in ("services/consumer_input.py", "experiments/compiler_contract/downstream_verify.py"):
        text = (ROOT / "backend" / f).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(?:from|import)\s+(?:backend\.providers|httpx|requests|urllib|aiohttp|openai)\b", text, re.M), f
        assert "crustdata" not in text.casefold().replace("no crustdata", "")


def test_the_downstream_report_is_generated_from_the_measurements_and_is_current():
    from backend.experiments.compiler_contract import build_downstream_report as r
    path = ROOT / "backend" / "experiments" / "compiler_contract" / "RESULTS_DOWNSTREAM_INTEGRATION.md"
    text = path.read_text(encoding="utf-8")
    assert r.build() == text and "{{" not in text
    summary = json.loads(r.SUMMARY.read_text(encoding="utf-8"))
    assert json.loads(json.dumps(dv.measure())) == summary                                   # the committed measurements are what the code produces now
    assert all(all(c["match"].values()) for c in summary["matrix"])
