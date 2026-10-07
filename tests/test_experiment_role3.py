"""Role 3 (JD-only) cross-role validation: evaluator, freeze guards, harness. Offline and model-free.

The exemplar is hand-written from the Role 3 JD to test the EVALUATOR: a small correct intent passes everything, and each specific
over-application or fidelity error fails the specific assertion with the right class. It says nothing about what the model produces.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError  # noqa: F401  (kept for parity with the other experiment tests)

from backend.experiments.intake_strategy import gold_role3 as gold
from backend.experiments.intake_strategy import run_role3 as r3
from backend.experiments.intake_strategy.experimental_extractor import DEFAULT_PROMPT, PROMPTS, build_prompt
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.experiments.intake_strategy.gold_assertions import EXTRACTION, FAIL, PARTIAL, PASS, VALIDATION

PKG = Path(r3.__file__).parent
JD = r3.load_inputs()["jd"]


def b(quote: str, source: str = "jd") -> dict:
    return {"sources": [source], "quote": quote}


J_TITLE = "Senior Manager – FP&A and Business Finance"
J_LOC = "Location: Hyderabad, India"
J_EXP = "8–12 years of relevant experience in FP&A, Business Finance, Commercial Finance, or closely related financial planning roles."
J_EDU = "Bachelor’s degree in Finance, Accounting, Economics, Business, or a related discipline."
J_PLAN = "Strong experience in financial planning, budgeting, forecasting, and variance analysis."
J_MODEL = "Strong financial modeling skills, including scenario and sensitivity analysis."
J_EXCEL = "Advanced proficiency in Microsoft Excel."
J_PBI = "Working knowledge of Power BI or a similar business intelligence/reporting platform."
J_PRES = "Experience presenting financial analysis and recommendations to senior stakeholders."
J_PARTNER = "Strong business partnering and communication skills."
J_ERP = "Experience working with ERP systems such as SAP, Oracle, or comparable platforms."
J_PROFQ = "Professional qualification such as CA, CMA, ACCA, or MBA Finance is preferred."
J_ENV = "Experience in large multinational or complex enterprise environments is preferred."
J_COMP = "Candidates with experience in organizations such as Unilever, Procter & Gamble, PepsiCo, Nestlé, Coca-Cola, Mondelez International, or similar large consumer/industrial organizations would be particularly relevant."
J_LEADSUP = "Experience supporting commercial, operations, or business-unit leadership is preferred."
J_OWN = "This role requires meaningful FP&A/business-finance ownership."
J_EXCL = "Candidates whose experience is exclusively in statutory audit, tax, bookkeeping, or transaction processing, without substantive FP&A or business-finance responsibilities, are not suitable."
R_PACKS = "Prepare monthly and quarterly management reporting packs with clear commentary on business performance."
R_AUTO = "Improve financial planning and reporting processes through automation, standardization, and data-driven analysis."
R_CROSS = "Work cross-functionally with Accounting, Commercial, Operations, and other business teams."
R_ADHOC = "Support ad hoc financial analysis and strategic projects as required."
R_MODEL = "Develop and maintain financial models to support planning, scenario analysis, investment decisions, and business performance reviews."


def sk(name: str, quote: str, **kw) -> dict:
    return {"name": name, "strength": "required", "relationship": "any", "basis": b(quote), **kw}


def good3() -> dict:
    return {
        "role_archetype": {"value": "title_defined", "confidence": 0.9, "rationale": "a finance title"},
        "role_family": ["FP&A and Business Finance Manager"],
        "seniority": {"value": "Senior Manager", "strength": "required", "basis": b(J_TITLE)},
        "experience": {"minimum_years": 8, "maximum_years": 12, "strength": "required", "basis": b(J_EXP)},
        "education": {"degrees": ["Bachelor's degree"], "streams": ["Finance", "Accounting", "Economics", "Business", "Related discipline"], "strength": "required", "basis": b(J_EDU)},
        "location": {"entries": ["Hyderabad, Telangana, India"], "strength": "required", "work_mode": "hybrid", "basis": b(J_LOC)},
        "skills": [
            sk("Financial planning", J_PLAN), sk("Budgeting", J_PLAN), sk("Forecasting", J_PLAN), sk("Variance analysis", J_PLAN),
            sk("Financial modeling, including scenario and sensitivity analysis", J_MODEL),
            sk("Microsoft Excel", J_EXCEL, proficiency="advanced"),
            sk("Power BI or a similar BI/reporting platform", J_PBI, proficiency="working_knowledge"),
            sk("Presenting financial analysis and recommendations to senior stakeholders", J_PRES),
            sk("Business partnering", J_PARTNER), sk("Communication", J_PARTNER),
            sk("ERP systems (such as SAP, Oracle)", J_ERP),
        ],
        "skill_any_of": [{"any_of": ["CA", "CMA", "ACCA", "MBA Finance"], "strength": "preferred", "relationship": "any", "basis": b(J_PROFQ)}],
        "companies": [{"name": n, "strength": "preferred", "relationship": "any", "basis": b(J_COMP)}
                      for n in ("Unilever", "Procter & Gamble", "PepsiCo", "Nestlé", "Coca-Cola", "Mondelez International")],
        "evidence_signals": [
            {"name": "Meaningful FP&A / business-finance ownership", "strength": "required", "basis": b(J_OWN)},
            {"name": "Experience in large multinational or complex enterprise environments", "strength": "preferred", "basis": b(J_ENV)},
            {"name": "Experience supporting commercial, operations, or business-unit leadership", "strength": "preferred", "basis": b(J_LEADSUP)},
            {"name": "Prepares monthly and quarterly management reporting packs", "strength": "context", "basis": b(R_PACKS)},
            {"name": "Improves planning and reporting through automation and standardization", "strength": "context", "basis": b(R_AUTO)},
            {"name": "Works cross-functionally with Accounting, Commercial and Operations", "strength": "context", "basis": b(R_CROSS)},
            {"name": "Supports ad hoc analysis and strategic projects", "strength": "context", "basis": b(R_ADHOC)},
        ],
        "semantic_exclusions": [{"concept": "Experience exclusively in statutory audit, tax, bookkeeping, or transaction processing, without substantive FP&A or business-finance responsibilities",
                                 "includes": ["statutory audit", "tax", "bookkeeping", "transaction processing"], "basis": b(J_EXCL)}],
    }


def run(raw: dict):
    intent = ExperimentalHiringIntent.model_validate(raw)
    result = gold.evaluate(intent, JD)
    return intent, {r["id"]: r for r in result["critical"]}, result["validation"]


# ---------------------------------------------------------------------------- freeze guards and JD-only discipline


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_the_representation_validators_and_prompt_are_frozen_for_role_3() -> None:
    """If this fails, something frozen for the Role 3 phase changed. That needs an explicit owner decision."""
    pinned = {
        "experimental_schema.py": "afadf57e96939a78156cb2dec28de83f9fbc7cb9954bdf9e70073c6924823158",
        "validators_cross_role.py": "ca26fe1869c4abb3150838152e9ee79fc94ebebb088f4b7b00e3ca978fa834d2",
        "validators.py": "b9895980c85013e3f73d80224344b0a635b46a0b3a69b67b17d6402e9b351ce5",
        "prompt_v4.txt": "27f79f50c94fb0b7584b84ebbf01b3e92f096d2230c3af9b78950dbbabc71c5d",
        "experimental_extractor.py": "d09570f6c174f8d0dfa85dcc3d990529554183c4eb4f9dde04f03ba7876e6890",
        "gold_role2.py": "d53e5d169200b128102e7c2bc153e63f37960cc0a5388431f1bdb3bdff5c1c82",
        "inputs/role3_jd.txt": "5df089944dd908d40efd51f1797d963ee714cf7cf9a4fe1a8ae417343467b8eb",
        "ROLE3_GROUND_TRUTH.md": "ba3ede982ca6552cb4f527ca29e5db8181caf30c5045f66c2f6d34ea79208306",
    }
    for rel, digest in pinned.items():
        assert _sha(PKG / rel) == digest, rel
    assert r3.PROMPT == "v4" and r3.prompt_sha256() == _sha(PKG / "prompt_v4.txt") and DEFAULT_PROMPT == "v3"


def test_role_3_is_jd_only_there_is_no_recruiter_brief() -> None:
    assert not (PKG / "inputs" / "role3_recruiter_brief.txt").exists() and list((PKG / "inputs").glob("role3*")) == [PKG / "inputs" / "role3_jd.txt"]
    assert r3.load_inputs() == {"jd": JD} and r3.NO_BRIEF == ""
    assert JD.startswith("Senior Manager – FP&A and Business Finance") and "Work Mode: Hybrid" in JD and "8–12 years" in JD and "Bachelor’s" in JD
    assert "current" not in JD.lower()                                      # no temporal wording at all, so no `current` can be source-supported
    text = build_prompt(JD, r3.NO_BRIEF, "v4")
    assert "(none provided)" in text and JD[:60] in text


def test_the_ground_truth_has_no_recruiter_source_and_classes_every_assertion() -> None:
    gt = (PKG / "ROLE3_GROUND_TRUTH.md").read_text(encoding="utf-8")
    flat = " ".join(gt.split())
    rows = [l for l in gt.splitlines() if l.startswith("| ") and any(f"| {c}" in l for c in ("JD", "APPROVED_KNOWLEDGE", "INFERRED"))]
    assert len(rows) >= 30
    assert not any("| RECRUITER_BRIEF" in l for l in gt.splitlines())
    for needle in ("JD-only", "no recruiter/HM brief", "`sourcing_paths` must be empty", "Smaller and correct beats richer and invented"):
        assert needle in flat, needle


def test_the_prompt_never_receives_ground_truth() -> None:
    text = build_prompt(JD, r3.NO_BRIEF, "v4")
    for needle in ("ROLE3_GROUND_TRUTH", "no_sourcing_path", "excel_advanced", "semantic_exclusion_faithful"):
        assert needle not in text


def test_the_evaluator_and_runner_import_no_provider_or_compiler() -> None:
    forbidden = ("providers.crustdata", "providers.harvest", "search_pipeline", "requirement_judge", "search_translator", "backend.api", "search_compiler")
    for name in ("gold_role3.py", "run_role3.py"):
        for line in (PKG / name).read_text(encoding="utf-8").splitlines():
            if line.startswith(("import ", "from ")):
                assert not any(f in line for f in forbidden), (name, line)


# ---------------------------------------------------------------------------- the evaluator is calibrated


def test_a_small_correct_intent_passes_every_assertion() -> None:
    intent, r, v = run(good3())
    assert {k: x["status"] for k, x in r.items() if x["status"] != PASS} == {}
    assert v["errors"] == {}
    assert not intent.sourcing_paths and not intent.reconciliations and not intent.exclusions and not intent.domain
    assert not intent.seniority.leadership and not intent.seniority.alternatives and not intent.location.countries and intent.location.remote is None


def _mut_skill(raw: dict, prefix: str, **kw) -> None:
    next(s for s in raw["skills"] if s["name"].startswith(prefix)).update(kw)


@pytest.mark.parametrize("mutate,assertion,status,cls", [
    (lambda r: r.update(sourcing_paths=[{"id": "Option 1", "label": "a", "strategy": "hybrid"}]), "no_sourcing_path_or_reconciliation", FAIL, EXTRACTION),
    (lambda r: r.update(reconciliations=[{"topic": "x", "action": "narrowed", "result": "y"}]), "no_sourcing_path_or_reconciliation", FAIL, EXTRACTION),
    (lambda r: r.update(exclusions=[{"kind": "exclude_current_company", "value": "KPMG"}]), "no_invented_exclusion", FAIL, EXTRACTION),
    (lambda r: r["semantic_exclusions"].append({"concept": "Fully remote candidates"}), "no_invented_exclusion", FAIL, EXTRACTION),
    (lambda r: r["semantic_exclusions"][0].update(concept="Experience in audit, tax, bookkeeping or transaction processing", includes=[]), "semantic_exclusion_faithful", PARTIAL, EXTRACTION),
    (lambda r: r.update(semantic_exclusions=[]), "semantic_exclusion_faithful", FAIL, EXTRACTION),
    (lambda r: r["location"].update(countries=["India"]), "geography_hyderabad_single", FAIL, EXTRACTION),
    (lambda r: r["location"].update(entries=["Hyderabad, Telangana, India", "Pune, Maharashtra, India"]), "geography_hyderabad_single", FAIL, EXTRACTION),
    (lambda r: r["location"].update(radius={"value": 25, "unit": "miles", "around": "Hyderabad, Telangana, India"}), "geography_hyderabad_single", FAIL, EXTRACTION),
    (lambda r: r["location"].update(remote="allowed"), "work_mode_hybrid_typed", FAIL, EXTRACTION),
    (lambda r: r["location"].update(work_mode="onsite"), "work_mode_hybrid_typed", FAIL, EXTRACTION),
    (lambda r: r["location"].update(work_mode="remote"), "work_mode_hybrid_typed", FAIL, EXTRACTION),
    (lambda r: r["location"].update(work_mode=None), "work_mode_hybrid_typed", FAIL, EXTRACTION),
    (lambda r: r["location"].update(remote="not_allowed"), "work_mode_hybrid_typed", PARTIAL, EXTRACTION),
    (lambda r: _mut_skill(r, "Microsoft Excel", proficiency="hands_on"), "excel_advanced", PARTIAL, EXTRACTION),
    (lambda r: _mut_skill(r, "Microsoft Excel", proficiency=None), "excel_advanced", PARTIAL, EXTRACTION),
    (lambda r: _mut_skill(r, "Microsoft Excel", proficiency="working_knowledge"), "excel_advanced", FAIL, EXTRACTION),
    (lambda r: _mut_skill(r, "Power BI", proficiency="hands_on"), "power_bi_working_knowledge", FAIL, EXTRACTION),
    (lambda r: _mut_skill(r, "Power BI", name="Power BI"), "power_bi_working_knowledge", PARTIAL, EXTRACTION),
    (lambda r: _mut_skill(r, "Financial modeling", proficiency="advanced"), "no_invented_proficiency", FAIL, EXTRACTION),
    (lambda r: _mut_skill(r, "Budgeting", proficiency="hands_on"), "no_invented_proficiency", FAIL, EXTRACTION),
    (lambda r: r["companies"][0].update(strength="required"), "company_preference_kept_as_preference", FAIL, EXTRACTION),
    (lambda r: r["companies"][0].update(relationship="current"), "company_preference_kept_as_preference", FAIL, EXTRACTION),
    (lambda r: r["companies"][0].update(relationship="past"), "company_preference_kept_as_preference", PARTIAL, EXTRACTION),
    (lambda r: r.update(company_scale={"minimum_employees": 10000, "strength": "required"}), "company_preference_kept_as_preference", FAIL, EXTRACTION),
    (lambda r: r.update(companies=r["companies"][:3]), "company_preference_kept_as_preference", PARTIAL, EXTRACTION),
    (lambda r: r["skill_any_of"][0].update(strength="required"), "professional_qualification_preferred", FAIL, EXTRACTION),
    (lambda r: r.update(skill_any_of=[]), "professional_qualification_preferred", PARTIAL, EXTRACTION),
    (lambda r: r["education"].update(degrees=["Bachelor's degree", "CA", "MBA Finance"]), "education_bachelor_required", FAIL, EXTRACTION),
    (lambda r: r["education"].update(strength="preferred"), "education_bachelor_required", FAIL, EXTRACTION),
    (lambda r: r["evidence_signals"][1].update(strength="required"), "background_preferences_preferred", FAIL, EXTRACTION),
    (lambda r: r["seniority"].update(value="Director"), "seniority_senior_manager", FAIL, EXTRACTION),
    (lambda r: r["seniority"].update(leadership=["people"]), "seniority_senior_manager", FAIL, EXTRACTION),
    (lambda r: r["seniority"].update(alternatives=["Manager"]), "seniority_senior_manager", FAIL, EXTRACTION),
    (lambda r: r.update(seniority=None), "seniority_senior_manager", PARTIAL, EXTRACTION),
    (lambda r: r.update(role_family=["FP&A and Business Finance Manager", "Financial Analyst"]), "role_family_discipline", FAIL, EXTRACTION),
    (lambda r: r.update(role_family=["Finance Business Partner"]), "role_family_discipline", FAIL, EXTRACTION),
    (lambda r: r.update(role_family=["Head of FP&A"]), "role_family_discipline", FAIL, EXTRACTION),
    (lambda r: r["experience"].update(maximum_years=None), "experience_8_to_12", PARTIAL, EXTRACTION),
    (lambda r: r["experience"].update(minimum_years=10), "experience_8_to_12", FAIL, EXTRACTION),
    (lambda r: r["skills"].extend([sk("SAP", J_ERP), sk("Oracle", J_ERP)]), "erp_examples_not_and", FAIL, EXTRACTION),
], ids=lambda x: x if isinstance(x, str) else "")
def test_each_over_application_or_fidelity_error_fails_its_assertion(mutate, assertion, status, cls) -> None:
    raw = good3()
    mutate(raw)
    _, r, _ = run(raw)
    assert r[assertion]["status"] == status, r[assertion]
    assert r[assertion]["failure_class"] == cls


def test_power_bi_as_an_or_group_loses_its_depth_and_the_lossless_form_is_one_atom() -> None:
    raw = good3()
    raw["skills"] = [s for s in raw["skills"] if not s["name"].startswith("Power BI")]
    raw["skill_any_of"].append({"any_of": ["Power BI", "Tableau"], "strength": "required", "relationship": "any", "basis": b(J_PBI)})
    _, r, _ = run(raw)
    assert r["power_bi_working_knowledge"]["status"] == PARTIAL and "OR group carries no proficiency" in r["power_bi_working_knowledge"]["evidence"]
    _, ok, _ = run(good3())
    assert ok["power_bi_working_knowledge"]["status"] == PASS


def test_relationship_current_or_past_is_unsupported_everywhere_and_the_frozen_validator_agrees() -> None:
    raw = good3()
    _mut_skill(raw, "Financial modeling", relationship="current")
    _, r, v = run(raw)
    assert r["no_unsupported_temporal_relationship"]["status"] == FAIL
    assert v["errors"].get("unsupported_current_relationship") == 1 and r["generic_validators_clean"]["failure_class"] == VALIDATION
    raw = good3()
    _mut_skill(raw, "Budgeting", relationship="past")
    _, r, _ = run(raw)
    assert r["no_unsupported_temporal_relationship"]["status"] == FAIL


def test_a_responsibility_only_requirement_is_caught_twice_and_a_stated_qualification_is_not() -> None:
    for line, name in ((R_PACKS, "Management reporting packs"), (R_AUTO, "Process automation and standardization"), (R_CROSS, "Cross-functional work"), (R_ADHOC, "Ad hoc analysis")):
        raw = good3()
        raw["evidence_signals"].append({"name": name, "strength": "required", "basis": b(line)})
        _, r, v = run(raw)
        assert r["no_responsibility_hardening"]["status"] == FAIL, name
        assert v["errors"].get("responsibility_only_required") == 1 and r["generic_validators_clean"]["status"] == FAIL
    raw = good3()
    raw["skills"].append(sk("Financial modeling", R_MODEL))          # cites the responsibility line, but the JD also states it as a qualification
    _, r, v = run(raw)
    assert r["no_responsibility_hardening"]["status"] == PASS and "responsibility_only_required" not in v["errors"]


def test_a_preference_hardened_to_required_is_reported_in_aggregate() -> None:
    raw = good3()
    raw["companies"][2]["strength"] = "required"
    raw["skill_any_of"][0]["strength"] = "required"
    _, r, _ = run(raw)
    assert r["no_preference_hardened"]["status"] == FAIL


def test_a_source_claim_of_a_brief_that_does_not_exist_is_a_provenance_failure() -> None:
    raw = good3()
    raw["location"]["basis"] = {"sources": ["recruiter_brief"], "quote": J_LOC}
    _, r, _ = run(raw)
    assert (r["no_fabricated_brief_source"]["status"], r["no_fabricated_brief_source"]["failure_class"]) == (FAIL, "PROVENANCE")


def test_provenance_catches_a_fabricated_quote_and_an_inferred_requirement() -> None:
    raw = good3()
    raw["skills"][0]["basis"] = b("Must have audited a Fortune 500 consolidation.")
    _, r, _ = run(raw)
    assert r["provenance_preserved"]["status"] != PASS and r["provenance_preserved"]["failure_class"] == "PROVENANCE"
    raw = good3()
    raw["skills"].append({"name": "Treasury", "strength": "required", "relationship": "any", "basis": {"sources": ["inferred"], "quote": None}})
    _, r, v = run(raw)
    assert "inferred_hard_constraint" in {d["code"] for d in v["diagnostics"]} and r["provenance_preserved"]["status"] == PARTIAL


def test_seniority_may_keep_manager_in_the_role_family() -> None:
    raw = good3()
    raw["seniority"].update(value="Senior")
    raw["role_family"] = ["Manager – FP&A and Business Finance"]
    _, r, _ = run(raw)
    assert r["seniority_senior_manager"]["status"] == PASS
    raw["role_family"] = ["FP&A and Business Finance"]
    _, r, _ = run(raw)
    assert r["seniority_senior_manager"]["status"] == PARTIAL           # 'Manager' lost


def test_work_mode_hybrid_in_text_only_is_partial_because_the_typed_field_exists() -> None:
    raw = good3()
    raw["location"]["work_mode"] = None
    raw["evidence_signals"].append({"name": "Hybrid working", "strength": "required", "basis": b("Work Mode: Hybrid")})
    _, r, _ = run(raw)
    assert r["work_mode_hybrid_typed"]["status"] == PARTIAL


def test_a_domain_is_optional_and_a_required_domain_restating_a_stated_requirement_is_not_over_application() -> None:
    """Post-run correction: the committed ground truth never forbade a required domain; the first evaluator rule exceeded it."""
    raw = good3()
    raw["domain"] = [{"name": "Large multinational or complex enterprise environments", "strength": "preferred", "basis": b(J_ENV)},
                     {"name": "FP&A, Business Finance, Commercial Finance, or closely related financial planning roles", "strength": "required", "basis": b(J_EXP)}]
    intent, r, _ = run(raw)
    assert r["no_role_shape_structure"]["status"] == PASS
    required = gold.observations(intent)["required_domain"]
    assert len(required) == 1 and required[0][1] == "required" and required[0][0].startswith("FP&A, Business Finance, Commercial Finance")
    assert gold.evaluate(intent, JD)["observations"]["domain"]                       # reported, never graded
    raw["seniority"]["leadership"] = ["technical"]                                   # a genuinely invented structure is still caught
    _, r, _ = run(raw)
    assert r["no_role_shape_structure"]["status"] == FAIL and r["seniority_senior_manager"]["status"] == FAIL


# ---------------------------------------------------------------------------- harness (fake client, no model)


class _Fake:
    def __init__(self, payload: str) -> None:
        self._payload = payload
        self.responses = self
        self.prompts: list = []

    def create(self, **kwargs):
        assert kwargs.get("stream") is True
        self.prompts.append(kwargs["input"][0]["content"])
        final = SimpleNamespace(output_text=self._payload, usage=SimpleNamespace(input_tokens=5, output_tokens=3))
        return iter([SimpleNamespace(type="response.completed", response=final)])


def test_the_runner_uses_prompt_v4_with_no_brief_and_records_intent_gold_and_validation() -> None:
    fake = _Fake(json.dumps(good3()))
    record = r3.run_once(1, lambda: fake, JD)
    assert record["error"] is None and record["gold"]["validation"]["errors"] == {} and "compiled" not in record
    assert "(none provided)" in fake.prompts[0] and "23. TEMPORAL RELATIONSHIP" in fake.prompts[0] and JD[:50] in fake.prompts[0]
    assert record["model_calls"][0]["model"] == "gpt-6.1-sol" and record["model_calls"][0]["reasoning"] == {"effort": "medium"} and record["model_calls"][0]["streamed"]


def test_stability_summarises_meaning_and_a_parse_failure_is_a_result() -> None:
    other = good3()
    _mut_skill(other, "Financial planning", relationship="current")
    records = [r3.run_once(i, lambda p=p: _Fake(json.dumps(p)), JD) for i, p in enumerate((good3(), good3(), other), 1)]
    bad = r3.run_once(4, lambda: _Fake("not json"), JD)
    assert bad["error"] and "intent" not in bad
    s = r3.stability(records + [bad])
    assert s["runs"] == 4 and s["parsed"] == 3 and s["components"]["paths"]["agreement"] == "3/3" and s["components"]["relationships"]["agreement"] == "2/3"
    assert s["assertion_statuses"]["no_unsupported_temporal_relationship"] == {"PASS": 2, "FAIL": 1}


def test_the_role3_runner_refuses_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert r3.main(["--runs", "1"]) == 2
