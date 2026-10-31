"""RoleModel JSON round-trip — persistence must return the model byte-for-byte."""

import json

from recruiter.role_model import (
    ARCHITECT,
    JD,
    RECRUITER,
    CapabilityGroup,
    CompanyRules,
    Location,
    Provenance,
    Requirement,
    RoleModel,
    Seniority,
)
from recruiter.role_model.serde import from_dict, to_dict


def _rich_model() -> RoleModel:
    return RoleModel(
        identity="eDiscovery Operations Analyst",
        seniority=Seniority(8, 12, Provenance(RECRUITER, "8-12 yrs")),
        role_level=ARCHITECT,
        location=Location(countries=("India",), states=("Karnataka",), cities=("Bengaluru", "Pune"),
                          preferred_cities=("Hyderabad",), radius_place="San Francisco, California",
                          radius_miles=25.0, work_mode="hybrid"),
        requirements=(
            Requirement("eDiscovery operations", "core", Provenance(JD, "EDRM"), hard=True, when="current"),
            Requirement("Java background", "core", Provenance(JD), when="past"),
        ),
        capability_groups=(CapabilityGroup("eDiscovery", ("Relativity", "Nuix", "EDRM"), "eDiscovery", "because"),),
        companies=CompanyRules(exclude_current=("Epiq",), prefer_ever=("KLDiscovery", "Consilio")),
        exclude_titles=("VP", "Director"),
        industries=("Legal Services",),
        disqualifiers=("agency-only",),
        posted_title="Operations Analyst – eDiscovery",
        posted_title_source="jd",
        employment_type="full-time",
        hiring_company="Epiq",
        limitations=("work mode not filterable",),
        model_id="abc123",
    )


def test_role_model_round_trips_through_json():
    model = _rich_model()
    # to_dict -> json (the exact SearchStore write) -> json -> from_dict
    restored = from_dict(json.loads(json.dumps(to_dict(model), default=str)))
    assert restored == model


def test_minimal_model_round_trips():
    model = RoleModel(identity="Engineer", seniority=Seniority(2, None, Provenance(JD)),
                      role_level="ic", location=Location(countries=("India",)))
    assert from_dict(json.loads(json.dumps(to_dict(model), default=str))) == model
