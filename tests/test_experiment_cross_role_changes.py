"""Changes made after Role 2, before Role 3 (EXPERIMENT ONLY): ordinal proficiency, typed work mode, and five generic validators.

Offline and model-free. Section A-F cover each change; the last section is the regression guard: Role 1 and Role 2 inputs, ground truth,
results, prompts and evaluators are pinned by hash and re-evaluated, the production StructuredHiringIntent is untouched, and every stored
intent from every earlier arm still validates against the extended schema.

Validators in `validators_cross_role` are role-agnostic; the synthetic sources below are deliberately unrelated to Roles 1 and 2.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.experiments.intake_strategy import compare_arms, compare_role2
from backend.experiments.intake_strategy import experimental_schema as schema
from backend.experiments.intake_strategy import gold_experimental, gold_role2
from backend.experiments.intake_strategy import run_baseline, run_role2
from backend.experiments.intake_strategy.experimental_extractor import DEFAULT_PROMPT, PROMPTS, build_prompt
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent, effective_view
from backend.experiments.intake_strategy.validators import validate
from backend.experiments.intake_strategy.validators_cross_role import (
    CROSS_ROLE_ERROR_CODES,
    classify_lines,
    validate_cross_role,
)
from backend.models.structured_intent import Seniority, StructuredHiringIntent
from backend.services.search_compiler import compile_intent

PKG = Path(run_role2.__file__).parent
REPO = PKG.parents[2]
R2 = run_role2.load_inputs()
R1 = run_baseline.load_inputs()
JD2, BRIEF2 = R2["jd"], R2["brief"]


def b(source: str, quote: str | None) -> dict:
    return {"sources": [source], "quote": quote}


def base(**kw) -> dict:
    out = {"role_archetype": {"value": "hybrid", "confidence": 0.8, "rationale": "x"}, "role_family": ["Software Engineer"]}
    out.update(kw)
    return out


def check(raw: dict, jd: str, brief: str = "") -> dict:
    return validate_cross_role(ExperimentalHiringIntent.model_validate(raw), jd, brief)


def codes(report: dict) -> set:
    return {d["code"] for d in report["diagnostics"]}


L_PYJ = "Advanced proficiency in Python and Java with strong experience building APIs, services, and distributed systems."
L_UI = "Experience building modern user interfaces using React, Bootstrap, and related frameworks."
L_AZDO = "Familiarity with Azure DevOps, Jira, and modern software delivery practices."
L_CHAMPION = "Champion engineering best practices, coding standards, testing strategies, and quality metrics across development teams."
L_GENAI_REQ = "Hands-on experience implementing and deploying Generative AI solutions in production environments."
L_GENAI_RESP = "Build and deploy AI-powered applications utilizing Large Language Models (LLMs), Retrieval-Augmented Generation (RAG), Agentic AI frameworks, and modern AI orchestration patterns."
L_SOFT = "Strong analytical, problem-solving, and troubleshooting skills."
B_EXIST = "he would be working closely with the existing teams on enhancing the existing products and features."
B_HYBRID = "Location is Hyderabad and need someone who can work on a Hybrid basis."


# ================================================================== A. advanced proficiency


def test_a_schema_gains_one_ordinal_value_and_stays_backward_compatible() -> None:
    assert schema.PROFICIENCIES == ("hands_on", "working_knowledge", "advanced")
    assert schema.PROFICIENCY_RANK["working_knowledge"] < schema.PROFICIENCY_RANK["hands_on"] < schema.PROFICIENCY_RANK["advanced"]
    for value in ("advanced", "hands_on", "working_knowledge", None):
        assert ExperimentalHiringIntent.model_validate(base(skills=[{"name": "Python", "proficiency": value}])).skills[0].proficiency == value
    with pytest.raises(ValidationError):
        ExperimentalHiringIntent.model_validate(base(skills=[{"name": "Python", "proficiency": "expert"}]))   # no free-form ladder
    assert ExperimentalHiringIntent.model_validate(base(skills=[{"name": "Python"}])).skills[0].proficiency is None   # unstated stays unstated


def test_a_advanced_is_distinct_from_hands_on_and_is_checked_against_the_wording() -> None:
    ok = check(base(skills=[{"name": "Python", "proficiency": "advanced", "basis": b("jd", L_PYJ)}]), L_PYJ)
    assert "unsupported_proficiency" not in codes(ok)
    understated = check(base(skills=[{"name": "Python", "proficiency": "hands_on", "basis": b("jd", L_PYJ)}]), L_PYJ)
    assert "unsupported_proficiency" not in codes(understated)                                   # a lower depth is not an INVENTED depth
    assert [d for d in understated["diagnostics"] if d["code"] == "proficiency_understated"]    # but the lost 'advanced' is visible
    assert "proficiency_understated" not in understated["cross_role_errors"]                    # informational, never an error


def test_a_a_weaker_statement_is_never_read_as_hands_on() -> None:
    report = check(base(skills=[{"name": "Azure DevOps", "proficiency": "hands_on", "basis": b("jd", L_AZDO)}]), L_AZDO)
    err = [d for d in report["diagnostics"] if d["code"] == "unsupported_proficiency"]
    assert err and "weaker depth" in err[0]["detail"] and report["errors"]["unsupported_proficiency"] == 1
    assert "unsupported_proficiency" not in codes(check(base(skills=[{"name": "Azure DevOps", "proficiency": "working_knowledge", "basis": b("jd", L_AZDO)}]), L_AZDO))


def test_a_an_unspecified_skill_is_not_promoted_to_a_level() -> None:
    promoted = check(base(skills=[{"name": "React", "proficiency": "hands_on", "basis": b("jd", L_UI)}]), L_UI)
    assert "unsupported_proficiency" in codes(promoted) and "states no depth" in [d for d in promoted["diagnostics"] if d["code"] == "unsupported_proficiency"][0]["detail"]
    assert "unsupported_proficiency" not in codes(check(base(skills=[{"name": "React", "proficiency": None, "basis": b("jd", L_UI)}]), L_UI))
    assert "unsupported_proficiency" in codes(check(base(skills=[{"name": "Python", "proficiency": "advanced", "basis": b("jd", L_UI)}]), L_UI))


def test_a_the_depth_cue_must_be_about_the_skill_that_carries_it() -> None:
    """'Advanced' belongs to Python/Java in that sentence; it does not support a different skill that cites the same sentence."""
    report = check(base(skills=[{"name": "Kubernetes Operations", "proficiency": "advanced", "basis": b("jd", L_PYJ)}]), L_PYJ)
    assert "unsupported_proficiency" in codes(report)


def test_a_downstream_compiler_behaviour_is_unchanged() -> None:
    plain = ExperimentalHiringIntent.model_validate(base(skills=[{"name": "Python", "strength": "required", "relationship": "any"}]))
    deep = ExperimentalHiringIntent.model_validate(base(skills=[{"name": "Python", "strength": "required", "relationship": "any", "proficiency": "advanced"}]))
    a, c = compile_intent(plain), compile_intent(deep)
    # Updated in the compiler-hardening phase: the PROVIDER plan is still unchanged by proficiency (a depth is never a provider filter), but the compiler
    # no longer ignores it: it adds one downstream audit row carrying the stated level (it used to be silently dropped).
    assert a.filter_tree == c.filter_tree
    extra = [x for x in c.audit if x not in a.audit]
    assert [x.source for x in extra] == ["proficiency:Python=advanced"] and extra[0].route == "downstream_evidence"


# ================================================================== B. work mode


def test_b_work_mode_is_typed_optional_and_separate_from_remote() -> None:
    assert schema.WORK_MODES == ("remote", "hybrid", "onsite") and schema.REMOTE_VALUES == ("allowed", "not_allowed")
    for mode in ("remote", "hybrid", "onsite", None):
        assert ExperimentalHiringIntent.model_validate(base(location={"entries": ["Pune, Maharashtra, India"], "work_mode": mode})).location.work_mode == mode
    assert ExperimentalHiringIntent.model_validate(base(location={"entries": ["Pune, Maharashtra, India"]})).location.work_mode is None   # None = unspecified
    for bad in ({"work_mode": "flexible"}, {"remote": "hybrid"}):          # 'hybrid' may NOT be expressed through `remote`
        with pytest.raises(ValidationError):
            ExperimentalHiringIntent.model_validate(base(location={"entries": ["Pune, Maharashtra, India"], **bad}))


def test_b_role_1_remote_allowed_keeps_its_meaning_and_coexists_with_work_mode() -> None:
    role1_shape = ExperimentalHiringIntent.model_validate(base(location={"countries": ["India"], "remote": "allowed"}))
    assert role1_shape.location.remote == "allowed" and role1_shape.location.work_mode is None
    both = ExperimentalHiringIntent.model_validate(base(location={"entries": ["Hyderabad, Telangana, India"], "remote": "not_allowed", "work_mode": "hybrid"}))
    assert (both.location.remote, both.location.work_mode) == ("not_allowed", "hybrid")


def test_b_work_mode_is_not_geography_and_travels_with_a_path_location() -> None:
    no_place = ExperimentalHiringIntent.model_validate(base(location={"work_mode": "hybrid"}))
    assert no_place.location.entries == [] and no_place.location.countries == [] and no_place.location.work_mode == "hybrid"
    pathed = ExperimentalHiringIntent.model_validate(base(
        sourcing_paths=[{"id": "Option 1", "label": "a", "strategy": "domain_led", "location": {"countries": ["India"], "work_mode": "remote"}},
                        {"id": "Option 2", "label": "b", "strategy": "capability_led", "location": {"entries": ["Pune, Maharashtra, India"], "work_mode": "onsite"}}]))
    assert effective_view(pathed, "Option 1")["location"].work_mode == "remote" and effective_view(pathed, "Option 2")["location"].work_mode == "onsite"


def test_b_work_mode_must_be_stated_by_a_source() -> None:
    assert "work_mode_unsupported" not in codes(check(base(location={"entries": ["Hyderabad, Telangana, India"], "work_mode": "hybrid", "basis": b("recruiter_brief", B_HYBRID)}), "", BRIEF2))
    unsupported = check(base(location={"entries": ["Hyderabad, Telangana, India"], "work_mode": "hybrid"}), R1["jd"], R1["brief"])
    assert "work_mode_unsupported" in codes(unsupported) and unsupported["errors"]["work_mode_unsupported"] == 1
    strategy_word = check(base(location={"entries": ["Pune, Maharashtra, India"], "work_mode": "hybrid"}), "Source B is capability-led / hybrid.")
    assert "work_mode_unsupported" in codes(strategy_word)                 # 'hybrid' as a strategy is not a working arrangement
    negated = check(base(location={"entries": ["Pune, Maharashtra, India"], "work_mode": "remote"}), "This is not a remote role. The team sits in Pune.")
    assert "work_mode_unsupported" in codes(negated)                       # a denial does not state it
    assert "work_mode_unsupported" not in codes(check(base(location={"entries": ["Pune, Maharashtra, India"], "work_mode": "onsite"}), "You will work on-site in Pune."))


def test_b_work_mode_does_not_reach_the_compiler() -> None:
    off = ExperimentalHiringIntent.model_validate(base(location={"entries": ["Hyderabad, Telangana, India"], "work_mode": None}))
    on = ExperimentalHiringIntent.model_validate(base(location={"entries": ["Hyderabad, Telangana, India"], "work_mode": "hybrid"}))
    assert compile_intent(off).filter_tree == compile_intent(on).filter_tree
    assert schema.schema_concepts()["work_mode"] and schema.schema_concepts()["ordinal_proficiency"]


# ================================================================== C. title analogy


UNRELATED_JD = "Role: Bookkeeper.\nYou will keep the ledgers."


@pytest.mark.parametrize("cue", ["more like a", "similar to a", "resembles a", "like a", "reminiscent of a", "someone like a", "more like the"])
def test_c_a_title_named_only_in_a_comparison_is_not_a_target_title(cue: str) -> None:
    brief = f"We want a bookkeeper, {cue} financial controller who owns the month-end close."
    report = check(base(role_family=["Bookkeeper", "Financial Controller"]), UNRELATED_JD, brief)
    flagged = [d for d in report["diagnostics"] if d["code"] == "title_analogy"]
    assert len(flagged) == 1 and "Financial Controller" in flagged[0]["ref"]      # only the reference title; Bookkeeper is the target


def test_c_the_role_2_error_is_caught_without_naming_it_in_the_code() -> None:
    report = check(base(role_family=["Software Engineer", "Solution Architect", "Forward Deployed Engineer"]), JD2, BRIEF2)
    assert [d["ref"] for d in report["diagnostics"] if d["code"] == "title_analogy"] == ["role_family[Forward Deployed Engineer]"]
    source = (PKG / "validators_cross_role.py").read_text(encoding="utf-8").lower()
    for name in ("forward", "deployed", "bookkeeper", "controller"):
        assert name not in source.replace("a bookkeeper", "")                        # the docstring example text aside, no title is known


def test_c_a_comparison_title_that_the_source_also_presents_as_a_target_is_kept() -> None:
    brief = "We want a financial controller. The profile is similar to a financial controller at a mid-size business."
    assert "title_analogy" not in codes(check(base(role_family=["Financial Controller"]), UNRELATED_JD, brief))
    assert "title_analogy" not in codes(check(base(role_family=["Staff Accountant"]), UNRELATED_JD, "Nothing about that title here."))   # not mentioned: not this check's job


def test_c_title_variants_and_the_context_signal_are_handled() -> None:
    brief = "Hire a clerk, more like a data-steward who cleans reference data."
    assert "title_analogy" in codes(check(base(role_family=["Data Steward"]), "Clerical role.", brief))          # hyphen vs space
    assert "title_analogy" in codes(check(base(role_family=["Data Stewards"]), "Clerical role.", brief))         # plural
    kept = check(base(role_family=["Clerk"], evidence_signals=[{"name": "Profile resembles a data steward", "strength": "context", "basis": b("recruiter_brief", brief)}]),
                 "Clerical role.", brief)
    assert "title_analogy" not in codes(kept)                                                                     # the comparison may live as context


# ================================================================== D. responsibility-only requirement


def _sig(name: str, quote: str, source: str = "jd", strength: str = "required") -> dict:
    return {"name": name, "strength": strength, "basis": b(source, quote)}


def test_d_a_responsibility_only_required_atom_is_flagged_and_visible() -> None:
    report = check(base(evidence_signals=[_sig("Champion engineering best practices", L_CHAMPION)]), JD2, BRIEF2)
    flagged = [d for d in report["diagnostics"] if d["code"] == "responsibility_only_required"]
    assert len(flagged) == 1 and "evidence_signals[0]" == flagged[0]["ref"]
    assert report["errors"]["responsibility_only_required"] == 1 and "responsibility_only_required" in CROSS_ROLE_ERROR_CODES


def test_d_context_a_stated_qualification_and_a_brief_criterion_are_not_flagged() -> None:
    assert "responsibility_only_required" not in codes(check(base(evidence_signals=[_sig("Champion engineering best practices", L_CHAMPION, strength="context")]), JD2, BRIEF2))
    assert "responsibility_only_required" not in codes(check(base(evidence_signals=[_sig("Strong analytical and troubleshooting skills", L_SOFT)]), JD2, BRIEF2))
    # cites the responsibility line, but the same thing is also stated as a qualification elsewhere in the JD
    assert "responsibility_only_required" not in codes(check(base(evidence_signals=[_sig("Hands-on experience implementing and deploying Generative AI solutions in production", L_GENAI_RESP)]), JD2, BRIEF2))
    assert "responsibility_only_required" not in codes(check(base(evidence_signals=[_sig("Works with the existing teams on existing products", B_EXIST, "recruiter_brief")]), JD2, BRIEF2))


def test_d_the_distinction_is_semantic_not_just_the_heading() -> None:
    no_headings = "Own the data platform roadmap.\nBuild and maintain ETL pipelines.\n5+ years of experience with Spark."
    report = check(base(evidence_signals=[_sig("Own the data platform roadmap", "Own the data platform roadmap.")], skills=[_skill_spark()]), no_headings)
    assert [d["ref"] for d in report["diagnostics"] if d["code"] == "responsibility_only_required"] == ["evidence_signals[0]"]   # imperative, no heading
    renamed = "What you'll do\nLead the migration to the new billing system.\nWhat you'll bring\nExperience with billing systems."
    assert "responsibility_only_required" in codes(check(base(evidence_signals=[_sig("Lead the billing migration", "Lead the migration to the new billing system.")]), renamed))
    assert "responsibility_only_required" not in codes(check(base(evidence_signals=[_sig("Experience with billing systems", "Experience with billing systems.")]), renamed))
    misfiled = "Responsibilities\nMust have 5+ years of payments experience.\nPartner with finance."
    assert "responsibility_only_required" not in codes(check(base(evidence_signals=[_sig("5+ years of payments experience", "Must have 5+ years of payments experience.")]), misfiled))
    nonselection = "Responsibilities\nMaintain the tooling required for release management."
    assert "responsibility_only_required" in codes(check(base(evidence_signals=[_sig("Maintain release tooling", "Maintain the tooling required for release management.")]), nonselection))


def _skill_spark() -> dict:
    return {"name": "Spark", "strength": "required", "relationship": "any", "basis": b("jd", "5+ years of experience with Spark.")}


def test_d_line_classification_is_exposed_and_headings_are_not_atoms() -> None:
    def kind(prefix: str) -> str:
        return next(ln["kind"] for ln in classify_lines(JD2) if ln["text"].startswith(prefix))
    assert kind("Job Responsibilities") == "heading" and kind("Requirements / Skills") == "heading"
    assert kind("Champion engineering best practices") == "responsibility"
    assert kind("Strong analytical, problem-solving") == "qualification"


# ================================================================== E. unsupported current relationship


def test_e_current_without_a_source_statement_of_present_use_is_flagged() -> None:
    jd = "Experience with Python.\nCurrently working with Kubernetes in production.\nStay current with advancements in cloud."
    raw = base(skills=[
        {"name": "Python", "relationship": "current", "basis": b("jd", "Experience with Python.")},
        {"name": "Kubernetes", "relationship": "current", "basis": b("jd", "Currently working with Kubernetes in production.")},
        {"name": "Cloud advancements", "relationship": "current", "basis": b("jd", "Stay current with advancements in cloud.")},
        {"name": "Python again", "relationship": "any", "basis": b("jd", "Experience with Python.")},
    ])
    report = check(raw, jd)
    flagged = sorted(d["ref"] for d in report["diagnostics"] if d["code"] == "unsupported_current_relationship")
    assert flagged == ["skills[0]", "skills[2]"]        # 'Stay current with' is not present use; the `any` skill and the stated 'Currently' are fine
    assert report["errors"]["unsupported_current_relationship"] == 2


def test_e_groups_companies_and_approved_knowledge_are_covered() -> None:
    jd = "Experience with Spark or Flink.\nWorked at Acme."
    raw = base(skill_any_of=[{"any_of": ["Spark", "Flink"], "relationship": "current", "basis": b("jd", "Experience with Spark or Flink.")}],
               companies=[{"name": "Acme", "relationship": "current", "strength": "preferred", "basis": b("jd", "Worked at Acme.")}],
               skills=[{"name": "Spark", "relationship": "current", "basis": {"sources": ["approved_knowledge"], "quote": None}}])
    assert sorted(d["ref"] for d in check(raw, jd)["diagnostics"] if d["code"] == "unsupported_current_relationship") == ["companies[0]", "skill_any_of[0]"]


def test_e_the_role_2_pattern_is_flagged_for_every_current_skill() -> None:
    """Replays the stored Role 2 runs: every required skill marked `current` had no present-use wording in its source (read-only)."""
    for path in sorted((PKG / "results" / "role2").glob("role2_run*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        intent = ExperimentalHiringIntent.model_validate(record["intent"])
        current = sum(1 for s in intent.skills if s.relationship == "current")
        flagged = validate_cross_role(intent, JD2, BRIEF2)["cross_role_errors"].get("unsupported_current_relationship", 0)
        assert flagged == current


# ================================================================== F. unknown seniority is preserved, never substituted


def test_f_an_unknown_level_is_preserved_by_the_representation() -> None:
    raw = base(seniority={"value": "Staff", "strength": "required", "basis": b("jd", "Staff Software Engineer/ Solution Architect - AI Solutions")})
    intent = ExperimentalHiringIntent.model_validate(raw)
    assert intent.seniority.value == "Staff" and ExperimentalHiringIntent.model_validate(intent.model_dump()).seniority.value == "Staff"
    report = check(raw, JD2, BRIEF2)
    assert "unsupported_level" not in codes(report) and report["errors"] == {}
    assert Seniority(value="Staff").value == "Staff"                                  # the production type is free text too


def test_f_the_compiler_carries_the_unknown_level_verbatim_and_never_rewrites_it() -> None:
    plan = compile_intent(ExperimentalHiringIntent.model_validate(base(seniority={"value": "Staff", "strength": "required"})))
    row = [a for a in plan.audit if a.source == "seniority"]
    assert row and "value=Staff" in row[0].note and row[0].route == "admission_level_fit"


def test_f_substituting_a_different_known_level_is_flagged() -> None:
    raw = base(seniority={"value": "Principal", "strength": "required", "basis": b("jd", "Staff Software Engineer/ Solution Architect - AI Solutions")})
    report = check(raw, JD2, BRIEF2)
    assert [d for d in report["diagnostics"] if d["code"] == "unsupported_level" and "Principal" in d["detail"]]


def test_f_the_v4_prompt_keeps_an_unknown_level_as_written() -> None:
    text = PROMPTS["v4"].read_text(encoding="utf-8")
    assert "keep the source's own word as written" in text and "never replace it with a listed level and never drop it" in text


# ================================================================== prompts


_ROLE_TERMS = ("power query", "sql", "python", "soc", "cyber", "hyderabad", "pune", "india", "legal", "lpo", "security", "data analyst", "relativity",
               "canopy", "breach", "path a", "path b", "incident", "siem", "lead data", "senior", "firm", "6+", "forward deployed", "poc", "proofs of concept",
               "staff", "aks", "eks", "terraform", "ic engineer", "solution architect", "azure", "aws", "snowflake", "react")


def test_the_v4_prompt_is_a_new_file_keeps_production_rules_and_adds_only_generic_text() -> None:
    import re
    prod = (REPO / "prompts" / "structured_intent.txt").read_text(encoding="utf-8")
    v4 = PROMPTS["v4"].read_text(encoding="utf-8")
    assert prod[prod.index("RULES — these are hiring-intent semantics"):prod.index("There are two sources of hiring intent")] in v4
    added = v4[v4.index("11. SOURCE ROLES AND PRIORITY"):v4.index("Job description / notes:")]
    for term in _ROLE_TERMS:
        assert not re.search(rf"\b{re.escape(term)}\b", added, re.I), term
    for needle in ('"advanced" (the source says advanced or expert-level proficiency)', "never read a weaker statement as a stronger depth", '"location.work_mode"',
                   "never express \"hybrid\" or \"onsite\" through \"remote\"", "21. TITLE ANALOGY", "22. RESPONSIBILITIES ARE NOT SELECTION CRITERIA",
                   "23. TEMPORAL RELATIONSHIP", "use \"any\"", "A title named in a comparison is a target only if"):
        assert needle in v4, needle
    assert "{job_description}" in v4 and "{recruiter_brief}" in v4
    assert DEFAULT_PROMPT == "v3" and run_role2.PROMPT == "v3"                          # the frozen runners keep their prompt; Role 3 selects v4


def test_domain_is_untouched_optional_and_not_expanded() -> None:
    v3, v4 = PROMPTS["v3"].read_text(encoding="utf-8"), PROMPTS["v4"].read_text(encoding="utf-8")
    rule17 = lambda t: t[t.index("17. DOMAIN."):t.index("18. LOCATION")]          # noqa: E731
    assert rule17(v3) == rule17(v4)                                               # not reworded, not expanded
    assert set(schema.DomainReq.model_fields) == {"strength", "basis", "name"}    # same members as Role 1 established
    assert ExperimentalHiringIntent.model_validate(base()).domain == []           # optional: a role may correctly have none
    assert schema.ExperimentalHiringIntent.model_fields["domain"].is_required() is False


def test_the_v4_prompt_never_receives_ground_truth() -> None:
    text = build_prompt(JD2, BRIEF2, "v4")
    for needle in ("ROLE2_GROUND_TRUTH", "no_second_path", "title_analogy", "responsibility_only_required"):
        assert needle not in text


# ================================================================== regression: Role 1 / Role 2 frozen; production untouched


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _combined(paths) -> str:
    h = hashlib.sha256()
    for p in sorted(str(x.relative_to(PKG)) for x in paths):
        h.update(p.encode())
        h.update(hashlib.sha256((PKG / p).read_bytes()).digest())
    return h.hexdigest()


def test_role_1_files_results_and_evaluators_are_unmodified() -> None:
    """If this fails, a frozen Role 1 artifact changed. That needs an explicit owner decision."""
    pinned = {
        "inputs/role1_jd.txt": "e1be55f46e5b9bb210b9dfa269621c6922a735572a884f71346839fee124d012",
        "inputs/role1_recruiter_brief.txt": "81749f20a50e6f8934eb3a063a58c5fa2e82eca5328f6cfb5298b92625556dba",
        "gold_experimental.py": "7335ecb3a4a622833432fb4f4857e8f2a14747fa37137efda468cdd52472b755",
        "gold_assertions.py": "3d73149e267b5fed6d79dc7d69fc87540130776f7a04a5cfcbcdf60a1e34e43d",
        "validators.py": "b9895980c85013e3f73d80224344b0a635b46a0b3a69b67b17d6402e9b351ce5",
        "prompt_v2.txt": "abbfa445ba4592f6c33a3fb5e982429b41844f7377c49a5db2356eb5d8f37f58",
        "prompt_v3.txt": "480a244816013f90b47dd56474ae11826cfa77e75a82cc4c525321a6fcb6691a",
        "run_experimental.py": "98b79d27c6256c22738510b10ff2ca575495c8b4d15c00ac4fc964b74b3c6bbf",
        "run_role2.py": "82377240d78ff9298fd6764875d3b47e768ec685ac129ff5be006c08921131ca",
    }
    for rel, digest in pinned.items():
        assert _sha(PKG / rel) == digest, rel
    role1_results = [*(PKG / "results" / "baseline").glob("*"), *(PKG / "results" / "experimental").glob("*"), *(PKG / "results" / "experimental_v3").glob("*"),
                     PKG / "results" / "comparison.json"]
    assert len(role1_results) == 19 and _combined(role1_results) == "c0887437b720ac58ace97e8ebaa10c048de66046d742663758af07fb79b514cf"
    assert _combined([PKG / "RESULTS.md", PKG / "RESULTS_HARDENING.md"]) == "147f1d0125e3f3cfaca13accab3bed148c6cfa12ebba153ee2240e97bd967e47"


def test_role_2_inputs_ground_truth_and_results_are_unmodified() -> None:
    assert _combined([PKG / "inputs" / "role2_jd.txt", PKG / "inputs" / "role2_recruiter_brief.txt", PKG / "ROLE2_GROUND_TRUTH.md"]) == \
        "90de6c0126b23ecf9fbd9b66136b03337a0f14ff8e78eaf3983605ede963521a"
    results = [*(PKG / "results" / "role2").glob("*"), PKG / "results" / "role2_analysis.json"]
    assert len(results) == 7 and _combined(results) == "49e5a871c02083b820965cc818138038df5d880a2e29b585b696c2aee4f4cbad"


def test_role_1_evaluation_reproduces_its_committed_table() -> None:
    result = compare_arms.compare(PKG / "results")
    committed = json.loads((PKG / "results" / "comparison.json").read_text(encoding="utf-8"))
    assert json.loads(json.dumps(result["table"])) == committed["table"]


def test_role_2_evaluation_reproduces_its_committed_table() -> None:
    result = compare_role2.analyse(PKG / "results" / "role2")
    committed = json.loads((PKG / "results" / "role2_analysis.json").read_text(encoding="utf-8"))
    assert json.loads(json.dumps(result["table"])) == committed["table"]
    gaps = gold_role2.schema_gaps()         # Role 2's gaps are recorded as they stood DURING Role 2; the live schema has since closed them
    assert gaps["advanced_proficiency"]["representable"] is False and gaps["hybrid_work_mode"]["representable"] is False
    assert "advanced" in schema.PROFICIENCIES and "hybrid" in schema.WORK_MODES


def test_the_frozen_validate_path_does_not_know_the_new_checks() -> None:
    intent = ExperimentalHiringIntent.model_validate(base(role_family=["Software Engineer", "Solution Architect", "Forward Deployed Engineer"],
                                                          skills=[{"name": "React", "proficiency": "hands_on", "relationship": "current", "basis": b("jd", L_UI)}]))
    frozen = validate(intent, JD2, BRIEF2)
    assert not (set(frozen["errors"]) & CROSS_ROLE_ERROR_CODES) and not (CROSS_ROLE_ERROR_CODES & {d["code"] for d in frozen["diagnostics"]})
    assert CROSS_ROLE_ERROR_CODES <= set(validate_cross_role(intent, JD2, BRIEF2)["errors"]) | {"responsibility_only_required", "work_mode_unsupported"}
    assert gold_experimental.evaluate  # Role 1's evaluator still imports the frozen validate()


def test_every_stored_intent_from_every_earlier_arm_validates_against_the_extended_schema() -> None:
    seen = 0
    for sub, pattern in (("experimental", "experimental_run*.json"), ("experimental_v3", "experimental_run*.json"), ("role2", "role2_run*.json")):
        for path in sorted((PKG / "results" / sub).glob(pattern)):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("intent"):
                ExperimentalHiringIntent.model_validate(record["intent"])
                seen += 1
    assert seen == 15
    for path in sorted((PKG / "results" / "baseline").glob("baseline_run*.json")):          # production-shaped intents too
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("intent"):
            StructuredHiringIntent.model_validate(record["intent"])
            ExperimentalHiringIntent.model_validate(record["intent"])


def test_the_production_structured_hiring_intent_is_untouched_and_legacy_json_stays_valid() -> None:
    assert set(StructuredHiringIntent.model_fields) == {
        "role_archetype", "role_family", "seniority", "skills", "skill_any_of", "companies", "company_scale", "education", "experience",
        "location", "exclusions", "evidence_signals"}
    assert "proficiency" not in StructuredHiringIntent.model_json_schema()["$defs"]["SkillReq"]["properties"]
    assert not {"work_mode", "countries", "remote"} & set(StructuredHiringIntent.model_json_schema()["$defs"]["LocationReq"]["properties"])
    legacy = {"role_archetype": {"value": "hybrid", "confidence": 0.7, "rationale": "x"}, "role_family": ["Data Analyst"],
              "skills": [{"name": "SQL"}], "location": {"entries": ["Hyderabad, Telangana, India"], "strength": "required"}}
    assert StructuredHiringIntent.model_validate(legacy) and ExperimentalHiringIntent.model_validate(legacy)
    for path in (REPO / "backend").rglob("*.py"):
        if "experiments" not in path.parts:
            assert "experiments.intake_strategy" not in path.read_text(encoding="utf-8"), path
