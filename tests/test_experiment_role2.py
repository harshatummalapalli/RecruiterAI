"""Role 2 cross-role validation: evaluator, freeze guards and harness. Offline and model-free.

The exemplar below is hand-written from the Role 2 sources to test the EVALUATOR: a correct, small intent passes everything the
schema can express, and each specific over-application or fidelity error fails the specific assertion with the right class. It
says nothing about what the model produces.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.experiments.intake_strategy import gold_assertions as base
from backend.experiments.intake_strategy import gold_role2 as gold
from backend.experiments.intake_strategy import run_role2 as r2
from backend.experiments.intake_strategy.experimental_extractor import PROMPTS, build_prompt
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent

PKG = Path(r2.__file__).parent
INPUTS = r2.load_inputs()
JD, BRIEF = INPUTS["jd"], INPUTS["brief"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def b(source: str, quote: str | None) -> dict:
    return {"sources": [source], "quote": quote}


L_TITLE = "Staff Software Engineer/ Solution Architect - AI Solutions"
L_EXP = "12+ years of experience in Full Stack Software Development, Solution Design, Data Engineering, and AI/ML implementation."
L_EDU = "Bachelor's or Master's degree in Computer Science, Information Technology, Software Engineering, or a related field."
L_PYJ = "Advanced proficiency in Python and Java with strong experience building APIs, services, and distributed systems."
L_GENAI = "Hands-on experience implementing and deploying Generative AI solutions in production environments."
L_LLM = "Strong understanding of LLMs, RAG architectures, Agentic AI, Prompt Engineering, MCP, A2A, and modern AI application development patterns."
L_ML = "Experience working with NLP frameworks and machine learning libraries such as TensorFlow, PyTorch, scikit-learn, or similar technologies."
L_CLOUD = "Experience with cloud platforms and services including Azure and/or AWS."
L_DEVOPS = "Experience with DevOps tools and practices including CI/CD pipelines, Terraform, AKS, EKS, GitHub Actions, and containerized deployments."
L_UI = "Experience building modern user interfaces using React, Bootstrap, and related frameworks."
L_AZDO = "Familiarity with Azure DevOps, Jira, and modern software delivery practices."
L_DATA = "Experience working with Snowflake, Databricks, and modern data platforms."
L_DATA2 = "Strong understanding of Data Integration, ETL, Data Quality, Data Discovery, and enterprise data management concepts."
L_API = "Experience integrating third-party and enterprise APIs."
L_META = "Familiarity with metadata management tools and data governance concepts."
L_SOFT = "Strong analytical, problem-solving, and troubleshooting skills."
L_COMM = "Excellent communication and stakeholder management skills with the ability to effectively engage clients, business stakeholders, leadership teams, and engineering organizations."
L_HANDS = "Strong hands-on software engineering background with proven experience designing and developing enterprise-scale applications."
L_DESIGN = "Demonstrated experience designing technical solutions and participating in architecture reviews, system design discussions, and technical decision-making."
L_LEAD = "Provide technical leadership, mentor team members, resolve complex technical challenges, and foster a collaborative engineering culture."
B_IC = "Look for an IC Engineer who understands how to design a solution for a client problem"
B_FDE = "more like a Forward Deployed Engineer who understands the client requirements, builds POC's, designs the system."
B_EXIST = "he would be working closely with the existing teams on enhancing the existing products and features."
B_LOC = "Location is Hyderabad and need someone who can work on a Hybrid basis."


def _skill(name: str, quote: str, source: str = "jd", **kw) -> dict:
    return {"name": name, "strength": "required", "basis": b(source, quote), **kw}


def good2() -> dict:
    return {
        "role_archetype": {"value": "hybrid", "confidence": 0.8, "rationale": "title plus a stack"},
        "role_family": ["Software Engineer", "Solution Architect"],
        "seniority": {"value": "Staff", "strength": "required", "basis": b("jd", L_TITLE)},
        "experience": {"minimum_years": 12, "strength": "required", "basis": b("jd", L_EXP)},
        "education": {"degrees": ["Bachelor's degree", "Master's degree"], "streams": ["Computer Science", "Information Technology", "Software Engineering", "Related field"],
                      "strength": "required", "basis": b("jd", L_EDU)},
        "location": {"entries": ["Hyderabad, Telangana, India"], "strength": "required", "remote": "not_allowed", "basis": b("recruiter_brief", B_LOC)},
        "skills": [
            _skill("Python", L_PYJ, proficiency="hands_on"), _skill("Java", L_PYJ, proficiency="hands_on"),
            _skill("Generative AI in production", L_GENAI, proficiency="hands_on"),
            _skill("LLMs", L_LLM), _skill("RAG", L_LLM), _skill("Agentic AI", L_LLM), _skill("Prompt Engineering", L_LLM), _skill("MCP", L_LLM), _skill("A2A", L_LLM),
            _skill("CI/CD pipelines", L_DEVOPS), _skill("Terraform", L_DEVOPS), _skill("GitHub Actions", L_DEVOPS), _skill("Containerized deployments", L_DEVOPS),
            _skill("React", L_UI), _skill("Bootstrap", L_UI), _skill("Snowflake", L_DATA), _skill("Databricks", L_DATA),
            _skill("Data Integration", L_DATA2), _skill("ETL", L_DATA2), _skill("Data Quality", L_DATA2), _skill("Data Discovery", L_DATA2),
            _skill("Enterprise data management", L_DATA2), _skill("Third-party and enterprise API integration", L_API),
            _skill("Azure DevOps", L_AZDO, proficiency="working_knowledge"), _skill("Jira", L_AZDO, proficiency="working_knowledge"),
            _skill("Metadata management and data governance", L_META, proficiency="working_knowledge"),
        ],
        "skill_any_of": [
            {"any_of": ["Azure", "AWS"], "strength": "required", "basis": b("jd", L_CLOUD)},
            {"any_of": ["TensorFlow", "PyTorch", "scikit-learn"], "strength": "required", "basis": b("jd", L_ML)},
        ],
        "evidence_signals": [
            {"name": "IC (individual contributor) engineer", "strength": "required", "basis": b("recruiter_brief", B_IC)},
            {"name": "Designs solutions for a client problem; understands client requirements", "strength": "required", "basis": b("recruiter_brief", B_FDE)},
            {"name": "Builds POCs and designs the system", "strength": "required", "basis": b("recruiter_brief", B_FDE)},
            {"name": "Works with existing teams to enhance existing products and features", "strength": "required", "basis": b("recruiter_brief", B_EXIST)},
            {"name": "Hybrid working basis", "strength": "required", "basis": b("recruiter_brief", B_LOC)},
            {"name": "Strong hands-on software engineering of enterprise-scale applications", "strength": "required", "basis": b("jd", L_HANDS)},
            {"name": "Solution design, architecture reviews and technical decision-making", "strength": "required", "basis": b("jd", L_DESIGN)},
            {"name": "Analytical, problem-solving and troubleshooting skills", "strength": "required", "basis": b("jd", L_SOFT)},
            {"name": "Communication and stakeholder management", "strength": "required", "basis": b("jd", L_COMM)},
            {"name": "Provides technical leadership and mentors team members", "strength": "context", "basis": b("jd", L_LEAD)},
        ],
    }


def evaluate(raw: dict):
    intent = ExperimentalHiringIntent.model_validate(raw)
    result = gold.evaluate(intent, JD, BRIEF)
    return intent, {r["id"]: r for r in result["critical"]}, result["validation"]


def statuses(r: dict) -> dict:
    return {k: v["status"] for k, v in r.items()}


# ---------------------------------------------------------------------------- freeze guards


def test_role1_and_the_frozen_prompt_are_untouched() -> None:
    """If this fails, someone edited a frozen Role 1 / cross-role artifact. Changing them needs an explicit owner decision."""
    assert _sha(PKG / "prompt_v3.txt") == "480a244816013f90b47dd56474ae11826cfa77e75a82cc4c525321a6fcb6691a"
    assert _sha(PKG / "inputs" / "role1_jd.txt") == "e1be55f46e5b9bb210b9dfa269621c6922a735572a884f71346839fee124d012"
    assert _sha(PKG / "inputs" / "role1_recruiter_brief.txt") == "81749f20a50e6f8934eb3a063a58c5fa2e82eca5328f6cfb5298b92625556dba"
    assert _sha(PKG / "gold_experimental.py") == "7335ecb3a4a622833432fb4f4857e8f2a14747fa37137efda468cdd52472b755"
    assert r2.PROMPT == "v3" and r2.prompt_sha256() == _sha(PKG / "prompt_v3.txt")


def test_role2_inputs_are_the_supplied_sources_and_contain_no_preference_wording() -> None:
    assert JD.startswith("Summary") and "Advanced proficiency in Python and Java" in JD and "12+ years" in JD
    assert BRIEF.startswith("Look for an IC Engineer") and "Hybrid basis" in BRIEF and "POC's" in BRIEF
    for text in (JD, BRIEF):
        for word in ("preferred", "nice to have", "ideally", "a plus", "bonus"):
            assert word not in text.lower()


def test_the_evaluator_and_runner_do_not_import_a_provider_or_the_compiler() -> None:
    forbidden = ("providers.crustdata", "providers.harvest", "search_pipeline", "requirement_judge", "search_translator", "backend.api", "search_compiler")
    for name in ("gold_role2.py", "run_role2.py"):
        for line in (PKG / name).read_text(encoding="utf-8").splitlines():
            if line.startswith(("import ", "from ")):
                assert not any(f in line for f in forbidden), (name, line)


def test_the_prompt_never_receives_ground_truth_or_assertions() -> None:
    text = build_prompt(JD, BRIEF, "v3")
    assert JD[:60] in text and BRIEF[:40] in text
    for needle in ("no_second_path", "ROLE2_GROUND_TRUTH", "hybrid_work_mode", "advanced_proficiency", "sourcing_paths must be empty"):
        assert needle not in text


# ---------------------------------------------------------------------------- the evaluator is calibrated


def test_the_schema_gaps_are_decided_from_the_schema_not_from_a_model() -> None:
    gaps = gold.schema_gaps()
    assert gaps["advanced_proficiency"]["representable"] is False and gaps["hybrid_work_mode"]["representable"] is False
    assert gaps["advanced_proficiency"]["values"] == ["hands_on", "working_knowledge"] and gaps["hybrid_work_mode"]["values"] == ["allowed", "not_allowed"]


def test_a_small_correct_intent_passes_everything_the_schema_can_express() -> None:
    _, r, v = evaluate(good2())
    assert {k: s for k, s in statuses(r).items() if s != gold.PASS} == {"advanced_proficiency": gold.PARTIAL, "hybrid_work_mode": gold.PARTIAL}
    assert r["advanced_proficiency"]["failure_class"] == gold.REPRESENTATION and r["hybrid_work_mode"]["failure_class"] == gold.REPRESENTATION
    assert v["errors"] == {}


@pytest.mark.parametrize("mutate,assertion,cls", [
    (lambda r: r.update(sourcing_paths=[{"id": "Option 1", "label": "x", "strategy": "domain_led"}]), "no_second_path", gold.EXTRACTION),
    (lambda r: r.update(semantic_exclusions=[{"concept": "people managers"}]), "no_invented_exclusion", gold.EXTRACTION),
    (lambda r: r.update(exclusions=[{"kind": "exclude_title", "value": "Engineering Manager"}]), "no_invented_exclusion", gold.EXTRACTION),
    (lambda r: r.update(companies=[{"name": "Palantir", "strength": "preferred"}]), "no_company_filter", gold.EXTRACTION),
    (lambda r: r.update(company_scale={"minimum_employees": 500, "strength": "required"}), "no_company_filter", gold.EXTRACTION),
    (lambda r: r.update(role_family=["Software Engineer", "Solution Architect", "Forward Deployed Engineer"]), "fidelity_role_family", gold.EXTRACTION),
    (lambda r: r["seniority"].update(value="Principal"), "seniority_staff", gold.EXTRACTION),
    (lambda r: r["seniority"].update(alternatives=["Lead"]), "seniority_staff", gold.EXTRACTION),
    (lambda r: r["seniority"].update(leadership=["technical"]), "no_hard_seniority_from_responsibilities", gold.EXTRACTION),
    (lambda r: r.update(domain=[{"name": "AI solutions", "strength": "preferred"}]), "no_role1_concepts", gold.EXTRACTION),
    (lambda r: r["location"].update(countries=["India"]), "no_role1_concepts", gold.EXTRACTION),
    (lambda r: r["location"].update(remote="allowed"), "hybrid_work_mode", gold.EXTRACTION),
    (lambda r: r["location"].update(entries=["Hyderabad, Telangana, India", "Pune, Maharashtra, India"]), "fidelity_geography_hyderabad", gold.EXTRACTION),
    (lambda r: r["location"].update(radius={"value": 25, "unit": "miles", "around": "Hyderabad, Telangana, India"}), "fidelity_geography_hyderabad", gold.EXTRACTION),
    (lambda r: r["skills"][0].update(proficiency="working_knowledge"), "advanced_proficiency", gold.EXTRACTION),
    (lambda r: r["skills"][13].update(proficiency="hands_on"), "no_invented_proficiency", gold.EXTRACTION),         # React has no stated depth
    (lambda r: r["skills"][23].update(proficiency="hands_on"), "no_preference_hardened", gold.EXTRACTION),          # 'Familiarity' overstated
    (lambda r: r["experience"].update(minimum_years=10), "fidelity_experience_12", gold.EXTRACTION),
    (lambda r: r["experience"].update(strength="preferred"), "fidelity_experience_12", gold.EXTRACTION),
    (lambda r: r.update(education=None), "fidelity_education", gold.EXTRACTION),
], ids=lambda x: x if isinstance(x, str) else "")
def test_each_over_application_or_fidelity_error_fails_its_assertion(mutate, assertion, cls) -> None:
    raw = good2()
    mutate(raw)
    _, r, _ = evaluate(raw)
    assert r[assertion]["status"] in (gold.FAIL, gold.PARTIAL), r[assertion]
    assert r[assertion]["failure_class"] == cls


def test_or_groups_turned_into_ands_and_ands_into_ors_are_caught() -> None:
    raw = good2()
    raw["skill_any_of"] = [raw["skill_any_of"][1]]
    raw["skills"] += [_skill("Azure", L_CLOUD), _skill("AWS", L_CLOUD)]
    _, r, _ = evaluate(raw)
    assert r["fidelity_cloud_or"]["status"] == gold.FAIL and "AND" in r["fidelity_cloud_or"]["evidence"]
    raw = good2()
    raw["skills"] = [s for s in raw["skills"] if s["name"] not in ("Python", "Java")]
    raw["skill_any_of"].append({"any_of": ["Python", "Java"], "strength": "required", "basis": b("jd", L_PYJ)})
    _, r, _ = evaluate(raw)
    assert r["fidelity_python_and_java"]["status"] == gold.FAIL


def test_a_requirement_weakened_to_preferred_is_reported_but_familiarity_may_be_either() -> None:
    raw = good2()
    for s in raw["skills"]:
        if s["name"] in ("Python", "Java"):
            s["strength"] = "preferred"
    _, r, _ = evaluate(raw)
    assert r["strength_requirements_not_weakened"]["status"] != gold.PASS and r["fidelity_python_and_java"]["status"] == gold.PARTIAL
    raw = good2()
    for s in raw["skills"]:
        if s["name"] in ("Azure DevOps", "Jira"):
            s["strength"] = "preferred"
    _, r, _ = evaluate(raw)
    assert r["strength_requirements_not_weakened"]["status"] == gold.PASS


def test_responsibility_language_is_not_a_seniority_requirement() -> None:
    raw = good2()
    raw["evidence_signals"][-1]["strength"] = "required"          # 'technical leadership / mentor' hardened
    _, r, _ = evaluate(raw)
    assert r["no_hard_seniority_from_responsibilities"]["status"] == gold.PARTIAL
    raw = good2()
    raw["evidence_signals"].append({"name": "Manages a team of engineers", "strength": "required", "basis": b("jd", L_LEAD)})
    _, r, _ = evaluate(raw)
    assert r["no_hard_seniority_from_responsibilities"]["status"] == gold.FAIL
    raw = good2()
    raw["evidence_signals"].append({"name": "Not a people-management role", "strength": "required", "basis": b("recruiter_brief", B_IC)})
    _, r, _ = evaluate(raw)
    assert r["no_hard_seniority_from_responsibilities"]["status"] == gold.PASS      # a denial is not a requirement


def test_poc_is_recognised_in_its_plural_and_spelled_out_forms() -> None:
    """Post-run correction: five real runs wrote 'proofs of concept' and the first pattern missed it."""
    for wording in ("Build proofs of concept", "Builds POCs and designs the system", "builds a proof of concept", "prototype POC work"):
        raw = good2()
        raw["evidence_signals"][2]["name"] = wording
        _, r, _ = evaluate(raw)
        assert r["fidelity_brief_profile"]["status"] == gold.PASS, wording
    raw = good2()
    raw["evidence_signals"][2]["name"] = "Designs the system"
    _, r, _ = evaluate(raw)
    assert r["fidelity_brief_profile"]["status"] == gold.PARTIAL


def test_losing_a_stated_fact_is_a_fidelity_failure_not_a_schema_failure() -> None:
    raw = good2()
    raw["location"].update(remote=None)
    raw["evidence_signals"] = [e for e in raw["evidence_signals"] if "Hybrid" not in e["name"]]
    _, r, _ = evaluate(raw)
    assert (r["hybrid_work_mode"]["status"], r["hybrid_work_mode"]["failure_class"]) == (gold.FAIL, gold.EXTRACTION)
    raw = good2()
    raw["evidence_signals"] = [e for e in raw["evidence_signals"] if "IC" not in e["name"]]
    _, r, _ = evaluate(raw)
    assert r["fidelity_brief_profile"]["status"] == gold.FAIL
    raw = good2()
    raw["seniority"] = None
    _, r, _ = evaluate(raw)
    assert r["seniority_staff"]["status"] == gold.PARTIAL


def test_reconciliation_discipline_flags_an_invented_waiver_and_an_invented_conflict() -> None:
    raw = good2()
    raw["reconciliations"] = [{"topic": "Java", "action": "waived", "jd_quote": L_PYJ, "brief_quote": B_IC, "result": "Java is not required."}]
    _, r, _ = evaluate(raw)
    assert (r["reconciliation_discipline"]["status"], r["reconciliation_discipline"]["failure_class"]) == (gold.FAIL, gold.RECONCILIATION)
    raw = good2()
    raw["reconciliations"] = [{"topic": "Experience scope", "action": "unresolved", "jd_quote": L_EXP, "brief_quote": B_IC, "result": "Unclear whether 12 years is per discipline."}]
    _, r, _ = evaluate(raw)
    assert r["reconciliation_discipline"]["status"] == gold.PARTIAL
    raw = good2()
    raw["reconciliations"] = [{"topic": "People leadership", "action": "narrowed", "jd_quote": L_LEAD, "brief_quote": B_IC, "result": "IC: technical leadership, not people management."}]
    _, r, _ = evaluate(raw)
    assert r["reconciliation_discipline"]["status"] == gold.PASS      # a leadership/IC clarification is legitimate


def test_provenance_and_validators_catch_invented_or_misplaced_claims() -> None:
    raw = good2()
    raw["skills"].append({"name": "Kubernetes", "strength": "required", "basis": {"sources": ["inferred"], "quote": None}})
    _, r, v = evaluate(raw)
    assert r["provenance_preserved"]["status"] == gold.PARTIAL and r["provenance_preserved"]["failure_class"] == gold.PROVENANCE
    assert "inferred_hard_constraint" in {d["code"] for d in v["diagnostics"]}
    raw = good2()
    raw["location"]["basis"] = b("jd", B_LOC)                         # Hyderabad is the brief's, not the JD's
    _, r, _ = evaluate(raw)
    assert r["provenance_location_from_brief"]["status"] == gold.FAIL
    raw = good2()
    raw["location"]["countries"] = ["India"]                          # India is stated in neither source
    _, r, v = evaluate(raw)
    assert "place_not_in_source" in {d["code"] for d in v["diagnostics"]} and r["generic_validators_clean"]["status"] == gold.FAIL
    raw = good2()
    raw["seniority"]["value"] = "Principal"                           # a level the sources never state
    _, r, v = evaluate(raw)
    assert "unsupported_level" in {d["code"] for d in v["diagnostics"]}
    raw = good2()
    raw["location"]["remote"] = "allowed"                             # no source line about remote work
    _, _, v = evaluate(raw)
    assert "remote_unsupported" in {d["code"] for d in v["diagnostics"]}


def test_the_single_strategy_role_is_not_helped_by_empty_scaffolding() -> None:
    """Smaller and correct is accepted: an intent with only the stated facts and no unused Role 1 structure leaves those fields empty."""
    intent, r, _ = evaluate(good2())
    assert not intent.sourcing_paths and not intent.semantic_exclusions and not intent.exclusions and not intent.domain and not intent.companies
    assert not intent.reconciliations and (intent.seniority and not intent.seniority.leadership and not intent.seniority.alternatives)
    assert r["no_role1_concepts"]["status"] == gold.PASS


# ---------------------------------------------------------------------------- harness (fake client)


class _Fake:
    def __init__(self, payload: str) -> None:
        self._payload = payload
        self.responses = self
        self.prompts = []

    def create(self, **kwargs):
        assert kwargs.get("stream") is True
        self.prompts.append(kwargs["input"][0]["content"])
        final = SimpleNamespace(output_text=self._payload, usage=SimpleNamespace(input_tokens=5, output_tokens=3))
        return iter([SimpleNamespace(type="response.completed", response=final)])


def test_the_runner_uses_the_frozen_prompt_and_records_intent_gold_and_validation() -> None:
    fake = _Fake(json.dumps(good2()))
    record = r2.run_once(1, lambda: fake, JD, BRIEF)
    assert record["error"] is None and record["gold"]["validation"]["errors"] == {}
    assert JD[:50] in fake.prompts[0] and "belongs to THAT path only" in fake.prompts[0]
    assert record["model_calls"][0]["model"] == "gpt-6.1-sol" and record["model_calls"][0]["reasoning"] == {"effort": "medium"} and record["model_calls"][0]["streamed"]
    assert "compiled" not in record


def test_stability_summarises_meaning_across_runs_and_a_parse_failure_is_a_result() -> None:
    other = good2()
    other["skills"][23]["proficiency"] = "hands_on"            # Azure DevOps: the JD says "Familiarity"
    records = [r2.run_once(i, lambda p=p: _Fake(json.dumps(p)), JD, BRIEF) for i, p in enumerate((good2(), good2(), other), 1)]
    bad = r2.run_once(4, lambda: _Fake("not json"), JD, BRIEF)
    assert bad["error"] and "intent" not in bad
    s = r2.stability(records + [bad])
    assert s["runs"] == 4 and s["parsed"] == 3 and s["components"]["paths"]["agreement"] == "3/3"
    assert s["components"]["proficiency"]["agreement"] == "2/3"
    assert s["assertion_statuses"]["no_invented_proficiency"] == {"PASS": 2, "FAIL": 1}


def test_the_role2_runner_refuses_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert r2.main(["--runs", "1"]) == 2
