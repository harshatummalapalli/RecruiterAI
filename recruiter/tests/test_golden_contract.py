"""The net, proven both ways: a correct RoleModel for the golden role passes
every check, and the legacy-shaped broken model is caught.

This is the contract the Intake agent must satisfy once built: feed it the
fixture's notes+boundary and the resulting RoleModel must pass check_role_model.
"""

from recruiter.evals import assertions
from recruiter.evals.fixtures import ai_solutions_architect as fx
from recruiter.role_model import (
    ARCHITECT,
    CapabilityGroup,
    IC,
    JD,
    Location,
    Provenance,
    RECRUITER,
    Requirement,
    RoleModel,
    Seniority,
)


def _good_model() -> RoleModel:
    """What a correct Intake agent should produce for the golden role: years are
    the gate (15), the role reads as architect so exec titles are NOT excluded,
    all three cities survive, the AI capability is enforced, hybrid disclosed."""
    return RoleModel(
        identity="AI Solutions Architect",
        seniority=Seniority(15, None, Provenance(JD, "15+ years")),
        role_level=ARCHITECT,
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
        exclude_titles=(),  # architect role -> no default exec exclusions
        limitations=("Work mode (hybrid) is recorded but the search cannot filter on it.",),
    )


def test_golden_role_model_passes_all_checks():
    failures = assertions.check_role_model(_good_model(), fx.ROLE.expect)
    assert failures == [], failures


def test_net_catches_the_legacy_failures():
    # Reproduce the legacy output: years missing, role treated as plain IC so exec
    # titles are excluded, collapsed to one city, capability lost, work mode dropped.
    broken = RoleModel(
        identity="AI Solutions Architect",
        seniority=Seniority(None, None, Provenance(RECRUITER)),
        role_level=IC,
        location=Location(countries=("India",), cities=("Hyderabad",), work_mode="hybrid"),
        requirements=(Requirement("AI", "core", Provenance(JD)),),
        capability_groups=(),
        exclude_titles=("VP", "Head of", "Director"),
        limitations=(),
    )
    joined = " | ".join(assertions.check_role_model(broken, fx.ROLE.expect))
    assert "cities dropped" in joined
    assert "min_years" in joined
    assert "role_level" in joined
    assert "exec/leadership" in joined
    assert "capability" in joined
    assert "work_mode" in joined


def test_all_golden_roles_load():
    from recruiter.evals.golden import all_roles

    roles = all_roles()
    assert roles and all(r.notes and r.boundary for r in roles)
