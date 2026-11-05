"""Agent 3 (Calibration) — intent validation (no query internals), apply answers, authorize."""

from recruiter.agents.briefing import BriefingAgent
from recruiter.agents.calibration import CalibrationAgent
from recruiter.agents.intake.model import Question
from recruiter.agents.intake.question_planner import plan_refinements
from recruiter.agents.intake.model import ReadRequirement, Understanding
from recruiter.role_model import (
    ARCHITECT,
    CapabilityGroup,
    JD,
    CompanyRules,
    Location,
    Provenance,
    Requirement,
    RoleModel,
    Seniority,
)


def _model():
    return RoleModel(
        identity="AI Architect",
        seniority=Seniority(12, None, Provenance(JD)),
        role_level=ARCHITECT,
        location=Location(countries=("India",), preferred_cities=("Hyderabad", "Bengaluru", "Pune"), work_mode="remote"),
        requirements=(
            Requirement("Agentic Systems", "core", Provenance(JD), when="current"),
            Requirement("Python", "core", Provenance(JD), when="current"),
            Requirement("Java", "core", Provenance(JD), when="past"),
        ),
        capability_groups=(CapabilityGroup("Agentic AI", ("agentic", "LLM", "RAG"), "AI", "r"),),
        companies=CompanyRules(exclude_current=("Epiq",)),
        limitations=("Work mode (remote) is recorded for context; the search cannot filter candidates by work mode.",),
    )


def test_recruiter_review_is_plain_and_hides_query_internals():
    model = _model()
    plan = BriefingAgent().build(model)
    pkg = CalibrationAgent().review(model, plan, ())
    labels = {ln.label for ln in pkg.summary}
    assert {"Role", "Experience", "Location", "Must have now", "Background (nice, not required)"} <= labels
    blob = " ".join(f"{ln.label} {ln.value}" for ln in pkg.summary).lower()
    # No plumbing leaks into the recruiter view.
    for forbidden in ("keyword", "must_have", "filter", "geo_distance", "natural_language", "query"):
        assert forbidden not in blob
    # The soft-location preference reads plainly.
    assert "preferring hyderabad" in blob
    # Honest limit carried through.
    assert any("work mode" in lim.lower() for lim in pkg.limits)


def test_dealbreakers_mark_requirements_hard():
    out = CalibrationAgent().authorize(_model(), {"dealbreakers": ["Agentic Systems", "Python"]})
    assert out.authorized
    hard = {r.text for r in out.model.requirements if r.hard}
    assert hard == {"Agentic Systems", "Python"}


def test_capability_remove_widens():
    out = CalibrationAgent().authorize(_model(), {"capability": "remove"})
    assert out.model.capability_groups == ()


def test_specialization_answer_adds_a_soft_core_requirement():
    # Thread B2: choosing "Backend" narrows ranking/judging, not a hard keyword gate.
    out = CalibrationAgent().authorize(_model(), {"specialization": "Backend"})
    backend = next((r for r in out.model.requirements if r.text == "Backend"), None)
    assert backend is not None and backend.tier == "core" and backend.hard is False
    assert out.model.capability_groups == _model().capability_groups  # untouched; no hard filter forced


def test_stack_answer_adds_a_precise_capability_group():
    # Thread B-depth2: a chosen language IS a precise hard keyword filter.
    out = CalibrationAgent().authorize(_model(), {"stack": "Java"})
    java = next((g for g in out.model.capability_groups if g.label == "Java"), None)
    assert java is not None and "java" in java.terms


def test_any_stack_answer_filters_nothing():
    out = CalibrationAgent().authorize(_model(), {"stack": "Any stack is fine"})
    assert out.model.capability_groups == _model().capability_groups  # unchanged


def test_track_tighten_excludes_off_track_titles():
    # C1: _model() is an ARCHITECT (IC-technical) role -> tightening drops people-managers.
    out = CalibrationAgent().authorize(_model(), {"track": "Tighten to this track"})
    assert "Manager" in out.model.exclude_titles and "Director" in out.model.exclude_titles


def test_track_keep_as_is_changes_nothing():
    out = CalibrationAgent().authorize(_model(), {"track": "Keep as-is"})
    assert out.model.exclude_titles == _model().exclude_titles


def test_retier_moves_requirements_between_tiers():
    # Option A: the recruiter overrides the reader's tier guess on the brief.
    out = CalibrationAgent().authorize(_model(), {"retier": {"Java": "differentiator", "Python": "supporting"}})
    tiers = {r.text: r.tier for r in out.model.requirements}
    assert tiers["Java"] == "differentiator" and tiers["Python"] == "supporting"
    assert tiers["Agentic Systems"] == "core"  # untouched


def test_retier_then_priority_sees_the_new_cores():
    # retier is applied before priority, so a requirement promoted to Core can be ranked.
    out = CalibrationAgent().authorize(
        _model(), {"retier": {"Java": "supporting"}, "priority": ["Python", "Agentic Systems"]})
    core_order = [r.text for r in out.model.requirements if r.tier == "core"]
    assert core_order == ["Python", "Agentic Systems"]  # Java left Core


def test_retier_ignores_unknown_tiers():
    out = CalibrationAgent().authorize(_model(), {"retier": {"Python": "bogus"}})
    assert {r.text: r.tier for r in out.model.requirements}["Python"] == "core"  # unchanged


def test_priority_reorders_cores():
    out = CalibrationAgent().authorize(_model(), {"priority": ["Python", "Agentic Systems", "Java"]})
    core_order = [r.text for r in out.model.requirements if r.tier == "core"]
    assert core_order == ["Python", "Agentic Systems", "Java"]


def test_domain_required_adds_industry_filter():
    q = Question(id="domain", prompt="Is fintech…", kind="choice", routing="filter",
                 options=("required", "preferred", "irrelevant"), payload="fintech")
    out = CalibrationAgent().authorize(_model(), {"domain": "required"}, (q,))
    assert "fintech" in out.model.industries


def test_disqualifiers_recorded_for_the_judge():
    out = CalibrationAgent().authorize(_model(), {"disqualifiers": "agency-only; research-only"})
    assert out.model.disqualifiers == ("agency-only; research-only",)


def test_confirm_level_no_blocks_authorization():
    out = CalibrationAgent().authorize(_model(), {"confirm_level": "no"})
    assert not out.authorized and "correct the role" in out.blocked_reason


def test_admin_view_exposes_the_query():
    plan = BriefingAgent().build(_model())
    view = CalibrationAgent().admin_query(plan)
    assert "natural_language" in view and "disclosures" in view and "judge_verifies" in view
