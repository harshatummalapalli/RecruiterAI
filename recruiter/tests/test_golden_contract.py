"""The net, proven both ways: a correct RoleModel for the golden role passes
every check, and the legacy-style broken model (senior + one city) is caught.

This is the contract the Intake agent must satisfy once it is built: feed it the
fixture's notes+boundary and the resulting RoleModel must pass check_role_model.
"""

from recruiter.evals import assertions
from recruiter.evals.fixtures import ai_solutions_architect as fx
from recruiter.role_model import (
    CapabilityGroup,
    JD,
    Location,
    Provenance,
    RECRUITER,
    Requirement,
    RoleModel,
    Seniority,
)


def _good_model() -> RoleModel:
    """What a correct Intake agent should produce for the golden role."""
    return RoleModel(
        identity="AI Solutions Architect",
        seniority=Seniority("senior", 15, None, Provenance(JD, "15+ years")),
        location=Location(
            countries=("India",),
            cities=("Hyderabad", "Bengaluru", "Pune"),
            work_mode="hybrid",
        ),
        requirements=(
            Requirement("AI solution design and deployment", "core", Provenance(JD), hard=True),
            Requirement("Java and/or Python", "core", Provenance(JD)),
            Requirement("Cloud (Azure, AWS or GCP)", "core", Provenance(JD)),
            Requirement("RAG and Langchain", "supporting", Provenance(JD)),
            Requirement("Azure preferred", "differentiator", Provenance(JD)),
        ),
        capability_groups=(
            CapabilityGroup("AI / ML", ("AI", "ML", "machine learning", "LLM", "RAG"), "AI", "role-defining"),
        ),
        limitations=("Work mode (hybrid) is recorded but the search cannot filter on it.",),
    )


def test_golden_role_model_passes_all_checks():
    failures = assertions.check_role_model(_good_model(), fx.ROLE.expect)
    assert failures == [], failures


def test_net_catches_the_legacy_failures():
    # Reproduce the legacy output: scoped "senior", collapsed to one city.
    broken = RoleModel(
        identity="AI Solutions Architect",
        seniority=Seniority("senior", None, None, Provenance(RECRUITER)),  # no years -> stays senior
        location=Location(countries=("India",), cities=("Hyderabad",), work_mode="hybrid"),
        requirements=(Requirement("AI", "core", Provenance(JD)),),
        capability_groups=(),               # role-defining capability lost
        limitations=(),                     # work mode silently dropped
    )
    failures = assertions.check_role_model(broken, fx.ROLE.expect)
    # It must flag: missing cities, under-scoped seniority, lost capability, undisclosed work mode.
    joined = " | ".join(failures)
    assert "cities dropped" in joined
    assert "under-scoped" in joined
    assert "AI" in joined
    assert "work_mode" in joined


def test_all_golden_roles_load():
    from recruiter.evals.golden import all_roles

    roles = all_roles()
    assert roles and all(r.notes and r.boundary for r in roles)
