"""Compiler-contract experiment tests (EXPERIMENT ONLY). Offline: no model, no network, no provider.

They pin (1) that the compiler-side code and the frozen intents were NOT changed, (2) the measurement machinery, and (3) the baseline facts about the
UNCHANGED compiler that the report states. If a later compiler change makes a baseline fact false, the matching test fails on purpose: the baseline
report then needs to be regenerated, not the test quietly edited."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from backend.experiments.compiler_contract import fate, loader, paths, probes, signature as S
from backend.experiments.compiler_contract import run_contract
from backend.experiments.compiler_contract.atoms import enumerate_atoms
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.experiments.compiler_contract.legacy_compiler_v1 import compile_intent   # the BEFORE measurements are of the legacy compiler

REPO = Path(__file__).resolve().parents[1]
CC = REPO / "backend" / "experiments" / "compiler_contract"
RESULTS = CC / "results"

# The compiler-hardening phase changed search_compiler.py, compiler_audit.py and structured_intent.py ON PURPOSE. The BEFORE measurements are of the
# byte-identical legacy copy (its hash is the old search_compiler.py hash), so that the baseline stays reproducible. The files the hardening did NOT
# touch stay pinned.
PINNED = {
    "backend/experiments/compiler_contract/legacy_compiler_v1.py": "38d0fc14ac659e47835cc195e816502b5dddd01fa2049e0eec7f962b0df781cd",
    "backend/services/crustdata_capabilities.py": "c2038c5754ab26e4d5fdaed60da2ac27a32e36271202863963554611524a6148",
    "backend/services/role_family_taxonomy.py": "8d828121ffa8a8fe334cafee92642837bd4272c4a745d836a7c34b123eebca25",
    "backend/knowledge/seniority.json": "106b55214b6b91c18573e5a63b8fb81755811a92c6cae9f20e937b20972f4534",
}


def sha(p: str) -> str:
    return hashlib.sha256((REPO / p).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def intents():
    return loader.load_all()


@pytest.fixture(scope="module")
def analysis():
    return json.loads((RESULTS / "contract_analysis.json").read_text(encoding="utf-8"))


# --- 1. nothing outside the experiment changed -------------------------------------------------------------------------


@pytest.mark.parametrize("path,digest", sorted(PINNED.items()))
def test_compiler_side_files_are_unchanged(path, digest):
    assert sha(path) == digest


def test_stored_intents_are_the_frozen_ones(intents):
    manifest = json.loads((RESULTS / "baseline_manifest.json").read_text(encoding="utf-8"))
    assert loader.source_hashes() == manifest["source_run_file_sha256"]
    assert len(intents) == 15


def test_experiment_modules_make_no_model_or_provider_call():
    forbidden = re.compile(r"^\s*(?:from|import)\s+(?:openai|requests|httpx|urllib|socket|aiohttp|backend\.providers|backend\.experiments\.crustdata_retrieval|"
                           r"backend\.experiments\.intake_strategy\.run_|backend\.experiments\.intake_strategy\.experimental_extractor)", re.M)
    for f in CC.glob("*.py"):
        assert not forbidden.search(f.read_text(encoding="utf-8")), f.name


def test_nothing_in_the_experiment_modifies_the_compiler_or_the_schema():
    text = "".join(f.read_text(encoding="utf-8") for f in CC.glob("*.py"))
    assert "monkeypatch" not in text and "setattr(search_compiler" not in text


# --- 2. the measurement machinery ---------------------------------------------------------------------------------------


def test_ablating_nothing_reproduces_the_baseline_plan(intents):
    for it in intents.values():
        again = ExperimentalHiringIntent.model_validate(it.model_dump())
        assert S.signature(compile_intent(again)) == S.signature(compile_intent(it))


def test_analysis_is_deterministic(intents):
    for key in (("R1", 2), ("R2", 3), ("R3", 4)):
        a = fate.analyse(intents[key])
        b = fate.analyse(intents[key])
        assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def test_ablating_a_required_current_skill_changes_the_provider_plan():
    it = probes.mk(skills=[{"name": "SQL", "strength": "required", "relationship": "current"}])
    base = S.signature(compile_intent(it))
    ab = S.signature(compile_intent(probes.mk()))
    dl = S.delta(base, ab)
    assert dl["leaves_lost"] and not dl["empty"]


def test_ablating_a_proficiency_changes_nothing_in_the_output():
    it = probes.mk(skills=[{"name": "SQL", "strength": "required", "relationship": "any", "proficiency": "hands_on"}])
    d = it.model_dump()
    d["skills"][0]["proficiency"] = None
    assert S.delta(S.signature(compile_intent(it)), S.signature(compile_intent(ExperimentalHiringIntent.model_validate(d))))["empty"]


def test_read_set_and_ablation_agree(intents, analysis):
    """Concepts the tracer says are never read are exactly the concepts whose atoms have an empty delta."""
    union = set()
    for it in intents.values():
        union |= S.read_set(it)
    never_read = {"domain", "semantic_exclusions", "sourcing_paths", "reconciliations", "role_archetype", "skills[].proficiency", "seniority.leadership",
                  "seniority.alternatives", "location.countries", "location.remote", "location.work_mode", "skills[].basis"}
    assert not (never_read & union)
    dropped_concepts = {"domain", "semantic_exclusion", "sourcing_path", "reconciliation", "role_archetype", "skill.proficiency", "seniority.leadership",
                        "seniority.alternatives", "location.country", "location.remote", "location.work_mode", "provenance.basis"}
    for run in analysis["runs"].values():
        for a in run["atoms"]:
            if a["concept"] in dropped_concepts:
                assert a["fate"] == "SILENTLY_DROPPED", a


def test_every_atom_has_exactly_one_fate_from_the_closed_set(analysis):
    for run in analysis["runs"].values():
        for a in run["atoms"]:
            assert a["fate"] in fate.FATES


def test_a_same_word_in_another_row_is_not_a_justification():
    """Path A 'Lead' must not be 'justified' because a global row says value=Lead."""
    it = probes.mk(seniority={"value": "Lead", "strength": "required"},
                   sourcing_paths=[{"id": "PATH A", "label": "a", "strategy": "domain_led", "seniority": {"value": "Lead", "strength": "preferred"}}])
    atoms = [a for a in fate.analyse(it)["atoms"] if a["scope"] == "path:PATH A" and a["concept"] == "seniority.value"]
    assert atoms and atoms[0]["fate"] == "SILENTLY_DROPPED"


def test_the_baseline_files_equal_a_fresh_compile(intents):
    for (role, n), it in intents.items():
        rec = json.loads((RESULTS / "baseline" / f"{role}_run{n}.json").read_text(encoding="utf-8"))
        assert rec["filter_tree"] == compile_intent(it).filter_tree


# --- 3. baseline facts about the UNCHANGED compiler (the report's claims) ----------------------------------------------


def _count(analysis, role, concept, fate_name, scope=None):
    n = 0
    for k, run in analysis["runs"].items():
        if k.startswith(role):
            for a in run["atoms"]:
                if a["concept"] == concept and a["fate"] == fate_name and (scope is None or (a["scope"] == "global") == (scope == "global")):
                    n += 1
    return n


def test_prediction_1_extended_fields_are_never_read(analysis):
    for role in ("R1", "R2", "R3"):
        for concept in ("domain", "semantic_exclusion", "skill.proficiency", "location.work_mode"):
            for k, run in analysis["runs"].items():
                if k.startswith(role):
                    assert all(a["fate"] == "SILENTLY_DROPPED" for a in run["atoms"] if a["concept"] == concept)
    assert _count(analysis, "R1", "sourcing_path", "SILENTLY_DROPPED") == 10
    assert _count(analysis, "R3", "location.work_mode", "SILENTLY_DROPPED") == 5


def test_prediction_2_role1_plans_have_no_geography(analysis):
    for k, run in analysis["runs"].items():
        if k.startswith("R1"):
            assert not [l for l in run["plan_leaves"] if "location" in l[0]], k


def test_role1_runs_2_to_5_compile_to_a_single_title_leaf(analysis):
    for n in (2, 3, 4, 5):
        assert analysis["runs"][f"R1/{n}"]["hard_leaf_count"] == 1


def test_prediction_3_strength_is_ignored_for_experience_and_location():
    s = {(r["construct"], r["strength"]): r["hard_leaves"] for r in probes.strength_relationship_sweep()}
    assert s[("experience", "preferred")] == s[("experience", "required")] == 2
    assert s[("location", "preferred")] == s[("location", "required")] == 3


def test_prediction_4_preferred_education_has_no_audit_row_and_no_leaf():
    s = {(r["construct"], r["strength"]): r for r in probes.strength_relationship_sweep()}
    r = s[("education(degree+stream)", "preferred")]
    assert r["hard_leaves"] == 0 and r["audit"] is None


def test_strength_context_is_treated_as_required_by_the_compiler():
    s = {(r["construct"], r["strength"], r["relationship"]): r["hard_leaves"] for r in probes.strength_relationship_sweep()}
    assert s[("skill", "context", "current")] == s[("skill", "required", "current")] == 3
    assert s[("skill", "preferred", "current")] == 0
    assert s[("company", "context", "any")] == 1 and s[("company", "preferred", "any")] == 0


def test_prediction_5_omitted_relationship_equals_explicit_current_and_is_a_hard_filter(analysis):
    """BEFORE fact, read from the committed baseline measurement (the live models no longer default to `current`; see the hardening tests)."""
    r = analysis["probes"]["relationship_omission"]
    assert r["defaults"]["SkillReq"] == "current" and r["defaults"]["CompanyReq"] == "any"
    assert r["omitted_equals_explicit_current_after_validation"]
    assert r["compiled_output_identical_omitted_vs_explicit_current"]
    assert r["intent_hash_identical_omitted_vs_explicit_current"]
    assert r["E_omitted_required_creates_hard_filter"] and r["B_explicit_any_required"]["hard_leaves"] == 0
    assert not r["compiler_can_distinguish_omitted_from_explicit_current"]


def test_the_model_never_omitted_relationship_in_the_stored_runs():
    m = json.loads((RESULTS / "baseline_manifest.json").read_text(encoding="utf-8"))["relationship_omission_in_raw_model_output"]
    assert m["available"] and all(v["relationship_omitted_in_raw_output"] == 0 for v in m["per_role"].values())


def test_prediction_6_multi_entry_and_two_part_locations_lose_state_and_country():
    c = {r["case"]: r for r in probes.location_probes()}
    assert len(c["one_entry_3part"]["leaves"]) == 3
    assert len(c["two_entries_3part"]["leaves"]) == 1 and len(c["one_entry_2part"]["leaves"]) == 1
    assert c["countries_only"]["leaves"] == [] and c["work_mode_only"]["leaves"] == []


def test_prediction_7_any_skill_probe_field_is_not_in_the_capability_map():
    n = probes.capability_notes()
    assert n["experience.employment_details.description"]["in_map"] is False
    assert n["work_mode"]["filter_status"] == "unavailable"


def test_prediction_8_the_analogy_title_reaches_the_title_filter(analysis):
    for n in range(1, 6):
        ck = {c["id"]: c for c in analysis["runs"][f"R2/{n}"]["checks"]}["R2-06"]
        assert ck["result"] == "FAIL" and any("Forward Deployed" in t for t in ck["evidence"]["title_leaves"])


def test_prediction_9_unknown_levels_are_carried_verbatim():
    for r in probes.seniority_probes():
        assert r["compiler_carries_value_verbatim"]
    by = {r["value"]: r for r in probes.seniority_probes()}
    assert by["Senior Manager"]["downstream_level_marker"][1] == "senior" and by["Staff"]["in_seniority_json"] is False


def test_prediction_10_no_concept_becomes_a_company_or_title_filter(analysis):
    for k, run in analysis["runs"].items():
        assert not any(l[1] in ("(!)", "not_in") for l in run["plan_leaves"]), k
    for k, run in analysis["runs"].items():
        if k.startswith("R3"):
            assert not any("company_name" in l[0] for l in run["plan_leaves"])
    assert not probes.exclusion_probes()["semantic_exclusion_creates_negative_leaf"]


def test_the_role2_overlay_is_labelled_and_the_stored_intents_lack_both_facts(intents):
    for n in range(1, 6):
        it = intents[("R2", n)]
        assert all(s.proficiency != "advanced" for s in it.skills)
        assert it.location.work_mode is None
        ov = probes.role2_overlay(n)
        assert "SYNTHETIC" in probes.role2_overlay.__doc__ and ov["intent"].location.work_mode == "hybrid"


def test_path_comparison_uses_the_unchanged_compiler_and_finds_a_difference(intents):
    for n in range(1, 6):
        r = paths.compare(intents[("R1", n)])
        assert r["has_paths"] and not r["plan_mentions_any_path"]
        assert any(p["needed_by_path_but_absent_from_plan"] for p in r["paths"])


def test_the_audit_checklist_loses_proficiency(analysis):
    s = analysis["probes"]["checklist_sample_R3"]
    assert any(r == "Microsoft Excel" for _t, r in [(x["tier"], x["requirement"]) for x in s["downstream_checklist"]])
    assert not any("advanced" in x["requirement"].lower() for x in s["downstream_checklist"])


def test_the_report_is_generated_from_the_analysis_and_is_current():
    from backend.experiments.compiler_contract import build_report
    path = CC / "RESULTS_COMPILER_CONTRACT.md"
    before = path.read_text(encoding="utf-8")
    after = build_report.build()
    assert before == after
    assert "{{" not in after
