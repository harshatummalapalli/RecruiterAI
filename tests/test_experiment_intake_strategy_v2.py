"""Experimental representation for the Role 1 intake experiment: schema, validators, evaluator, harness.

Credit-free and model-free. The exemplar intent below is hand-written to test the EVALUATOR (a correct intent passes,
each specific flaw fails the specific assertion). It says nothing about what the model produces; that is the experiment.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.experiments.intake_strategy import gold_assertions as baseline_gold
from backend.experiments.intake_strategy import gold_experimental as gold
from backend.experiments.intake_strategy import run_experimental as exp
from backend.experiments.intake_strategy.experimental_extractor import PROMPT_V2, build_prompt
from backend.experiments.intake_strategy.experimental_schema import (
    ExperimentalHiringIntent,
    effective_view,
    schema_concepts,
)
from backend.experiments.intake_strategy.run_baseline import load_inputs
from backend.experiments.intake_strategy.validators import quote_in, validate
from backend.models.structured_intent import StructuredHiringIntent

INPUTS = load_inputs()
JD, BRIEF = INPUTS["jd"], INPUTS["brief"]
REPO = Path(__file__).resolve().parents[1]


def b(source: str, quote: str | None) -> dict:
    return {"sources": [source], "quote": quote}


HANDS = "Hands-on experience with SQL and Python for data querying, analysis, automation, and reporting."
PQ_JD = "Working knowledge of Power Query for data transformation, preparation, and reporting."
LEAD_BRIEF = '"Lead" may mean people leadership OR technical leadership.'
SECMON = "Experience performing review, quality assurance, compliance, audit, or security monitoring activities."
TEAMS = "Experience leading teams, mentoring analysts, and coordinating operational workflows."
DOMAIN_Q = "Cyber Incident Review and/or Data Breach Analysis experience"


def good() -> dict:
    return {
        "role_archetype": {"value": "hybrid", "confidence": 0.9, "rationale": "analyst identity plus a domain"},
        "role_family": ["Data Analyst"],
        "seniority": {"value": "Lead", "strength": "required", "leadership": ["people", "technical"], "basis": b("recruiter_brief", LEAD_BRIEF)},
        "skills": [
            {"name": "SQL", "strength": "required", "proficiency": "hands_on", "basis": b("jd", HANDS)},
            {"name": "Python", "strength": "required", "proficiency": "hands_on", "basis": b("jd", HANDS)},
            {"name": "Power Query", "strength": "required", "proficiency": "working_knowledge", "basis": b("jd", PQ_JD)},
            {"name": "Relativity", "relationship": "any", "strength": "preferred", "basis": b("jd", "Experience with Relativity and Canopy platforms is preferred.")},
            {"name": "Canopy", "relationship": "any", "strength": "preferred", "basis": b("jd", "Experience with Relativity and Canopy platforms is preferred.")},
        ],
        "education": {"strength": "preferred", "degrees": ["Bachelor's degree"],
                      "streams": ["Cybersecurity", "Information Technology", "Computer Science", "Information Systems", "Data Analytics"],
                      "basis": b("jd", "Bachelor's degree in Cybersecurity, Information Technology, Computer Science, Information Systems, Data Analytics, or a related discipline preferred.")},
        "evidence_signals": [
            {"name": "Review, quality assurance, compliance or audit experience", "strength": "required", "basis": b("jd", SECMON)},
            {"name": "Security frameworks, data privacy and regulatory compliance standards", "strength": "preferred",
             "basis": b("jd", "Experience working with security frameworks, data privacy requirements, and regulatory compliance standards is highly desirable.")},
        ],
        "domain": [{"name": "Cyber Incident Review / Data Breach Analysis in a Legal Tech environment", "strength": "preferred", "basis": b("recruiter_brief", DOMAIN_Q)}],
        "semantic_exclusions": [{"concept": "cybersecurity operations work", "includes": ["SOC", "Security Operations", "SIEM", "Threat Detection"],
                                 "basis": b("recruiter_brief", "This is NOT cybersecurity operations.")},
                                {"concept": "A strong SQL/Python analyst working at a security firm", "includes": [],
                                 "basis": b("recruiter_brief", "A strong SQL/Python analyst working at a security firm should be excluded.")}],
        "sourcing_paths": [
            {"id": "Path A", "label": "Domain-led", "strategy": "domain_led", "basis": b("recruiter_brief", "PATH A — DOMAIN-LED CANDIDATE"),
             "seniority": {"value": "Lead", "alternatives": ["Senior"], "strength": "preferred", "leadership": ["people", "technical"],
                           "basis": b("recruiter_brief", "Lead / Senior Data Analyst identity")},
             "location": {"countries": ["India"], "remote": "allowed", "strength": "required",
                          "basis": b("recruiter_brief", "remote resources across India are acceptable")},
             "skills": [{"name": "Power Query", "strength": "preferred", "proficiency": "working_knowledge", "basis": b("recruiter_brief", "Path A does NOT require Power Query.")}],
             "domain": [{"name": "Cyber Incident Review / Data Breach Analysis in a Legal Tech environment", "strength": "required", "basis": b("recruiter_brief", DOMAIN_Q)}]},
            {"id": "Path B", "label": "Capability-led", "strategy": "capability_led", "basis": b("recruiter_brief", "PATH B — CAPABILITY-LED DATA ANALYST"),
             "experience": {"minimum_years": 6, "strength": "required", "basis": b("recruiter_brief", "Path B requires Lead level and 6+ years.")},
             "location": {"entries": ["Hyderabad, Telangana, India", "Pune, Maharashtra, India"], "strength": "required", "basis": b("recruiter_brief", "location should be Hyderabad OR Pune")}},
        ],
        "reconciliations": [
            {"topic": "security monitoring", "action": "contradicted", "jd_quote": SECMON, "brief_quote": "This is NOT a conventional security-operations role.",
             "result": "Security monitoring is not a requirement; security-operations work is a negative."},
            {"topic": "Power Query", "action": "waived", "path_id": "Path A", "jd_quote": PQ_JD, "brief_quote": "Path A does NOT require Power Query.",
             "result": "Power Query is preferred, not required, on the domain-led path."},
            {"topic": "Lead leadership", "action": "waived", "jd_quote": TEAMS, "brief_quote": LEAD_BRIEF,
             "result": "Lead is satisfied by people OR technical leadership."},
        ],
    }


def evaluate(raw: dict):
    intent = ExperimentalHiringIntent.model_validate(raw)
    result = gold.evaluate(intent, JD, BRIEF)
    return intent, {r["id"]: r for r in result["critical"]}, result["validation"]


# ---------------------------------------------------------------------------- the evaluator is calibrated


def test_a_correct_intent_passes_every_assertion() -> None:
    _, r, v = evaluate(good())
    assert {k: x["status"] for k, x in r.items() if x["status"] != gold.PASS} == {}
    assert [d for d in v["diagnostics"] if d["code"] != "quote_weakly_related"] == []  # that one is informational only
    assert {a["status"] for a in v["atoms"]} <= {"verified", "lexical"}


def test_without_paths_the_path_assertions_fail_as_extraction() -> None:
    raw = good()
    raw["sourcing_paths"] = []
    _, r, _ = evaluate(raw)
    for id_ in ("two_paths_preserved", "path_a_domain_led", "path_b_capability_led", "path_geography_differs"):
        assert (r[id_]["status"], r[id_]["failure_class"]) == (gold.FAIL, gold.EXTRACTION)


def test_power_query_required_everywhere_fails_as_reconciliation() -> None:
    raw = good()
    raw["sourcing_paths"][0]["skills"] = []
    _, r, v = evaluate(raw)
    assert (r["pq_not_mandatory_path_a"]["status"], r["pq_not_mandatory_path_a"]["failure_class"]) == (gold.FAIL, gold.RECONCILIATION)
    assert r["pq_working_knowledge_path_b"]["status"] == gold.PASS
    # the model said it was waived on A but did not apply it: code notices
    assert "reconciliation_conflict" in {d["code"] for d in v["diagnostics"]}
    assert r["reconciliation_visible"]["status"] == gold.PARTIAL


def test_proficiency_is_judged_separately_from_strength() -> None:
    raw = good()
    raw["skills"][2]["proficiency"] = None
    raw["skills"][0]["proficiency"] = "working_knowledge"
    _, r, _ = evaluate(raw)
    assert r["pq_working_knowledge_path_b"]["status"] == gold.PARTIAL
    assert r["sql_hands_on"]["status"] == gold.PARTIAL and r["python_hands_on"]["status"] == gold.PASS


def test_security_operations_kept_as_a_requirement_fails_as_reconciliation() -> None:
    raw = good()
    raw["evidence_signals"].append({"name": "security monitoring experience", "strength": "required", "basis": b("jd", SECMON)})
    _, r, _ = evaluate(raw)
    assert (r["cyber_review_not_secops"]["status"], r["cyber_review_not_secops"]["failure_class"]) == (gold.FAIL, gold.RECONCILIATION)


def test_a_missing_semantic_negative_is_partial_then_fail() -> None:
    raw = good()
    raw["semantic_exclusions"] = []
    _, r, _ = evaluate(raw)
    assert r["cyber_review_not_secops"]["status"] == gold.PARTIAL
    assert r["hard_negative_secops_preserved"]["status"] == gold.FAIL


def test_a_work_type_turned_into_a_company_exclusion_is_caught() -> None:
    raw = good()
    raw["exclusions"] = [{"kind": "exclude_current_company", "value": "Security firms", "basis": b("recruiter_brief", "A strong SQL/Python analyst working at a security firm should be excluded.")}]
    _, r, _ = evaluate(raw)
    assert r["no_invented_company_exclusion"]["status"] == gold.FAIL
    assert r["hard_negative_secops_preserved"]["status"] == gold.PASS  # the semantic negative is still there


def test_cities_invented_for_a_country_wide_path_are_caught() -> None:
    raw = good()
    raw["sourcing_paths"][0]["location"]["entries"] = ["Mumbai, Maharashtra, India"]
    _, r, v = evaluate(raw)
    assert r["path_geography_differs"]["status"] == gold.PARTIAL
    assert "place_not_in_source" in {d["code"] for d in v["diagnostics"]}  # Mumbai is in neither source


def test_a_country_written_as_a_city_entry_is_caught_twice() -> None:
    raw = good()
    raw["sourcing_paths"][0]["location"].update(countries=[], entries=["India"])
    _, r, v = evaluate(raw)
    assert r["intent_country_level_geography"]["status"] == gold.FAIL
    assert r["path_geography_differs"]["status"] != gold.PASS
    # structural check: India is the trailing component of Path B's "Hyderabad, Telangana, India", so it is a country
    assert "country_city_misrepresentation" in {d["code"] for d in v["diagnostics"]}
    assert r["generic_validators_clean"]["status"] == gold.FAIL and r["generic_validators_clean"]["failure_class"] == gold.VALIDATION


def test_a_city_in_the_countries_field_is_caught() -> None:
    raw = good()
    raw["sourcing_paths"][1]["location"].update(countries=["Hyderabad"])
    _, _, v = evaluate(raw)
    assert "country_city_misrepresentation" in {d["code"] for d in v["diagnostics"]}


def test_remote_is_typed_and_not_invented_for_the_other_path() -> None:
    raw = good()
    raw["sourcing_paths"][0]["location"]["remote"] = None
    _, r, _ = evaluate(raw)
    assert r["remote_typed"]["status"] == gold.FAIL           # remote must not survive only in quote text
    raw = good()
    raw["sourcing_paths"][1]["location"]["remote"] = "allowed"
    _, r, v = evaluate(raw)
    assert r["remote_typed"]["status"] == gold.FAIL
    assert "remote_unsupported" in {d["code"] for d in v["diagnostics"]}  # the sources state remote only for Path A
    bad = good()
    bad["sourcing_paths"][0]["location"]["remote"] = "sometimes"
    with pytest.raises(ValidationError):
        ExperimentalHiringIntent.model_validate(bad)


def test_domain_required_on_path_b_fails() -> None:
    raw = good()
    raw["domain"][0]["strength"] = "required"
    _, r, _ = evaluate(raw)
    assert r["path_b_domain_not_required"]["status"] == gold.FAIL


def test_leadership_people_only_or_a_surviving_people_requirement() -> None:
    raw = good()
    raw["seniority"]["leadership"] = ["people"]
    _, r, _ = evaluate(raw)
    assert (r["lead_people_or_technical"]["status"], r["lead_people_or_technical"]["failure_class"]) == (gold.FAIL, gold.EXTRACTION)
    raw = good()
    raw["evidence_signals"].append({"name": "leading teams and mentoring analysts", "strength": "required", "basis": b("jd", TEAMS)})
    _, r, _ = evaluate(raw)
    assert (r["lead_people_or_technical"]["status"], r["lead_people_or_technical"]["failure_class"]) == (gold.PARTIAL, gold.RECONCILIATION)


def test_dropping_jd_items_is_reported_not_hidden() -> None:
    raw = good()
    raw["skills"] = [s for s in raw["skills"] if s["name"] not in ("Relativity", "Canopy")]
    _, r, _ = evaluate(raw)
    assert r["jd_not_silently_discarded"]["status"] == gold.PARTIAL
    assert "Relativity" in r["jd_not_silently_discarded"]["evidence"]


def test_paths_are_found_by_strategy_not_by_label() -> None:
    raw = good()
    raw["sourcing_paths"][0].update(id="x1", label="Track one")
    raw["sourcing_paths"][1].update(id="x2", label="Track two", strategy="hybrid")
    raw["reconciliations"][1]["path_id"] = "x1"
    _, r, _ = evaluate(raw)
    # only the leakage check cannot run: x1 / x2 are not the source's names for the paths
    assert {k: x["status"] for k, x in r.items() if x["status"] != gold.PASS} == {"path_leakage_checkable": gold.PARTIAL}
    assert r["path_leakage_checkable"]["failure_class"] == gold.VALIDATION


# ---------------------------------------------------------------------------- hardening: leakage, levels, firm exclusion


def test_a_path_b_requirement_inherited_by_path_a_is_flagged_generically() -> None:
    raw = good()
    raw["experience"] = raw["sourcing_paths"][1].pop("experience")      # the model lifts 6+ years into the global intent
    _, r, v = evaluate(raw)
    leak = [d for d in v["diagnostics"] if d["code"] == "path_requirement_leakage"]
    assert leak and "Path A" in leak[0]["detail"] and "only for ['Path B']" in leak[0]["detail"]
    assert (r["path_b_requirements_not_in_path_a"]["status"], r["path_b_requirements_not_in_path_a"]["failure_class"]) == (gold.FAIL, gold.EXTRACTION)
    assert r["generic_validators_clean"]["status"] == gold.FAIL


def test_the_leakage_validator_knows_no_role_content() -> None:
    """Same structure, unrelated words: the check must not depend on '6+ years' or 'Path B'."""
    from backend.experiments.intake_strategy.validators import scope_checks, validate  # noqa: F401
    jd = "Claims handler role.\n"
    brief = ("Overview: we want claims handlers with 9 years of experience.\n\n"
             "OPTION ONE\n- marine claims\n- Lisbon or Porto\n\nOPTION TWO\n- any claims background\n- 9 years of experience\n"
             "Option Two requires fluent Portuguese.\n")
    raw = {"role_archetype": {"value": "hybrid", "confidence": 0.5, "rationale": "x"}, "role_family": ["Claims Handler"],
           "experience": {"minimum_years": 9, "strength": "required"},
           "sourcing_paths": [{"id": "Option One", "label": "marine", "strategy": "domain_led"},
                              {"id": "Option Two", "label": "generalist", "strategy": "capability_led"}]}
    v = validate(ExperimentalHiringIntent.model_validate(raw), jd, brief)
    leaks = [d for d in v["diagnostics"] if d["code"] == "path_requirement_leakage"]
    assert len(leaks) == 1 and "Option One" in leaks[0]["detail"] and "Option Two" in leaks[0]["detail"]


def test_a_requirement_stated_for_every_path_is_not_flagged() -> None:
    _, _, v = evaluate(good())
    assert "path_requirement_leakage" not in {d["code"] for d in v["diagnostics"]}   # SQL/Python are stated in both paths' sections


def test_senior_is_source_supported_for_path_a_only() -> None:
    _, r, v = evaluate(good())
    assert r["seniority_levels_source_supported"]["status"] == gold.PASS            # "Lead / Senior" is the brief's own Path A wording
    assert "unsupported_level" not in {d["code"] for d in v["diagnostics"]}
    raw = good()
    raw["sourcing_paths"][1]["seniority"] = {"value": "Lead", "alternatives": ["Senior"], "strength": "required", "basis": b("recruiter_brief", "Path B requires Lead level and 6+ years.")}
    _, r, v = evaluate(raw)
    assert r["seniority_levels_source_supported"]["status"] == gold.FAIL
    assert any(d["code"] == "unsupported_level" and "Path B" in d["ref"] for d in v["diagnostics"])


def test_a_model_generated_level_is_never_promoted() -> None:
    raw = good()
    raw["sourcing_paths"][0]["seniority"]["alternatives"] = ["Senior", "Principal"]
    _, _, v = evaluate(raw)
    assert any(d["code"] == "unsupported_level" and "Principal" in d["detail"] and "nowhere" in d["detail"] for d in v["diagnostics"])
    raw = good()
    raw["sourcing_paths"][0]["seniority"].update(value="Senior", alternatives=[])
    _, r, _ = evaluate(raw)
    assert r["seniority_levels_source_supported"]["status"] == gold.FAIL     # drops the stated target, Lead


def test_security_firm_exclusion_must_stay_qualified_semantic_and_not_a_company_filter() -> None:
    _, r, _ = evaluate(good())
    assert r["security_firm_exclusion_semantic"]["status"] == gold.PASS and r["no_invented_company_exclusion"]["status"] == gold.PASS
    raw = good()
    raw["semantic_exclusions"][1]["concept"] = "Anyone employed by a security firm"
    _, r, _ = evaluate(raw)
    assert r["security_firm_exclusion_semantic"]["status"] == gold.PARTIAL        # generalised into a blanket exclusion
    raw = good()
    raw["semantic_exclusions"][1]["concept"] = "A strong SQL/Python analyst currently working at a security firm"
    _, r, _ = evaluate(raw)
    assert r["security_firm_exclusion_semantic"]["status"] == gold.PARTIAL        # an invented temporal qualifier
    raw = good()
    del raw["semantic_exclusions"][1]
    _, r, _ = evaluate(raw)
    assert r["security_firm_exclusion_semantic"]["status"] == gold.FAIL


def test_reconciliation_conflict_is_generic_and_scope_aware() -> None:
    raw = good()
    raw["skills"][2]["strength"] = "required"
    raw["sourcing_paths"][0]["skills"] = []                              # Power Query inherited as required by the waived path
    _, _, v = evaluate(raw)
    assert [d for d in v["diagnostics"] if d["code"] == "reconciliation_conflict" and "Power Query" in d["detail"] and "Path A" in d["detail"]]
    # the same required atom is fine for the path the waiver does not name: only Path A is flagged
    assert not [d for d in v["diagnostics"] if d["code"] == "reconciliation_conflict" and "Path B" in d["detail"] and "Power Query" in d["detail"]]
    # a waiver recorded for an item the intent no longer carries is not a conflict
    _, _, clean = evaluate(good())
    assert "reconciliation_conflict" not in {d["code"] for d in clean["diagnostics"]}
    # an unresolved conflict is surfaced, never flagged
    raw = good()
    raw["reconciliations"][0]["action"] = "unresolved"
    raw["evidence_signals"].append({"name": "security monitoring", "strength": "required", "basis": b("jd", SECMON)})
    _, _, v = evaluate(raw)
    assert "reconciliation_conflict" not in {d["code"] for d in v["diagnostics"]}


def test_no_assertion_depends_only_on_quote_text() -> None:
    """Strip every quote: the content assertions must not change. Only provenance/validation may react to quotes."""
    full = evaluate(good())[1]
    raw = good()

    def strip(o):
        if isinstance(o, dict):
            if "quote" in o:
                o["quote"] = None
            for k in ("jd_quote", "brief_quote"):
                if k in o:
                    o[k] = None
            for v in o.values():
                strip(v)
        elif isinstance(o, list):
            for v in o:
                strip(v)
    strip(raw)
    stripped = evaluate(raw)[1]
    quote_aware = {"provenance_preserved", "reconciliation_visible"}
    for id_, row in full.items():
        if id_ not in quote_aware:
            assert stripped[id_]["status"] == row["status"], id_


# ---------------------------------------------------------------------------- provenance is verified by code


def test_a_fabricated_quote_is_unsupported_not_trusted() -> None:
    raw = good()
    raw["skills"][0]["basis"] = b("jd", "Expert in Snowflake and dbt pipelines for finance reporting.")
    raw["skills"][0]["name"] = "Snowflake"
    _, r, v = evaluate(raw)
    atom = next(a for a in v["atoms"] if a["text"] == "Snowflake")
    assert atom["status"] == "unsupported" and atom["label"] == "unsupported"
    assert "claim_unsupported" in {d["code"] for d in v["diagnostics"]}
    assert r["provenance_preserved"]["status"] == gold.PARTIAL and r["provenance_preserved"]["failure_class"] == gold.VALIDATION


def test_a_real_quote_cited_to_the_wrong_source_is_misattributed() -> None:
    raw = good()
    raw["skills"][3]["basis"] = b("recruiter_brief", "Experience with Relativity and Canopy platforms is preferred.")  # only the JD says it
    _, _, v = evaluate(raw)
    assert next(a for a in v["atoms"] if a["ref"] == "skills[3]")["status"] == "misattributed"


def test_inferred_hard_constraint_and_unverifiable_approved_knowledge_are_flagged() -> None:
    raw = good()
    raw["skills"].append({"name": "Tableau", "strength": "required", "basis": {"sources": ["inferred"], "quote": None}})
    raw["skills"].append({"name": "Excel", "strength": "preferred", "basis": {"sources": ["approved_knowledge"], "quote": None}})
    _, _, v = evaluate(raw)
    codes = {d["code"] for d in v["diagnostics"]}
    assert {"inferred_hard_constraint", "approved_knowledge_unverified"} <= codes


def test_missing_basis_on_a_constraint_fails_provenance() -> None:
    raw = good()
    raw["skills"][0].pop("basis")
    _, r, v = evaluate(raw)
    assert "basis_missing" in {d["code"] for d in v["diagnostics"]}
    assert r["provenance_preserved"]["status"] == gold.FAIL


def test_labels_are_derived_from_what_code_verified() -> None:
    _, _, v = evaluate(good())
    labels = {a["ref"]: a["label"] for a in v["atoms"]}
    assert labels["skills[0]"] == "stated_in_both"      # SQL: the model cited the JD, code also finds the brief stating it
    assert labels["skills[3]"] == "retained_from_jd"    # Relativity: only the JD
    assert labels["paths[Path B].experience"] == "added_by_brief"   # 6+ years: only the brief
    assert labels["semantic_exclusions[0]"] == "added_by_brief"
    assert labels["paths[Path A].skills[0]"] == "waived_by_brief"


def test_a_real_but_unrelated_quote_is_flagged_informationally_and_never_changes_a_verdict() -> None:
    raw = good()
    raw["skills"][3]["basis"] = b("jd", "Maintain accurate documentation, procedures, audit trails, and quality records in accordance with organizational and client requirements.")
    _, r, v = evaluate(raw)
    atom = next(a for a in v["atoms"] if a["ref"] == "skills[3]")
    assert atom["status"] == "verified" and atom["quote_overlap"] == 0.0   # the quote exists; it just does not support Relativity
    assert "quote_weakly_related" in {d["code"] for d in v["diagnostics"]}
    assert r["provenance_preserved"]["status"] == gold.PASS               # informational: the known limit of a lexical check


def test_reconciliation_quotes_are_checked_against_the_right_source() -> None:
    raw = good()
    raw["reconciliations"][0]["brief_quote"] = "The recruiter said security monitoring is fine."
    _, r, v = evaluate(raw)
    assert "reconciliation_brief_quote_unverified" in {d["code"] for d in v["diagnostics"]}
    assert r["reconciliation_visible"]["status"] == gold.PARTIAL


def test_contradicted_item_that_still_stands_is_flagged() -> None:
    raw = good()
    raw["evidence_signals"].append({"name": "security monitoring", "strength": "required", "basis": b("jd", SECMON)})
    _, _, v = evaluate(raw)
    assert "reconciliation_conflict" in {d["code"] for d in v["diagnostics"]}


def test_quote_matching_is_forgiving_of_layout_not_of_content() -> None:
    assert quote_in("Path A  does NOT\nrequire Power Query.", BRIEF)
    assert quote_in("“Lead” may mean people leadership OR technical leadership", BRIEF)
    assert quote_in("Lead, mentor, and support ... quality, productivity, and compliance objectives", JD)
    assert not quote_in("quality, productivity ... Lead, mentor", JD)  # segments must appear in order
    assert not quote_in("Path A requires Power Query.", BRIEF)
    assert not quote_in(None, BRIEF) and not quote_in("   ", BRIEF)


# ---------------------------------------------------------------------------- schema: additive, isolated, safe


def test_override_semantics_global_plus_path() -> None:
    intent = ExperimentalHiringIntent.model_validate(good())
    a, bb = effective_view(intent, "Path A"), effective_view(intent, "Path B")
    assert {s.name: s.strength for s in a["skills"]}["Power Query"] == "preferred"
    assert {s.name: s.strength for s in bb["skills"]}["Power Query"] == "required"
    assert a["location"].countries == ["India"] and a["location"].remote == "allowed" and bb["location"].countries == []
    assert bb["experience"].minimum_years == 6 and a["experience"] is None          # path-scoped: Path A does not inherit it
    assert a["seniority"].alternatives == ["Senior"] and bb["seniority"].alternatives == []  # Path B inherits the global Lead only
    with pytest.raises(KeyError):
        effective_view(intent, "nope")


def test_existing_baseline_style_intent_still_validates_with_new_fields_empty() -> None:
    legacy = {"role_archetype": {"value": "hybrid", "confidence": 0.7, "rationale": "x"}, "role_family": ["Data Analyst"],
              "skills": [{"name": "SQL", "relationship": "current", "strength": "required"}]}
    assert StructuredHiringIntent.model_validate(legacy)
    x = ExperimentalHiringIntent.model_validate(legacy)
    assert x.sourcing_paths == [] and x.semantic_exclusions == [] and x.reconciliations == [] and x.domain == []
    assert isinstance(x, StructuredHiringIntent)


def test_production_schema_is_untouched() -> None:
    assert not ({"sourcing_paths", "domain", "semantic_exclusions", "reconciliations"} & set(StructuredHiringIntent.model_fields))
    assert not any(v for v in baseline_gold.schema_supports().values())
    assert all(schema_concepts().values())


def test_no_production_module_imports_the_experiment() -> None:
    for path in (REPO / "backend").rglob("*.py"):
        if "experiments" in path.parts:
            continue
        assert "experiments.intake_strategy" not in path.read_text(encoding="utf-8"), path


def test_enums_and_the_provider_leak_guard_cover_the_new_fields() -> None:
    raw = good()
    for mutate in (
        lambda r: r["skills"][0].update(proficiency="expert"),
        lambda r: r["sourcing_paths"][0].update(strategy="whatever"),
        lambda r: r["seniority"].update(leadership=["executive"]),
        lambda r: r["reconciliations"][0].update(action="merged"),
        lambda r: r["skills"][0]["basis"].update(sources=["wikipedia"]),
        lambda r: r["domain"][0].update(name="current.title contains analyst"),
        lambda r: r["semantic_exclusions"][0].update(concept="company_name not_in security"),
    ):
        bad = copy.deepcopy(raw)
        mutate(bad)
        with pytest.raises(ValidationError):
            ExperimentalHiringIntent.model_validate(bad)


# ---------------------------------------------------------------------------- the prompt is generic


_ROLE_TERMS = ("power query", "sql", "python", "soc", "cyber", "hyderabad", "pune", "india", "legal", "lpo", "security", "data analyst",
               "relativity", "canopy", "breach", "path a", "path b", "incident", "siem", "lead data")


@pytest.mark.parametrize("version", ["v2", "v3"])
def test_prompt_keeps_production_rules_verbatim_and_adds_no_role_specific_text(version: str) -> None:
    from backend.experiments.intake_strategy.experimental_extractor import PROMPTS
    prod = (REPO / "prompts" / "structured_intent.txt").read_text(encoding="utf-8")
    text = PROMPTS[version].read_text(encoding="utf-8")
    rules = prod[prod.index("RULES — these are hiring-intent semantics"):prod.index("There are two sources of hiring intent")]
    assert rules in text
    added = text[text.index("11. SOURCE ROLES AND PRIORITY"):text.index("Job description / notes:")]
    terms = _ROLE_TERMS + (("senior", "firm", "6+", "marine claims 6") if version == "v3" else ())
    for term in terms:
        assert not re.search(rf"\b{re.escape(term)}\b", added, re.I), term
    assert "{job_description}" in text and "{recruiter_brief}" in text


def test_v3_prompt_states_the_hardening_rules_generically() -> None:
    text = (PROMPT_V2.parent / "prompt_v3.txt").read_text(encoding="utf-8")
    for needle in ("belongs to THAT path only", "SHORT designation", "never the whole heading", "location.countries", "location.remote", "seniority.alternatives",
                   "Keep the source's own qualifiers", "check every required atom against your reconciliations"):
        assert needle in text, needle


def test_prompt_never_receives_gold_assertions() -> None:
    text = build_prompt(JD, BRIEF, "v3")
    assert JD[:60] in text and BRIEF[:40] in text
    for gold_text in ("two_paths_preserved", "pq_not_mandatory_path_a", "PASS", "PARTIAL", "gold"):
        assert gold_text not in text


# ---------------------------------------------------------------------------- harness (fake client)


class _Fake:
    def __init__(self, payloads) -> None:
        self._payloads = list(payloads)
        self.responses = self
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        assert kwargs.get("stream") is True  # the experimental arm streams (see run_experimental)
        item = self._payloads.pop(0)
        if isinstance(item, Exception):
            raise item
        final = SimpleNamespace(output_text=item, usage=SimpleNamespace(input_tokens=5, output_tokens=3))
        return iter([SimpleNamespace(type="response.output_text.delta"), SimpleNamespace(type="response.completed", response=final)])


class InternalServerError(Exception):
    status_code = 500


def test_harness_records_intent_gold_and_validation_and_keeps_model_config() -> None:
    fake = _Fake([json.dumps(good())])
    record = exp.run_once(1, lambda: fake, JD, BRIEF)
    assert record["error"] is None
    assert [d for d in record["gold"]["validation"]["diagnostics"] if d["code"] != "quote_weakly_related"] == []
    assert record["model_calls"][0]["model"] == "gpt-6.1-sol" and record["model_calls"][0]["reasoning"] == {"effort": "medium"}
    assert "compiled" not in record  # the compiler is not part of this arm


def test_a_stream_that_never_completes_is_an_error_not_an_empty_intent() -> None:
    class Cut(_Fake):
        def create(self, **kwargs):
            return iter([SimpleNamespace(type="response.output_text.delta")])

    record = exp.run_once(1, lambda: Cut([]), JD, BRIEF)
    assert "without response.completed" in record["error"] and "intent" not in record


def test_only_transient_errors_are_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exp.time, "sleep", lambda s: None)
    fake = _Fake([InternalServerError("upstream"), json.dumps(good())])
    record = exp.run_once(1, lambda: fake, JD, BRIEF)
    assert record["error"] is None and len(record["transient_retries"]) == 1 and fake.calls == 2
    bad = _Fake(["not json"])
    record = exp.run_once(1, lambda: bad, JD, BRIEF)
    assert record["error"] and bad.calls == 1 and "intent" not in record  # a parse failure is a result, not retried


def test_stability_compares_meaning_not_json(monkeypatch: pytest.MonkeyPatch) -> None:
    other = good()
    other["sourcing_paths"][1]["location"]["entries"] = ["Pune, Maharashtra, India", "Hyderabad, Telangana, India"]  # reordered
    drift = good()
    drift["skills"][2]["strength"] = "preferred"
    drift["sourcing_paths"][0]["skills"][0]["strength"] = "preferred"
    records = [exp.run_once(i, lambda p=p: _Fake([json.dumps(p)]), JD, BRIEF) for i, p in enumerate((good(), other, drift), 1)]
    s = exp.stability(records)
    assert s["components"]["geography_B"]["agreement"] == "3/3"          # reordering is not drift
    assert s["components"]["power_query_B"]["agreement"] == "2/3"        # a strength change is
    assert s["assertion_statuses"]["pq_working_knowledge_path_b"] == {"PASS": 2, "FAIL": 1}


def test_experimental_harness_refuses_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert exp.main(["--runs", "1"]) == 2
