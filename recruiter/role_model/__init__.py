"""The canonical role spine. Import everything from here."""

from recruiter.role_model.model import (
    CapabilityGroup,
    CompanyRules,
    Location,
    Requirement,
    RoleModel,
    TIERS,
)
from recruiter.role_model.provenance import (
    BACKSTOP,
    INFERRED,
    JD,
    RECRUITER,
    Provenance,
)
from recruiter.role_model.seniority import (
    LADDER,
    Seniority,
    floor_from_years,
    normalise_label,
    rank_of,
)

__all__ = [
    "RoleModel", "Requirement", "CapabilityGroup", "Location", "CompanyRules", "TIERS",
    "Seniority", "floor_from_years", "normalise_label", "rank_of", "LADDER",
    "Provenance", "RECRUITER", "JD", "INFERRED", "BACKSTOP",
]
