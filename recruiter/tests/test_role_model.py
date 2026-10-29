"""Unit tests for the RoleModel spine — years-only seniority, role-level
classification, default title exclusions, and the informational level flag."""

import pytest

from recruiter.role_model import (
    ARCHITECT,
    BACKSTOP,
    CapabilityGroup,
    DIRECTOR_PLUS,
    IC,
    JD,
    Location,
    MANAGER,
    Provenance,
    RECRUITER,
    Requirement,
    RoleModel,
    Seniority,
    candidate_role_level,
    classify_role_level,
    default_title_exclusions,
    level_note,
    needs_years_clarification,
    role_suppresses_default_exclusions,
)


def _prov():
    return Provenance(source=RECRUITER)


# --- seniority = years -------------------------------------------------------

def test_seniority_is_years_only():
    sen = Seniority(min_years=15, max_years=None, provenance=_prov())
    assert sen.is_specified
    assert not needs_years_clarification(sen.min_years)


def test_missing_years_triggers_clarification():
    sen = Seniority(min_years=None, max_years=None, provenance=_prov())
    assert not sen.is_specified
    assert needs_years_clarification(sen.min_years)


# --- role-level classification (for flag + exclusions, never gating) ---------

@pytest.mark.parametrize(
    "identity,expected",
    [
        ("AI Solutions Architect", ARCHITECT),
        ("Senior Software Engineer", IC),
        ("Staff Engineer", IC),
        ("Engineering Manager", MANAGER),
        ("Head of Data", DIRECTOR_PLUS),
        ("VP of Engineering", DIRECTOR_PLUS),
        ("Chief Technology Officer", DIRECTOR_PLUS),
    ],
)
def test_classify_role_level(identity, expected):
    assert classify_role_level(identity) == expected


# --- default title exclusions + suppression ---------------------------------

def test_ic_role_default_excludes_execs():
    excl = default_title_exclusions(IC)
    assert "VP" in excl and "Head of" in excl and "Manager" in excl and "Founder" in excl


@pytest.mark.parametrize("level", [ARCHITECT, MANAGER, DIRECTOR_PLUS])
def test_leadership_roles_suppress_default_exclusions(level):
    assert role_suppresses_default_exclusions(level)
    assert default_title_exclusions(level) == ()


def test_ic_role_does_not_suppress():
    assert not role_suppresses_default_exclusions(IC)


# --- the informational level flag -------------------------------------------

def test_level_note_flags_above_and_below():
    # Role is a Senior/Lead IC; an Architect candidate reads ABOVE.
    assert "above" in (level_note("Principal Architect", IC) or "")
    # Role is an Architect; a plain Senior Engineer reads BELOW.
    assert "below" in (level_note("Senior Software Engineer", ARCHITECT) or "")
    # Same band -> no note.
    assert level_note("Senior Software Engineer", IC) is None


def test_candidate_role_level():
    assert candidate_role_level("Director of AI") == DIRECTOR_PLUS


# --- model helpers -----------------------------------------------------------

def test_rolemodel_helpers():
    model = RoleModel(
        identity="AI Solutions Architect",
        seniority=Seniority(15, None, _prov()),
        role_level=ARCHITECT,
        location=Location(countries=("India",), cities=("Hyderabad", "Bengaluru", "Pune"), work_mode="hybrid"),
        requirements=(
            Requirement("AI solution design and deployment", "core", Provenance(JD, "built and deployed AI"), hard=True),
            Requirement("RAG and Langchain", "supporting", Provenance(JD, "especially with RAG")),
        ),
        capability_groups=(CapabilityGroup("AI / ML", ("AI", "ML", "LLM", "RAG"), "AI", "role-defining"),),
        limitations=("Work mode (hybrid) is recorded but not filterable.",),
    )
    assert model.location.is_multi_city
    assert [r.text for r in model.core] == ["AI solution design and deployment"]
    assert len(model.hard_requirements) == 1


def test_requirement_rejects_bad_tier():
    with pytest.raises(ValueError):
        Requirement(text="x", tier="nonsense", provenance=_prov())


def test_provenance_rejects_unknown_source():
    with pytest.raises(ValueError):
        Provenance(source="made_up")
    assert Provenance(BACKSTOP).is_stated is False
