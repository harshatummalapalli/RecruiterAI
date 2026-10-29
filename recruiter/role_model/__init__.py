"""The canonical role spine. Import everything from here."""

from recruiter.role_model.model import (
    CapabilityGroup,
    CompanyRules,
    Location,
    Requirement,
    RoleModel,
    TIERS,
    WHEN,
)
from recruiter.role_model.provenance import (
    BACKSTOP,
    INFERRED,
    JD,
    RECRUITER,
    Provenance,
)
from recruiter.role_model.seniority import Seniority, needs_years_clarification
from recruiter.role_model.levels import (
    ARCHITECT,
    DIRECTOR_PLUS,
    IC,
    MANAGER,
    candidate_role_level,
    classify_role_level,
    default_title_exclusions,
    level_note,
    role_suppresses_default_exclusions,
)

__all__ = [
    # spine
    "RoleModel", "Requirement", "CapabilityGroup", "Location", "CompanyRules", "TIERS", "WHEN",
    # seniority (years)
    "Seniority", "needs_years_clarification",
    # levels (flag + exclusions, non-gating)
    "classify_role_level", "candidate_role_level", "level_note",
    "default_title_exclusions", "role_suppresses_default_exclusions",
    "IC", "ARCHITECT", "MANAGER", "DIRECTOR_PLUS",
    # provenance
    "Provenance", "RECRUITER", "JD", "INFERRED", "BACKSTOP",
]
