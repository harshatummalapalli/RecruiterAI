"""Temporal requirements (past/current/any) and soft/preferred location — the
two gaps the Epiq role exposed."""

from recruiter.agents.briefing import BriefingAgent, build_nl_query
from recruiter.agents.intake.temporal import infer_when
from recruiter.role_model import (
    ARCHITECT,
    JD,
    Location,
    Provenance,
    Requirement,
    RoleModel,
    Seniority,
)

NOTES = (
    "AI Architect who came from a Java development background but right now working on "
    "Agentic Systems, strong experience with Python."
)


def test_infer_when_reads_tense_from_notes():
    assert infer_when(NOTES, "Java Development") == "past"
    assert infer_when(NOTES, "Agentic Systems") == "current"
    assert infer_when(NOTES, "Python") == "any"
    assert infer_when(NOTES, "Kubernetes") == "any"   # not mentioned -> any


def _model(requirements, location):
    return RoleModel(
        identity="AI Architect",
        seniority=Seniority(12, None, Provenance(JD)),
        role_level=ARCHITECT,
        location=location,
        requirements=requirements,
    )


def test_past_requirement_is_background_not_a_demand():
    model = _model(
        (
            Requirement("Agentic Systems", "core", Provenance(JD), when="current"),
            Requirement("Python", "core", Provenance(JD), when="any"),
            Requirement("Java Development", "core", Provenance(JD), when="past"),
        ),
        Location(countries=("India",), cities=("Hyderabad",)),
    )
    nl = build_nl_query(model)
    assert "with experience in Agentic Systems, Python" in nl
    assert "with a background in Java Development" in nl     # past phrased softly
    # Past requirement is never forced into the hard keyword group.
    plan = BriefingAgent().build(model)
    assert plan.query.must_have_keyword_groups == ()


def test_preferred_cities_are_soft_not_a_hard_filter():
    model = _model(
        (Requirement("Agentic Systems", "core", Provenance(JD), when="current"),),
        Location(countries=("India",), preferred_cities=("Hyderabad", "Bengaluru", "Pune")),
    )
    plan = BriefingAgent().build(model)
    nl = plan.query.natural_language
    # Named in the query for a boost...
    assert "based in India, preferably Hyderabad, Bengaluru or Pune" in nl
    # ...but NOT hard-filtered (so any-India candidates aren't excluded).
    assert plan.query.cities == ()
    assert plan.query.countries == ("India",)
