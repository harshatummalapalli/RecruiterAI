"""Legacy hard-filter parity: radius, remote-scope geography, employment_type."""

from recruiter.agents.briefing import BriefingAgent
from recruiter.agents.intake.assemble import _location
from recruiter.role_model import (
    ARCHITECT,
    JD,
    Location,
    Provenance,
    Requirement,
    RoleModel,
    Seniority,
)


def _model(location, employment_type=None):
    return RoleModel(
        identity="Engineer",
        seniority=Seniority(6, None, Provenance(JD)),
        role_level=ARCHITECT,
        location=location,
        requirements=(Requirement("Python", "core", Provenance(JD)),),
        employment_type=employment_type,
    )


# --- remote scope ------------------------------------------------------------

def test_remote_anywhere_is_country_only():
    loc = _location({"country": "India", "work_mode": "remote"})
    assert loc.countries == ("India",) and loc.cities == () and loc.states == ()


def test_remote_scoped_to_states_filters_states():
    loc = _location({"country": "USA", "work_mode": "remote", "remote_scope": "states",
                     "remote_states": ["California", "Texas"]})
    assert loc.states == ("California", "Texas") and loc.cities == ()


def test_remote_scoped_to_cities_filters_cities():
    loc = _location({"country": "India", "work_mode": "remote", "remote_scope": "cities",
                     "remote_cities": ["Mumbai", "Delhi"]})
    assert loc.cities == ("Mumbai", "Delhi")


# --- radius ------------------------------------------------------------------

def test_radius_flows_into_the_query():
    loc = _location({"country": "USA", "work_mode": "onsite", "city": "Austin",
                     "state": "Texas", "radius_miles": 25})
    assert loc.radius_place == "Austin, Texas" and loc.radius_miles == 25
    plan = BriefingAgent().build(_model(loc))
    assert plan.query.radius_place == "Austin, Texas" and plan.query.radius_miles == 25


# --- employment type ---------------------------------------------------------

def test_valid_employment_type_enforced():
    plan = BriefingAgent().build(_model(Location(countries=("India",)), employment_type="Full-time"))
    assert plan.query.employment_type == "full-time"


def test_invalid_employment_type_disclosed_not_filtered():
    plan = BriefingAgent().build(_model(Location(countries=("India",)), employment_type="Permanent"))
    assert plan.query.employment_type is None
    assert any("permanent" in d.lower() for d in plan.disclosures)
