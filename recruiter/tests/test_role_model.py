"""Unit tests for the RoleModel spine — the seniority floor (the live bug),
ladder ranking, and model helpers."""

import pytest

from recruiter.role_model import (
    BACKSTOP,
    CapabilityGroup,
    JD,
    Location,
    Provenance,
    RECRUITER,
    Requirement,
    RoleModel,
    Seniority,
    floor_from_years,
    normalise_label,
    rank_of,
)


def _prov():
    return Provenance(source=RECRUITER)


@pytest.mark.parametrize(
    "years,expected",
    [(None, None), (0, None), (2, "junior"), (4, "mid"), (7, "senior"),
     (12, "staff/lead"), (15, "principal"), (25, "principal")],
)
def test_floor_from_years(years, expected):
    assert floor_from_years(years) == expected


def test_effective_lifts_mis_stated_low_label():
    # The live bug: "senior" stated on a 15+ role. Effective must not stay senior.
    sen = Seniority(stated_label="senior", min_years=15, max_years=None, provenance=_prov())
    assert sen.derived_floor == "principal"
    assert sen.effective == "principal"
    assert rank_of(sen.effective) > rank_of("senior")


def test_effective_keeps_higher_stated_label():
    # A stated label above the years-floor is respected (years are a floor, not a cap).
    sen = Seniority(stated_label="director", min_years=6, max_years=None, provenance=_prov())
    assert sen.effective == "director"


def test_normalise_label_aliases():
    assert normalise_label("Sr.") == "senior"
    assert normalise_label("Principal Architect") in ("principal", "staff/lead")
    assert normalise_label("VP of Engineering") == "director"
    assert normalise_label("") is None


def test_requirement_rejects_bad_tier():
    with pytest.raises(ValueError):
        Requirement(text="x", tier="nonsense", provenance=_prov())


def test_rolemodel_helpers():
    model = RoleModel(
        identity="AI Solutions Architect",
        seniority=Seniority("senior", 15, None, _prov()),
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


def test_provenance_rejects_unknown_source():
    with pytest.raises(ValueError):
        Provenance(source="made_up")
    assert Provenance(BACKSTOP).is_stated is False
