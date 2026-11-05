"""Structured refine deltas -> a new immutable RoleModel. Pure, no free text."""

from recruiter.agents.calibration.refine import refine_model
from recruiter.role_model import (
    ARCHITECT, JD, CompanyRules, Location, Provenance, Requirement, RoleModel, Seniority,
)


def _model():
    return RoleModel(
        identity="AI Architect",
        seniority=Seniority(12, None, Provenance(JD)),
        role_level=ARCHITECT,
        location=Location(countries=("India",), cities=("Hyderabad",)),
        requirements=(
            Requirement("Agentic Systems", "core", Provenance(JD)),
            Requirement("Python", "supporting", Provenance(JD)),
        ),
        companies=CompanyRules(exclude_current=("Epiq",)),
        exclude_titles=("VP",),
    )


def test_years_change_is_recruiter_authored():
    out = refine_model(_model(), {"min_years": 8, "max_years": 15})
    assert out.seniority.min_years == 8 and out.seniority.max_years == 15
    assert out.seniority.provenance.source == "recruiter"


def test_location_cascade_and_work_mode():
    out = refine_model(_model(), {"location": {"cities": ["Hyderabad", "Pune"], "states": ["Telangana"]},
                                  "work_mode": "hybrid"})
    assert out.location.cities == ("Hyderabad", "Pune") and out.location.states == ("Telangana",)
    assert out.location.work_mode == "hybrid"
    assert out.location.countries == ("India",)       # untouched fields preserved


def test_company_and_title_excludes_merge_without_dupes():
    out = refine_model(_model(), {"exclude_companies_current": ["Epiq", "Relativity"],
                                  "exclude_companies_ever": ["KPMG"], "exclude_titles": ["VP", "Director"]})
    assert out.companies.exclude_current == ("Epiq", "Relativity")   # Epiq not duplicated
    assert out.companies.exclude_ever == ("KPMG",)
    assert out.exclude_titles == ("VP", "Director")


def test_only_companies_become_preferred():
    out = refine_model(_model(), {"only_companies": ["Google", "OpenAI"]})
    assert out.companies.prefer_ever == ("Google", "OpenAI")


def test_retier_and_add_requirement_from_suggestions():
    out = refine_model(_model(), {
        "retier": {"Python": "core"},
        "add_requirements": [{"text": "RAG", "tier": "core", "hard": True}],
    })
    by_text = {r.text: r for r in out.requirements}
    assert by_text["Python"].tier == "core"
    assert by_text["RAG"].tier == "core" and by_text["RAG"].hard is True
    assert by_text["RAG"].provenance.source == "recruiter"


def test_when_tense_updates_an_existing_requirement():
    out = refine_model(_model(), {"when": {"Python": "past"}})
    assert next(r for r in out.requirements if r.text == "Python").when == "past"


def test_refine_is_pure_no_mutation():
    model = _model()
    refine_model(model, {"min_years": 3, "exclude_titles": ["Manager"]})
    assert model.seniority.min_years == 12 and model.exclude_titles == ("VP",)
