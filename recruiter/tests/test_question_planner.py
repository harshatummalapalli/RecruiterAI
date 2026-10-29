"""The adaptive question planner — different roles get different question sets,
and nothing unenforceable is asked as a filter."""

from recruiter.agents.intake.model import ReadRequirement, Understanding
from recruiter.agents.intake.question_planner import plan_refinements
from recruiter.role_model import CapabilityGroup


def _ids(questions):
    return {q.id for q in questions}


def test_specialised_senior_role_gets_the_rich_set():
    u = Understanding(
        identity="AI Solutions Architect",
        posted_title="AI Solutions Architect",
        requirements=(
            ReadRequirement("AI solution design", "core"),
            ReadRequirement("Java and/or Python", "core"),
            ReadRequirement("Cloud", "core"),
        ),
    )
    groups = (CapabilityGroup("AI / ML", ("AI", "ML", "LLM"), "AI", "r"),)
    ids = _ids(plan_refinements(u, groups))
    assert {"capability", "dealbreakers", "priority", "disqualifiers", "confirm_level"} <= ids


def test_broad_single_core_role_stays_minimal():
    u = Understanding(
        identity="Backend Engineer",
        requirements=(ReadRequirement("Python backend services", "core"),),
    )
    ids = _ids(plan_refinements(u, ()))
    # No specialization, one core, IC level -> no capability/dealbreakers/priority/
    # disqualifiers/confirm. The planner stays quiet.
    assert ids == set()


def test_domain_asked_only_when_present_and_is_a_filter():
    with_domain = Understanding(
        identity="Backend Engineer",
        requirements=(ReadRequirement("Python services for a fintech payments platform", "core"),
                      ReadRequirement("Kafka", "core")),
    )
    qs = plan_refinements(with_domain, ())
    domain_q = next((q for q in qs if q.id == "domain"), None)
    assert domain_q is not None and "fintech" in domain_q.prompt
    assert domain_q.routing == "filter"   # CrustData can filter industry


def test_capability_confirm_is_a_filter_and_offers_remove():
    u = Understanding(identity="Salesforce Developer", requirements=(ReadRequirement("Apex", "core"),))
    groups = (CapabilityGroup("Salesforce", ("Salesforce", "Apex", "SOQL"), "Salesforce", "r"),)
    q = next(q for q in plan_refinements(u, groups) if q.id == "capability")
    assert q.routing == "filter" and "remove" in q.options


def test_disqualifiers_route_to_judge():
    u = Understanding(identity="Engineering Manager", requirements=(ReadRequirement("lead a team", "core"),))
    q = next(q for q in plan_refinements(u, ()) if q.id == "disqualifiers")
    assert q.routing == "judge"
