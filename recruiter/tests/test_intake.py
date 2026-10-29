"""Agent 1 (Intake) — end to end with injected reader + capability proposer
(no LLM, no credits). Proves the golden role assembles and passes the net, the
years-ask works, role-level exclusions behave, and capability comes from the
(injected) learned proposer rather than a hand-seeded table.
"""

from recruiter.agents.intake import IntakeAgent, Understanding
from recruiter.agents.intake.capability_memory import InMemoryCapabilityMemory, LearnedCapability
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.model import ReadRequirement
from recruiter.evals import assertions
from recruiter.evals.fixtures import ai_solutions_architect as fx


def _ai_llm(identity, posted_title, reqs):
    """Stub LLM proposer: an AI capability for AI roles, broad otherwise."""
    if "ai" in (identity or "").lower().split():
        return LearnedCapability("", "AI / ML", ("AI", "ML", "machine learning", "LLM", "RAG"), "AI")
    return None


def _agent(understanding: Understanding) -> IntakeAgent:
    proposer = CapabilityProposer(InMemoryCapabilityMemory(), llm_proposer=_ai_llm)
    return IntakeAgent(reader=lambda n, p=None: understanding, capability_proposer=proposer, org="acme")


def _architect_understanding() -> Understanding:
    return Understanding(
        identity="AI Solutions Architect",
        posted_title="AI Solutions Architect",
        posted_title_source="jd",
        min_years=15,
        requirements=(
            ReadRequirement("AI solution design and deployment", "core", "built and deployed AI solutions"),
            ReadRequirement("Java and/or Python", "core", "Java and/or Python"),
            ReadRequirement("Cloud (Azure, AWS or GCP)", "core", "Cloud - Azure, AWS or GCP is required"),
            ReadRequirement("RAG and Langchain", "supporting", "especially with RAG, Langchain"),
            ReadRequirement("Azure preferred", "differentiator", "Azure would be preferred"),
        ),
        work_mode_in_notes="hybrid",
    )


def test_golden_role_assembles_and_passes_the_net():
    outcome = _agent(_architect_understanding()).run(fx.ROLE.notes, fx.ROLE.boundary)
    assert outcome.ready, outcome.clarifications
    failures = assertions.check_role_model(outcome.model, fx.ROLE.expect)
    assert failures == [], failures


def test_missing_years_triggers_the_ask_then_resolves():
    u = Understanding(identity="AI Solutions Architect", min_years=None,
                      requirements=(ReadRequirement("AI", "core"),), work_mode_in_notes="hybrid")
    agent = _agent(u)
    blocked = agent.run(fx.ROLE.notes, fx.ROLE.boundary)
    assert not blocked.ready
    assert [q.kind for q in blocked.clarifications] == ["min_years"]

    resolved = agent.run(fx.ROLE.notes, fx.ROLE.boundary, answers={"min_years": 8})
    assert resolved.ready
    assert resolved.model.seniority.min_years == 8
    assert resolved.model.seniority.provenance.source == "recruiter"


def test_architect_role_suppresses_exec_exclusions_and_enforces_capability():
    outcome = _agent(_architect_understanding()).run(fx.ROLE.notes, fx.ROLE.boundary)
    model = outcome.model
    assert model.role_level == "architect"
    assert model.exclude_titles == ()
    assert any("AI" in g.label for g in model.capability_groups)
    # The adaptive planner surfaces the right refinements for a specialised senior role.
    assert "capability" in {q.id for q in outcome.refinements}


def test_ic_role_excludes_execs_and_has_no_capability_group():
    u = Understanding(identity="Senior Backend Engineer", min_years=6,
                      requirements=(ReadRequirement("Python backend services", "core"),))
    outcome = _agent(u).run("Senior Backend Engineer, 6+ years, Python.",
                            {"country": "India", "work_mode": "onsite", "city": "Pune"})
    model = outcome.model
    assert model.role_level == "ic"
    assert "VP" in model.exclude_titles and "Head of" in model.exclude_titles
    assert model.capability_groups == ()
    assert outcome.refinements == ()   # broad single-core IC role -> the planner stays quiet


def test_identity_is_normalized_to_title_shape():
    # Newer models append descriptors; the identity must stay title-shaped so
    # title-relevance scoring works.
    cases = {
        "AI Architect (Agentic Systems, production AI)": "AI Architect",
        "Sales Manager — single-outlet restaurant acquisition": "Sales Manager",
        "Sales Manager, B2B restaurant partner acquisition (field sales)": "Sales Manager",
    }
    for verbose, expected in cases.items():
        u = Understanding(identity=verbose, min_years=5, requirements=(ReadRequirement("x", "core"),))
        model = _agent(u).run("notes", {"country": "India", "work_mode": "onsite", "city": "Pune"}).model
        assert model.identity == expected, (verbose, model.identity)


def test_multi_city_and_hiring_company_exclusion():
    model = _agent(_architect_understanding()).run(fx.ROLE.notes, {**fx.ROLE.boundary, "hiring_company": "Acme"}).model
    assert model.location.cities == ("Hyderabad", "Bengaluru", "Pune")
    assert model.companies.exclude_current == ("Acme",)
