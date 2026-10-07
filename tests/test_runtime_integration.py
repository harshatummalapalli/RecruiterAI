"""Offline RUNTIME-INTEGRATION tests: does the meaning the compiler preserved survive past the compiler boundary?

No provider, no model, no real candidate data (the synthetic candidates below are invented), no scoring or ranking. A structural contract test, not a relevance test.
See backend/services/RUNTIME_INTEGRATION_CONTRACT.md."""

from __future__ import annotations

import copy
import dataclasses
import re
import socket
from pathlib import Path

import pytest

from backend.experiments.compiler_contract import loader, runtime_verify
from backend.experiments.compiler_contract.signature import leaves
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.models.candidate import Candidate
from backend.models.structured_intent import CompanyReq, SkillReq, StructuredHiringIntent, parse_structured_intent
from backend.services import compiler_audit as audit
from backend.services.downstream_context import (ADMISSION, GAPS, JUDGE_EXCLUSION, JUDGE_REQUIREMENT, PATH, PREFERENCE, PROVIDER_ENFORCED, UNRESOLVED_ITEM,
                                                 ContextEntry, DownstreamContext, build_downstream_contexts, legacy_consumer_gaps, to_judge_signals)
from backend.services.path_merge import MergedCandidateEvidence, candidate_identity, merge_path_results
from backend.services.search_compiler import FATES, compile_intent
from backend.services.source_provenance import SourceTexts, classify_title, quote_in_sources

ROOT = Path(__file__).resolve().parents[1]
BASE = {"role_archetype": {"value": "hybrid", "confidence": 0.5, "rationale": "t"}, "role_family": ["Probe Role"]}


def mk(**kw) -> ExperimentalHiringIntent:
    return ExperimentalHiringIntent.model_validate({**copy.deepcopy(BASE), **kw})


def b(quote, sources=("jd",)):
    return {"sources": list(sources), "quote": quote}


# a recorded-mode anchor: one atom with provenance makes the intent a provenance-carrying intent
ANCHOR = {"evidence_signals": [{"name": "anchor", "strength": "required", "basis": b("Anchor sentence.")}]}


def recorded(**kw) -> ExperimentalHiringIntent:
    return mk(**{**ANCHOR, **kw})


def src(text="We are hiring a Probe Role. Anchor sentence."):
    return SourceTexts(jd=text)


def L(plan):
    return leaves(plan.filter_tree)


def atoms(plan, concept):
    return [a for a in plan.atom_audit if a.concept == concept]


# ======================================================================================================================
# 2. PROVENANCE HARDENING (generic)
# ======================================================================================================================

# every intent field that can become a provider hard filter, as a recorded-mode atom with NO provenance of its own
_NO_PROVENANCE = {
    "role_family": (dict(role_family=["Probe Role"]), "current.title"),
    "skill": (dict(skills=[{"name": "Rust", "strength": "required", "relationship": "current"}]), "description"),
    "skill_any_of": (dict(skill_any_of=[{"any_of": ["Rust", "Go"], "strength": "required", "relationship": "current"}]), "description"),
    "company": (dict(companies=[{"name": "Acme", "strength": "required", "relationship": "current"}]), "company_name"),
    "company_scale": (dict(company_scale={"minimum_employees": 5000, "strength": "required", "relationship": "current"}), "headcount"),
    "education": (dict(education={"degrees": ["B.Tech"], "streams": ["CS"], "strength": "required"}), "education.schools"),
    "experience": (dict(experience={"minimum_years": 7, "strength": "required"}), "years_of_experience_raw"),
    "location": (dict(location={"entries": ["Pune, Maharashtra, India"], "strength": "required"}), "location.city"),
    "exclusion": (dict(exclusions=[{"kind": "exclude_past_company", "value": "Acme"}]), "company_name"),
}
_STATES = "We are hiring a Probe Role. Anchor sentence. Rust and Go experience. Acme is a target. A company of 5,000 employees. B.Tech in CS. 7 years. Pune, Maharashtra, India. Not Acme."


@pytest.mark.parametrize("concept", sorted(_NO_PROVENANCE))
def test_P_a_hard_filter_needs_provenance_and_absence_withholds_it(concept):
    kw, fld = _NO_PROVENANCE[concept]
    base = {"role_family": ["Probe Role"]}
    # an intent that records provenance, an atom that has none, and no source text to check it against -> NO hard filter, an explicit fate and reason
    intent = recorded(**{k: v for k, v in kw.items()})
    plan = compile_intent(intent)
    leaf_fields = [l[0] for l in L(plan)]
    assert not any(fld in f for f in leaf_fields), (concept, leaf_fields)
    a = next(a for a in plan.atom_audit if a.concept.startswith(concept.split("_any")[0]) or a.concept.startswith(concept) or a.concept == "role_family")
    assert a.fate in ("UNRESOLVED", "VERIFIED_DOWNSTREAM", "PREFERENCE_CONTEXT") and a.provenance["state"] == "absent"
    assert "never a hard provider filter" in a.justification
    # the same atom, once the SOURCE text states it, may be a filter
    plan2 = compile_intent(intent, SourceTexts(jd=_STATES))
    if concept not in ("skill", "skill_any_of"):          # (skills are checked below: their fate depends on the relationship)
        assert any(fld in l[0] for l in L(plan2)), (concept, [l[0] for l in L(plan2)])
    assert hard_filter_states(plan2) <= {"source", "knowledge"}


def hard_filter_states(plan):
    recs = list(plan.atom_audit) + [a for p in plan.paths for a in p.atom_audit]
    return {a.provenance["state"] for a in recs if a.fate in ("ENFORCED", "NORMALIZED")}


def test_P_an_atom_the_source_does_not_state_stays_withheld_even_with_a_source():
    plan = compile_intent(recorded(skills=[{"name": "Rust", "strength": "required", "relationship": "current"}]), src("We are hiring a Probe Role. Anchor sentence. Python."))
    assert not any("Rust" in l[2] for l in L(plan))
    assert atoms(plan, "skill")[0].provenance["state"] == "absent" and atoms(plan, "skill")[0].fate == "VERIFIED_DOWNSTREAM"


def test_P_a_skill_the_source_states_is_enforced_when_its_relationship_is_explicit():
    plan = compile_intent(recorded(skills=[{"name": "Rust", "strength": "required", "relationship": "current"}]), SourceTexts(jd=_STATES))
    a = atoms(plan, "skill")[0]
    assert a.fate == "ENFORCED" and a.provenance["state"] == "source" and a.provenance["classified"] == "source_text"


def test_P_a_legacy_intent_that_records_no_provenance_keeps_its_behaviour_and_says_so():
    plan = compile_intent(mk(skills=[{"name": "Rust", "strength": "required", "relationship": "current"}]))
    assert plan.provenance_mode == "legacy" and atoms(plan, "skill")[0].provenance["state"] == "unrecorded" and atoms(plan, "skill")[0].fate == "ENFORCED"
    plan2 = compile_intent(recorded(skills=[{"name": "Rust", "strength": "required", "relationship": "current"}]))
    assert plan2.provenance_mode == "recorded"


@pytest.mark.parametrize("sources,state,hard", [(("inferred",), "model_only", False), (("approved_knowledge",), "knowledge", True), (("jd",), "source", True),
                                                (("recruiter_brief",), "source", True), (("inferred", "jd"), "source", True)])
def test_P_basis_sources_decide_the_provenance_state(sources, state, hard):
    plan = compile_intent(recorded(skills=[{"name": "Rust", "strength": "required", "relationship": "current", "basis": b("Rust and Go experience.", sources)}]),
                          SourceTexts(jd="We are hiring a Probe Role. Anchor sentence. Rust and Go experience.", recruiter_brief="Rust and Go experience."))
    a = atoms(plan, "skill")[0]
    assert a.provenance["state"] == state and (a.fate == "ENFORCED") == hard


def test_P_a_cited_quote_that_is_not_in_the_source_text_is_not_trusted():
    plan = compile_intent(recorded(skills=[{"name": "Rust", "strength": "required", "relationship": "current", "basis": b("Rust is mandatory here.")}]), src())
    a = atoms(plan, "skill")[0]
    assert a.provenance["state"] == "unverified_quote" and a.fate == "VERIFIED_DOWNSTREAM" and not any("Rust" in l[2] for l in L(plan))
    assert quote_in_sources("rust AND go experience", SourceTexts(jd="Rust and Go experience.")) == "jd"       # case / punctuation insensitive


def test_P_the_frozen_intents_have_no_unsupported_hard_filter_and_every_cited_quote_verifies():
    for (role, n), it in loader.load_all().items():
        sources = loader.sources_for(role)
        plan = compile_intent(it, sources)
        assert runtime_verify.hard_filter_provenance(plan, it)["violations"] == [], (role, n)
        recs = list(plan.atom_audit)
        assert not [a for a in recs if a.provenance["state"] == "unverified_quote"], (role, n)


def test_P_the_gate_is_generic_no_role_value_is_special_cased():
    forbidden = ["Forward Deployed", "Telangana", "Hyderabad", "Staff", "Senior Manager", "FP&A", "Data Analyst", "Power Query", "Solution Architect", "Role 1", "Role 2", "Role 3"]
    for f in ("search_compiler.py", "source_provenance.py", "downstream_context.py", "path_merge.py"):
        text = (ROOT / "backend" / "services" / f).read_text(encoding="utf-8")
        code = re.sub(r'""".*?"""', "", text, flags=re.S)
        code = "\n".join(l.split("#")[0] for l in code.splitlines())
        for term in forbidden:
            assert term not in code, f"{f} mentions {term!r} in code"


# ======================================================================================================================
# 3. ANALOGY SAFETY
# ======================================================================================================================

_CUES = ["more like a", "similar to a", "resembles a", "akin to a", "comparable to a", "reminiscent of a", "someone like a", "like a"]


@pytest.mark.parametrize("cue", _CUES)
def test_A_a_title_the_source_only_compares_to_never_reaches_a_title_filter(cue):
    text = f"We want a Probe Role. Look for a Zorp Wrangler who builds things, {cue} Quantum Plumber who fixes the lines."
    assert classify_title("Quantum Plumber", SourceTexts(jd=text)).state == "comparison"
    plan = compile_intent(recorded(role_family=["Probe Role", "Quantum Plumber"]), SourceTexts(jd=text + " Anchor sentence."))
    titles = [l[2] for l in L(plan) if l[0].endswith("current.title")]
    assert titles == ['"Probe Role"']
    a = next(a for a in atoms(plan, "role_family") if a.value == "Quantum Plumber")
    assert a.fate == "UNRESOLVED" and a.provenance["state"] == "comparison" and "comparison" in a.justification


def test_A_a_title_stated_as_a_target_is_not_demoted_by_a_comparison_elsewhere():
    t = SourceTexts(jd="We are hiring a Quantum Plumber.", recruiter_brief="Someone more like a Quantum Plumber would be ideal.")
    assert classify_title("Quantum Plumber", t).state == "target"
    assert classify_title("Quantum Plumber", SourceTexts(jd="We need a Zorp Wrangler.")).state == "absent"


def test_A_the_real_role2_analogy_title_is_withheld_through_source_classification_only():
    sources = loader.sources_for("R2")
    for n in range(1, 6):
        it = loader.load_intent("R2", n)
        assert "Forward Deployed Engineer" in it.role_family
        plan = compile_intent(it, sources)
        titles = [l[2] for l in L(plan) if l[0].endswith("current.title")]
        assert '"Forward Deployed Engineer"' not in titles and '"Solution Architect"' in titles and '"Software Engineer"' in titles, (n, titles)
        a = next(a for a in atoms(plan, "role_family") if a.value == "Forward Deployed Engineer")
        assert a.provenance["state"] == "comparison" and a.fate == "UNRESOLVED"


def test_A_without_the_source_text_no_title_of_a_provenance_carrying_intent_is_a_filter():
    for n in range(1, 6):
        plan = compile_intent(loader.load_intent("R2", n))
        assert [l for l in L(plan) if l[0].endswith("current.title")] == []


# ======================================================================================================================
# 4. RELATIONSHIP MIGRATION SAFETY
# ======================================================================================================================


def test_R_every_consumer_of_a_relationship_is_known_and_none_defaults_to_current():
    """Static audit of production code (backend/, excluding experiments): the set of files that read a relationship, and no `or "current"` style default."""
    files = set()
    bad = []
    for path in (ROOT / "backend").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if "/experiments/" in rel:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"\.relationship\b|\[.relationship.\]|get\(.relationship.|\"relationship\"", text):
            files.add(rel)
        for m in re.finditer(r"relationship[^\n]{0,40}(?:\bor\b|\|\||,)\s*[\"']current[\"']|relationship\s*=\s*[\"']current[\"']|relationship[^\n]{0,20}default[^\n]{0,20}current", text):
            line = text[max(0, text.rfind("\n", 0, m.start())):text.find("\n", m.end())]
            if "#" in line.split("relationship")[0] or "never" in line.lower() or "NOT" in line:
                continue
            bad.append((rel, line.strip()))
    assert bad == [], bad
    assert files == {"backend/models/structured_intent.py", "backend/services/search_compiler.py",
                     "backend/services/structured_intent_extractor.py", "backend/services/downstream_context.py"}, files


@pytest.mark.parametrize("rel", ["current", "past", "any"])
def test_R_an_explicit_relationship_keeps_its_meaning_everywhere(rel):
    sk = SkillReq.model_validate_json(f'{{"name": "SQL", "relationship": "{rel}"}}')
    assert sk.relationship == rel
    it = recorded(skills=[{"name": "SQL", "strength": "required", "relationship": rel, "basis": b("SQL.")}])
    plan = compile_intent(it, src("We are hiring a Probe Role. Anchor sentence. SQL."))
    a = atoms(plan, "skill")[0]
    assert a.relationship == rel
    (ctx,) = build_downstream_contexts(plan)
    e = next(e for e in ctx.entries if e.concept == "skill")
    assert e.relationship == rel
    assert (a.fate == "ENFORCED") == (rel in ("current", "past"))


def test_R_an_unspecified_relationship_never_becomes_current_in_any_layer():
    sk = SkillReq.model_validate_json('{"name": "SQL"}')
    assert sk.relationship is None and "relationship" not in sk.model_dump(exclude_none=True)
    it = mk(skills=[{"name": "SQL", "strength": "required"}], skill_any_of=[{"any_of": ["A", "B"], "strength": "required"}],
            company_scale={"minimum_employees": 100, "strength": "required"})
    again = ExperimentalHiringIntent.model_validate_json(it.model_dump_json())
    assert again.skills[0].relationship is None and again.skill_any_of[0].relationship is None and again.company_scale.relationship is None
    plan = compile_intent(it)
    assert not any("current" in l[0] or "headcount" in l[0] for l in L(plan) if not l[0].endswith("current.title"))
    for a in plan.atom_audit:
        if a.concept in ("skill", "skill_any_of", "company_scale"):
            assert a.relationship is None and a.fate != "ENFORCED"
    (ctx,) = build_downstream_contexts(plan)
    assert [e.relationship for e in ctx.entries if e.concept in ("skill", "skill_any_of", "company_scale")] == [None, None, None]
    # the audit hash tells omitted and explicit-current apart now
    explicit = mk(skills=[{"name": "SQL", "strength": "required", "relationship": "current"}])
    assert audit.intent_hash(mk(skills=[{"name": "SQL", "strength": "required"}])) != audit.intent_hash(explicit)


def test_R_the_extractor_repairs_never_turn_a_missing_relationship_into_current():
    from backend.services.structured_intent_extractor import _fix_strength_relationship, _normalize
    e = {"name": "SQL", "strength": "required"}
    _fix_strength_relationship(e)
    assert "relationship" not in e or e["relationship"] is None
    e = {"name": "SQL", "relationship": "required"}          # a strength word in the relationship slot: repaired to `any`, not `current`
    _fix_strength_relationship(e)
    assert e["relationship"] == "any" and e["strength"] == "required"
    out = _normalize({"skills": [{"name": "A", "strength": "required"}], "skill_any_of": [{"any_of": ["Only"]}]})
    assert all(s.get("relationship") is None for s in out["skills"])


def test_R_the_company_default_is_unchanged_and_the_old_fixtures_still_parse_with_explicit_values():
    assert CompanyReq(name="Acme").relationship == "any"
    for name in ("python_backend_hyderabad", "epiq_product_owner"):
        it = parse_structured_intent((ROOT / "tests" / "fixtures" / "structured_intent" / f"{name}.expected.json").read_text(encoding="utf-8"))
        assert all(s.relationship in ("current", "past", "any") for s in it.skills) and all(g.relationship for g in it.skill_any_of)


# ======================================================================================================================
# 5. PATH-AWARE DOWNSTREAM CONTRACT (Role 1)
# ======================================================================================================================


def r1(n):
    it = loader.load_intent("R1", n)
    plan = compile_intent(it, loader.sources_for("R1"))
    return it, plan, {c.path_id: c for c in build_downstream_contexts(plan)}


def texts(entries):
    return {e.text for e in entries}


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_C_role1_path_contexts_keep_each_path_apart(n):
    it, plan, ctx = r1(n)
    A, B = ctx["PATH A"], ctx["PATH B"]
    assert (A.strategy, B.strategy) == ("domain_led", "capability_led") and set(ctx) == {"PATH A", "PATH B"}
    la, lb = ({(l[0].split(".")[-1], l[2]) for l in leaves(c.provider_plan)} for c in (A, B))
    # Path A: India + remote acceptable, domain-led, no 6+ years, Power Query waived
    assert ("country", '["India"]') in la and not any(x[0] == "city" for x in la) and ("years_of_experience_raw", "6") not in la
    remote = [e for e in A.entries if e.concept == "location.remote"]
    assert remote and remote[0].text == "allowed" and remote[0].fate == "PREFERENCE_CONTEXT" and remote[0].scope == "path:PATH A"
    assert not any(e.concept == "location.remote" for e in B.entries)
    pq_a = [e for e in A.entries if e.concept == "skill" and e.text == "Power Query"]
    assert not [e for e in pq_a if e.kind == JUDGE_REQUIREMENT and e.tier == "core"]                    # waived on A: absent, or only a preference
    # Path B: Hyderabad / Pune, 6+ years, Power Query required (working knowledge), capability-led
    assert ("city", '["Hyderabad", "Pune"]') in lb and ("years_of_experience_raw", "6") in lb and not any(x[0] == "country" and x[1] == '["India"]' for x in lb)
    pq_b = [e for e in B.entries if e.concept == "skill" and e.text == "Power Query"]
    assert pq_b and pq_b[0].kind == JUDGE_REQUIREMENT and pq_b[0].tier == "core" and pq_b[0].scope == "path:PATH B" and not pq_b[0].inherited
    prof_b = [e for e in B.entries if e.concept == "skill.proficiency" and "Power Query" in e.text]
    assert prof_b and prof_b[0].proficiency == "working_knowledge" and prof_b[0].text == "working knowledge of Power Query"
    assert not any(e.concept == "skill.proficiency" and "Power Query" in e.text and e.kind == JUDGE_REQUIREMENT for e in A.entries)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_C_no_path_atom_appears_in_another_path_and_nothing_is_flattened(n):
    it, plan, ctx = r1(n)
    assert len(ctx) == 2 and None not in ctx
    own = {pid: {e.atom_id for e in c.entries if e.scope == f"path:{pid}"} for pid, c in ctx.items()}
    assert own["PATH A"].isdisjoint(own["PATH B"])
    for pid, c in ctx.items():
        other = "PATH B" if pid == "PATH A" else "PATH A"
        assert not [e for e in c.entries if e.scope == f"path:{other}"]
    # the contexts' provider plans are the path plans, not one plan
    assert ctx["PATH A"].provider_plan != ctx["PATH B"].provider_plan
    # every context holds the SAME global atoms as inherited, marked as such, and its own path atoms as path-specific
    assert ctx["PATH A"].inherited and ctx["PATH B"].path_specific and ctx["PATH A"].path_specific


def test_C_role1_run1_is_an_intake_error_not_a_context_error():
    it, plan, ctx = r1(1)           # the intake put 6+ years in the GLOBAL intent: it is (correctly, as stated) inherited by both paths
    for c in ctx.values():
        e = next(e for e in c.entries if e.concept == "experience.min")
        assert e.scope == "global" and e.inherited


def test_C_each_context_carries_the_location_and_keeps_work_mode_apart_from_geography():
    it, plan, ctx = r1(2)
    assert "country" in ctx["PATH A"].location and "entry" in ctx["PATH B"].location and "entry" not in ctx["PATH A"].location
    plan3 = compile_intent(loader.load_intent("R3", 2), loader.sources_for("R3"))
    (c3,) = build_downstream_contexts(plan3)
    assert set(c3.location) >= {"entry", "work_mode"} and c3.location["work_mode"][0]["text"] == "hybrid"


# ======================================================================================================================
# 6. DOWNSTREAM EVIDENCE ROUTING (every VERIFIED_DOWNSTREAM atom reaches the context)
# ======================================================================================================================


def test_D_every_verified_downstream_atom_has_an_explicit_downstream_entry_in_every_context_it_applies_to():
    n_checked = 0
    for (role, n), it in loader.load_all().items():
        plan = compile_intent(it, loader.sources_for(role))
        ctxs = build_downstream_contexts(plan)
        for c in ctxs:
            source = plan.atom_audit if c.path_id is None else next(p for p in plan.paths if p.path_id == c.path_id).atom_audit
            want = {a.atom_id for a in source if a.fate == "VERIFIED_DOWNSTREAM"}
            got = {e.atom_id for e in c.entries if e.fate == "VERIFIED_DOWNSTREAM"}
            assert want == got, (role, n, c.path_id, want ^ got)
            for e in c.entries:
                if e.fate == "VERIFIED_DOWNSTREAM":
                    assert e.kind in (JUDGE_REQUIREMENT, JUDGE_EXCLUSION, ADMISSION) and e.text.strip() and e.provenance.get("state")
            n_checked += len(want)
    assert n_checked > 500


def test_D_the_extension_meanings_are_visible_to_the_downstream_consumer():
    plan = compile_intent(loader.load_intent("R3", 2), loader.sources_for("R3"))
    (ctx,) = build_downstream_contexts(plan)
    by = {}
    for e in ctx.entries:
        by.setdefault(e.concept, []).append(e)
    sem = by["semantic_exclusion"][0]
    assert sem.kind == JUDGE_EXCLUSION and "statutory audit" in sem.text and sem.fate == "VERIFIED_DOWNSTREAM"               # B: exclusion visible, as a negative
    prof = by["skill.proficiency"][0]
    assert prof.kind == JUDGE_REQUIREMENT and prof.proficiency == "advanced" and prof.text == "advanced proficiency in Microsoft Excel"        # C
    wm = by["location.work_mode"][0]
    assert wm.kind == UNRESOLVED_ITEM and wm.text == "hybrid" and "never converted" in wm.justification                       # D
    assert by["domain"] and all(e.kind in (JUDGE_REQUIREMENT, PREFERENCE) for e in by["domain"])
    assert {e.concept for e in ctx.entries} >= {"seniority.value", "company", "education.degree", "experience.min", "role_family"}
    sig = to_judge_signals(ctx)
    assert "advanced proficiency in Microsoft Excel" in sig["core"]
    assert not any("statutory audit" in t for ts in sig.values() for t in ts)       # a negative is never smuggled into the positive signals


def test_D_leadership_and_domain_reach_the_context_on_role1():
    it, plan, ctx = r1(2)
    for pid, c in ctx.items():
        assert any(e.concept == "seniority.leadership" for e in c.entries) or any(e.concept == "seniority.leadership" for e in ctx["PATH A"].entries + ctx["PATH B"].entries)
    all_entries = [e for c in ctx.values() for e in c.entries]
    assert any(e.concept == "domain" and e.kind == PREFERENCE for e in all_entries)


def test_D_an_atom_with_no_provider_or_consumer_slot_is_recorded_as_a_contract_gap_not_discarded():
    plan = compile_intent(loader.load_intent("R3", 2), loader.sources_for("R3"))
    (ctx,) = build_downstream_contexts(plan)
    gaps = legacy_consumer_gaps(ctx)
    codes = {(g["concept"], g["gap"]) for g in gaps}
    assert ("semantic_exclusion", "NO_NEGATIVE_SLOT") in codes and ("location.work_mode", "NO_UNRESOLVED_SLOT") in codes
    assert ("seniority.value", "NO_UNRESOLVED_SLOT") in codes and ("company", "PREFERENCE_NOT_FORWARDED") in codes
    ids = {e.atom_id for e in ctx.entries}
    assert all(g["atom_id"] in ids for g in gaps)                 # every gap still has its entry in the context
    assert set(GAPS) == {"NO_NEGATIVE_SLOT", "NO_UNRESOLVED_SLOT", "ADMISSION_READS_LEGACY_INTENT", "PREFERENCE_NOT_FORWARDED"}
    it, plan1, ctx1 = r1(2)
    assert any(g["gap"] == "ADMISSION_READS_LEGACY_INTENT" for g in legacy_consumer_gaps(ctx1["PATH B"]))


def test_D_the_judge_adapter_matches_the_compilers_own_checklist_per_path():
    it, plan, ctx = r1(3)
    for pid, c in ctx.items():
        expected = {(tier, text) for tier, text in audit.judge_checklist(plan, pid) if "leadership" not in text.lower()}
        sig = to_judge_signals(c)
        got = {(tier, t) for tier, ts in sig.items() for t in ts if "leadership" not in t.lower()}
        assert expected == got, (pid, expected ^ got)


# ======================================================================================================================
# 7. PREFERENCE ROUTING
# ======================================================================================================================


def test_E_preferences_survive_as_preferences_and_are_never_hardened():
    for (role, n), it in loader.load_all().items():
        plan = compile_intent(it, loader.sources_for(role))
        for c in build_downstream_contexts(plan):
            for e in c.entries:
                if e.strength in ("preferred", "context") and e.kind in (PROVIDER_ENFORCED,):
                    pytest.fail(f"{role}/{n}: a {e.strength} atom was hardened: {e.atom_id}")
                if e.fate == "PREFERENCE_CONTEXT":
                    assert e.kind == PREFERENCE and e.strength in ("preferred", "context", "required")
            prefs = {e.concept for e in c.preferences}
            if role == "R3":
                companies = [e for e in c.entries if e.concept == "company"]
                assert len(companies) == 6 and all(e.kind == PREFERENCE and e.strength == "preferred" for e in companies)
                assert not [e for e in c.entries if e.concept == "company" and e.kind != PREFERENCE]
                assert not any(l[0].endswith("company_name") for l in leaves(c.provider_plan))
                assert "Unilever" not in to_judge_signals(c)["core"]


def test_E_a_preference_is_not_given_a_rank_a_score_or_a_boost():
    names = {f.name for cls in (ContextEntry, DownstreamContext, MergedCandidateEvidence) for f in dataclasses.fields(cls)}
    assert not [n for n in names if re.search(r"score|rank|boost|weight|priority", n, re.I)], names


# ======================================================================================================================
# 8. SYNTHETIC END-TO-END (invented candidates; no provider; structural only)
# ======================================================================================================================


def cand(cid, name, company="Synthco", title="Analyst", score=None):
    return Candidate(candidate_id=cid, name=name, company=company, title=title, provider_score=score, raw_data={"synthetic": True})


def test_S_synthetic_end_to_end_across_roles_1_to_3(monkeypatch):
    def no_network(*a, **k):                # gate 10: nothing in this test may touch a network
        raise AssertionError("a network connection was attempted")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    plans = {}
    for role in ("R1", "R2", "R3"):
        it = loader.load_intent(role, 2)
        plans[role] = (it, compile_intent(it, loader.sources_for(role)))
        ctxs = build_downstream_contexts(plans[role][1])
        assert ctxs
        for c in ctxs:
            kinds = {e.kind for e in c.entries}
            assert kinds <= {PROVIDER_ENFORCED, JUDGE_REQUIREMENT, JUDGE_EXCLUSION, ADMISSION, PREFERENCE, UNRESOLVED_ITEM, "justified_drop", "record", PATH}
            assert all(e.provenance.get("state") for e in c.entries)                                  # G provenance survives
            assert all(e.fate in FATES for e in c.entries)
    # A + H: the two Role 1 contexts differ exactly where the paths differ
    (_, p1) = plans["R1"]
    a, b_ = build_downstream_contexts(p1)
    assert {e.text for e in a.path_specific} != {e.text for e in b_.path_specific}
    # F: unresolved taxonomy stays unresolved and visible
    (_, p3) = plans["R3"]
    (c3,) = build_downstream_contexts(p3)
    assert any(e.concept == "seniority.value" and e.kind == UNRESOLVED_ITEM and e.text == "Senior Manager" for e in c3.entries)
    # I: nothing was scored
    for role, (it, plan) in plans.items():
        for c in build_downstream_contexts(plan):
            assert not any(hasattr(e, "score") or hasattr(e, "rank") for e in c.entries)


def test_S_a_candidate_found_by_two_paths_carries_both_paths_obligations_apart():
    it, plan, ctx = r1(2)
    ctxs = list(ctx.values())
    results = {"PATH A": [cand("c1", "Syn One", score=0.9), cand("c2", "Syn Two", score=0.1)], "PATH B": [cand("c2", "Syn Two", score=0.7), cand("c3", "Syn Three")]}
    merged = merge_path_results(results, path_order=["PATH A", "PATH B"], contexts=ctxs)
    by_id = {m.identity[1]: m for m in merged}
    assert set(by_id) == {"c1", "c2", "c3"}
    two = by_id["c2"]
    assert two.contributing_path_ids == ("PATH A", "PATH B") and by_id["c1"].contributing_path_ids == ("PATH A",) and by_id["c3"].contributing_path_ids == ("PATH B",)
    # each contributing path's own payload is kept: nothing is overwritten and no score is merged or chosen
    assert two.per_path["PATH A"].provider_score == 0.1 and two.per_path["PATH B"].provider_score == 0.7
    # the obligations of a candidate found by both paths are BOTH paths' contexts, kept apart
    assert set(two.obligations_by_path) == {"PATH A", "PATH B"} and set(by_id["c1"].obligations_by_path) == {"PATH A"}
    a_only = {e.atom_id for e in two.obligations("PATH A")} - {e.atom_id for e in two.obligations("PATH B")}
    assert a_only and all(e.scope in ("path:PATH A", "global") for e in two.obligations("PATH A"))


# ======================================================================================================================
# 9. PATH MERGE CONTRACT
# ======================================================================================================================


def test_M_identity_is_the_existing_deduplication_key():
    assert candidate_identity(cand("x1", "N")) == ("candidate_id", "x1", None)
    assert candidate_identity(Candidate(profile_url="https://p/1")) == ("profile_url", "https://p/1", None)
    assert candidate_identity(Candidate(name="Ann Lee", company="Acme"))[0] == "name_company"
    assert candidate_identity(Candidate()) is None


def test_M_merge_keeps_all_contributing_paths_and_is_independent_of_input_order():
    r = {"B": [cand("1", "x"), cand("2", "y")], "A": [cand("2", "y"), cand("3", "z")], "C": [cand("2", "y")]}
    m1 = merge_path_results(r, path_order=["A", "B", "C"])
    m2 = merge_path_results({k: list(reversed(v)) for k, v in reversed(list(r.items()))}, path_order=["A", "B", "C"])
    assert [(m.identity, m.contributing_path_ids) for m in m1] == [(m.identity, m.contributing_path_ids) for m in m2]
    assert {m.identity[1]: m.contributing_path_ids for m in m1} == {"1": ("B",), "2": ("A", "B", "C"), "3": ("A",)}
    assert [m.identity[1] for m in m1] == sorted(m.identity[1] for m in m1)         # sorted by identity, so the order carries no path preference


def test_M_no_path_is_ranked_above_another_and_no_path_score_exists():
    r = {"A": [cand("1", "x", score=0.99)], "B": [cand("2", "y", score=0.01)]}
    m = merge_path_results(r)
    assert [x.identity[1] for x in m] == ["1", "2"]
    assert merge_path_results({"A": r["B"], "B": r["A"]}) == merge_path_results({"A": r["B"], "B": r["A"]})
    assert not [f.name for f in dataclasses.fields(MergedCandidateEvidence) if re.search(r"score|rank", f.name, re.I)]
    # provider scores are untouched
    assert m[0].per_path["A"].provider_score == 0.99 and m[1].per_path["B"].provider_score == 0.01


def test_M_a_candidate_with_no_identity_is_kept_and_flagged_never_silently_merged():
    ghost = Candidate()
    m = merge_path_results({"A": [ghost], "B": [Candidate()]})
    assert len(m) == 2 and all(not x.identity_resolved and x.identity is None for x in m) and {x.contributing_path_ids for x in m} == {("A",), ("B",)}


def test_M_the_same_candidate_twice_in_one_path_does_not_overwrite_that_paths_payload():
    first, second = cand("1", "first", score=1.0), cand("1", "second", score=2.0)
    (m,) = merge_path_results({"A": [first, second]})
    assert m.per_path["A"].name == "first" and m.contributing_path_ids == ("A",)


# ======================================================================================================================
# 10. JUDGE / ADMISSION CONSUMER AUDIT
# ======================================================================================================================


def test_J_the_judge_and_admission_still_consume_only_the_legacy_intent():
    """LEGACY DOWNSTREAM CONSUMER: none of these reads the compiled plan, a path, the downstream context, an exclusion, or provenance. If one is ever wired
    to the compiled plan this test fails on purpose: update the audit in RESULTS_RUNTIME_INTEGRATION.md and the contract."""
    compiled = re.compile(r"compile_intent|CompiledPlan|downstream_context|atom_audit|sourcing_path|semantic_exclusion|search_compiler(?!_shadow)|exclusion_checklist|AtomRecord|provenance_mode")
    for f in ("requirement_judge.py", "admission.py", "candidate_evidence_builder.py", "search_pipeline.py", "candidate_ranker.py", "match_explainer.py"):
        text = (ROOT / "backend" / "services" / f).read_text(encoding="utf-8")
        assert not compiled.search(text), f"{f} now references the compiled plan"
    judge = (ROOT / "backend" / "services" / "requirement_judge.py").read_text(encoding="utf-8")
    assert "intent.core_signals" in judge and "intent.supporting_signals" in judge and "intent.differentiator_signals" in judge
    evidence = (ROOT / "backend" / "services" / "candidate_evidence_builder.py").read_text(encoding="utf-8")
    assert "intent.role.seniority" in evidence


def test_J_the_only_production_caller_of_the_compiler_is_the_shadow_audit():
    callers = set()
    for path in (ROOT / "backend").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if "/experiments/" in rel or rel in ("backend/services/search_compiler.py",):
            continue
        if re.search(r"\bcompile_intent\(", path.read_text(encoding="utf-8")):
            callers.add(rel)
    assert callers == {"backend/services/search_compiler_shadow.py"}


def test_J_the_pipeline_reaches_the_compiler_only_through_the_shadow_hook_and_passes_it_the_jd_only():
    """LEGACY DOWNSTREAM CONSUMER / WIRING GAP: search_pipeline calls `run_shadow(search_id, jd_text, mapped_plan)` and nothing else compiled; the recruiter brief is not passed."""
    text = (ROOT / "backend" / "services" / "search_pipeline.py").read_text(encoding="utf-8")
    assert "run_shadow(search_id, jd_text, mapped_plan)" in text and "recruiter_brief" not in text.split("run_shadow(search_id")[1].split("\n")[0]


def test_J_the_shadow_audit_passes_the_source_text_to_the_compiler():
    text = (ROOT / "backend" / "services" / "search_compiler_shadow.py").read_text(encoding="utf-8")
    assert "SourceTexts(jd=jd_text" in text and "compile_intent(si, SourceTexts" in text


# ======================================================================================================================
# 12. ACCEPTANCE GATES
# ======================================================================================================================


@pytest.fixture(scope="module")
def verified():
    return {k: runtime_verify.verify_intent(it, loader.sources_for(k[0])) | {"intent": it} for k, it in loader.load_all().items()}


def test_G_gates_1_to_8_over_every_frozen_intent(verified):
    for (role, n), v in verified.items():
        plan, ctxs = v["plan"], v["contexts"]
        # 1 every hard provider filter has source / approved provenance
        assert runtime_verify.hard_filter_provenance(plan, v["intent"])["violations"] == []
        # 2 unspecified relationship never becomes current
        assert not [a for a in plan.atom_audit if a.relationship is None and a.fate == "ENFORCED" and a.concept in ("skill", "skill_any_of", "company_scale")]
        # 3 + 8 every path is independently addressable; no flattening
        assert [c.path_id for c in ctxs] == ([p.id for p in v["intent"].sourcing_paths] or [None])
        assert v["leaks"] == []
        # 4 + 6 + 7 every atom reaches the downstream context with its fate and provenance; nothing is silent at the boundary
        bad = [(r["concept"], r["value"], r["problems"]) for r in v["rows"] if r["problems"] or r["silent_at_boundary"]]
        assert bad == [], (role, n, bad)
        # 5 preferences preserved without hardening
        assert not [e for c in ctxs for e in c.entries if e.strength in ("preferred", "context") and e.kind == PROVIDER_ENFORCED]
        # 6 unresolved values remain visible, per context
        for c in ctxs:
            source = plan.atom_audit if c.path_id is None else next(p for p in plan.paths if p.path_id == c.path_id).atom_audit
            assert {a.atom_id for a in source if a.fate == "UNRESOLVED"} <= {e.atom_id for e in c.entries if e.kind == UNRESOLVED_ITEM}


def test_G_the_committed_runtime_measurements_match_the_live_run(verified):
    import json
    summary = json.loads((ROOT / "backend/experiments/compiler_contract/results/runtime_summary.json").read_text(encoding="utf-8"))
    for (role, n), v in verified.items():
        s = summary["runs"][f"{role}/{n}"]
        assert s["atoms"] == len(v["rows"]) and s["silent_at_boundary"] == 0 and s["problems"] == 0 and s["leaks"] == 0 and s["hard_filter_violations"] == 0


def test_G_no_new_module_can_reach_a_provider_or_a_model():
    forbidden = re.compile(r"^\s*(?:from|import)\s+(?:openai|requests|httpx|urllib|socket|aiohttp|backend\.providers|backend\.services\.requirement_judge|backend\.services\.search_pipeline)", re.M)
    for f in ("source_provenance.py", "downstream_context.py", "path_merge.py", "search_compiler.py"):
        assert not forbidden.search((ROOT / "backend" / "services" / f).read_text(encoding="utf-8")), f


def test_the_runtime_report_is_generated_from_the_measurements_and_is_current():
    from backend.experiments.compiler_contract import build_runtime_report
    path = ROOT / "backend" / "experiments" / "compiler_contract" / "RESULTS_RUNTIME_INTEGRATION.md"
    before = path.read_text(encoding="utf-8")
    assert build_runtime_report.build() == before and "{{" not in before
