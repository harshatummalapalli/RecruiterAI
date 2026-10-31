"""Agent 2 (Briefing) — RoleModel -> CrustData query. The retrieval bugs die here."""

from recruiter.agents.briefing import BriefingAgent
from recruiter.evals import assertions
from recruiter.role_model import (
    ARCHITECT,
    CapabilityGroup,
    IC,
    JD,
    CompanyRules,
    Location,
    Provenance,
    Requirement,
    RoleModel,
    Seniority,
)


def _architect_model() -> RoleModel:
    return RoleModel(
        identity="AI Solutions Architect",
        seniority=Seniority(15, None, Provenance(JD)),
        role_level=ARCHITECT,
        location=Location(countries=("India",), cities=("Hyderabad", "Bengaluru", "Pune"), work_mode="hybrid"),
        requirements=(
            Requirement("AI solution design and deployment", "core", Provenance(JD)),
            Requirement("Java and/or Python", "core", Provenance(JD)),
            Requirement("Cloud (Azure, AWS or GCP)", "core", Provenance(JD)),
            Requirement("RAG and Langchain", "supporting", Provenance(JD)),
        ),
        capability_groups=(CapabilityGroup("AI / ML", ("AI", "ML", "machine learning", "LLM", "RAG"), "AI", "r"),),
        companies=CompanyRules(exclude_current=("Acme",)),
        exclude_titles=(),
        limitations=("Work mode (hybrid) is recorded for context; the search cannot filter candidates by work mode.",),
    )


def test_hard_cities_are_filtered_not_in_nl():
    plan = BriefingAgent().build(_architect_model())
    # Hard cities bind in `filters` (exact mode) and must NOT dilute the NL query.
    assert assertions.cities_are_filtered(plan, ["Hyderabad", "Bengaluru", "Pune"]) is None
    assert assertions.hard_cities_not_in_nl(plan, ["Hyderabad", "Bengaluru", "Pune"]) is None


def test_capability_group_enforced_and_no_garble():
    plan = BriefingAgent().build(_architect_model())
    assert assertions.capability_enforced_as_keyword_group(plan) is None
    assert plan.query.must_have_keyword_groups == (("AI", "ML", "machine learning", "LLM", "RAG"),)
    assert assertions.no_garbled_requirement_echo(plan) is None


def test_years_are_hard_filtered_not_in_nl():
    plan = BriefingAgent().build(_architect_model())
    assert assertions.years_enforced(plan, 15) is None
    assert plan.query.min_years == 15                   # binds in filters (exact mode)
    assert "15+ years" not in plan.query.natural_language   # not diluting the ranking vector


def test_capability_is_woven_into_the_nl_query():
    # The defining capability must appear in the NL text (not only as a headline
    # keyword group), so CrustData's semantic match can recover a headline-miss.
    plan = BriefingAgent().build(_architect_model())
    nl = plan.query.natural_language
    assert "AI / ML" in nl and "RAG" in nl


def test_low_years_are_filtered_but_not_named_in_the_query():
    # A junior bar (2+) is a hard filter but NOT NL noise — everyone clears it.
    model = RoleModel(
        identity="eDiscovery Operations Analyst",
        seniority=Seniority(2, None, Provenance(JD)),
        role_level=IC,
        location=Location(countries=("India",)),
        requirements=(Requirement("eDiscovery operations", "core", Provenance(JD)),),
    )
    plan = BriefingAgent().build(model)
    assert plan.query.min_years == 2                       # still a hard filter
    assert "2+ years" not in plan.query.natural_language   # but not named


def test_work_mode_disclosed_not_filtered():
    plan = BriefingAgent().build(_architect_model())
    assert assertions.work_mode_disclosed_not_filtered(plan) is None


def test_company_exclusion_enforced_and_judge_signals_passed():
    plan = BriefingAgent().build(_architect_model())
    assert plan.query.exclude_current_companies == ("Acme",)
    assert len(plan.judge_signals) == 4


def test_company_include_and_exclude_are_hard_filters():
    from recruiter.role_model import CompanyRules
    model = RoleModel(
        identity="Backend Engineer",
        seniority=Seniority(5, None, Provenance(JD)),
        role_level=IC,
        location=Location(countries=("India",)),
        requirements=(Requirement("Python", "core", Provenance(JD)),),
        companies=CompanyRules(prefer_ever=("Google", "Stripe"), exclude_current=("Epiq",)),
    )
    plan = BriefingAgent().build(model)
    assert plan.query.preferred_companies_ever == ("Google", "Stripe")   # ever worked at
    assert plan.query.exclude_current_companies == ("Epiq",)              # not currently at


def test_full_front_half_intake_then_briefing_golden():
    """notes + boundary -> Intake -> RoleModel -> Briefing -> query, all offline,
    passing both the role-model and the briefing net checks for the golden role."""
    from recruiter.agents.intake import IntakeAgent
    from recruiter.agents.intake.capability_memory import InMemoryCapabilityMemory, LearnedCapability
    from recruiter.agents.intake.capability_proposal import CapabilityProposer
    from recruiter.agents.intake.model import ReadRequirement, Understanding
    from recruiter.evals.fixtures import ai_solutions_architect as fx

    understanding = Understanding(
        identity="AI Solutions Architect", posted_title="AI Solutions Architect", posted_title_source="jd",
        min_years=15, work_mode_in_notes="hybrid",
        requirements=(
            ReadRequirement("AI solution design and deployment", "core"),
            ReadRequirement("Java and/or Python", "core"),
            ReadRequirement("Cloud (Azure, AWS or GCP)", "core"),
            ReadRequirement("RAG and Langchain", "supporting"),
        ),
    )
    proposer = CapabilityProposer(
        InMemoryCapabilityMemory(),
        llm_proposer=lambda *a: LearnedCapability("", "AI / ML", ("AI", "ML", "LLM", "RAG"), "AI"),
    )
    intake = IntakeAgent(reader=lambda n, p=None: understanding, capability_proposer=proposer, org="acme")
    model = intake.run(fx.ROLE.notes, fx.ROLE.boundary).model

    plan = BriefingAgent().build(model)
    cities = ["Hyderabad", "Bengaluru", "Pune"]
    assert assertions.cities_are_filtered(plan, cities) is None
    assert assertions.hard_cities_not_in_nl(plan, cities) is None
    assert assertions.capability_enforced_as_keyword_group(plan) is None
    assert assertions.years_enforced(plan, 15) is None
    assert assertions.work_mode_disclosed_not_filtered(plan) is None
    assert assertions.no_garbled_requirement_echo(plan) is None


def test_ic_role_excludes_execs_in_the_query():
    model = RoleModel(
        identity="Senior Backend Engineer",
        seniority=Seniority(6, None, Provenance(JD)),
        role_level=IC,
        location=Location(countries=("India",), cities=("Pune",), work_mode="onsite"),
        requirements=(Requirement("Python backend services", "core", Provenance(JD)),),
        exclude_titles=("VP", "Head of", "Director"),
    )
    plan = BriefingAgent().build(model)
    assert "VP" in plan.query.exclude_titles
    assert plan.query.must_have_keyword_groups == ()   # no specialization -> broad
