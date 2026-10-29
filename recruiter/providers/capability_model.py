"""CrustData capability model — the code-owned source of truth for what can
be enforced, read back, and trusted. Migrated from the legacy
`crustdata_capabilities` (seeded from live probes 2026-10-01).

Three axes per field:
  filter_status    verified | unverified | unavailable  (can we constrain on it?)
  response_status  returned | gated                     (can we read it back?)
  data_confidence  high | unknown                        (is the data complete?)

Routing (what a recruiter signal of a given strength becomes):
  unavailable/unverified -> 'judge' if downstream-verifiable else 'disclose'
  verified + preferred   -> 'context_or_evidence' (no verified boost mechanism)
  verified + required:
      high confidence              -> 'enforce'
      unknown + gated response     -> 'enforce_but_not_verifiable'
      unknown + returned response  -> 'enforce_with_warning'
Both Intake (what to ask) and Briefing (what to enforce) read this.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

VERSION = "v1-2026-10-01"

# CrustData's person_search employment_type vocabulary (live-confirmed). An
# unvalidated value silently returns zero rows, so only a value in this set is
# ever enforced; anything else is disclosed instead.
SUPPORTED_EMPLOYMENT_TYPES = frozenset({"full-time", "part-time", "internship", "contract", "self-employed"})


def normalize_employment_type(value):
    if not value:
        return None
    norm = value.strip().lower().replace(" ", "-")
    return norm if norm in SUPPORTED_EMPLOYMENT_TYPES else None


VERIFIED, UNVERIFIED, UNAVAILABLE = "verified", "unverified", "unavailable"
RETURNED, GATED = "returned", "gated"
HIGH, UNKNOWN = "high", "unknown"

# Routing tokens.
ENFORCE = "enforce"
ENFORCE_WITH_WARNING = "enforce_with_warning"
ENFORCE_NOT_VERIFIABLE = "enforce_but_not_verifiable"
CONTEXT = "context_or_evidence"
JUDGE = "judge"
DISCLOSE = "disclose"


@dataclass(frozen=True)
class FieldCapability:
    field: str
    filter_status: str
    response_status: str
    data_confidence: str
    downstream_verifiable: bool
    note: str = ""


def _c(field, fs, rs, dc, dv, note=""):
    return FieldCapability(field, fs, rs, dc, dv, note)


_MAP: Dict[str, FieldCapability] = {c.field: c for c in [
    _c("experience.employment_details.current.company_name", VERIFIED, RETURNED, HIGH, True),
    _c("experience.employment_details.company_name", VERIFIED, RETURNED, UNKNOWN, True, "any-time; skews to past employees"),
    _c("experience.employment_details.past.company_name", VERIFIED, RETURNED, HIGH, True),
    _c("experience.employment_details.current.title", VERIFIED, RETURNED, HIGH, True),
    _c("experience.employment_details.past.title", VERIFIED, RETURNED, HIGH, True),
    _c("experience.employment_details.current.description", VERIFIED, GATED, UNKNOWN, True, "filterable, not returned; OR with headline"),
    _c("basic_profile.headline", VERIFIED, RETURNED, HIGH, True, "populated; main skill-bearing field at retrieval"),
    _c("basic_profile.summary", VERIFIED, GATED, UNKNOWN, True),
    _c("experience.employment_details.current.employment_type", VERIFIED, RETURNED, UNKNOWN, False, "fixed vocabulary only"),
    _c("years_of_experience_raw", VERIFIED, RETURNED, HIGH, True),
    _c("basic_profile.location.country", VERIFIED, RETURNED, HIGH, True),
    _c("basic_profile.location.state", VERIFIED, RETURNED, HIGH, True),
    _c("basic_profile.location.city", VERIFIED, RETURNED, HIGH, True),
    _c("basic_profile.location", VERIFIED, RETURNED, HIGH, True, "geo_distance"),
    _c("experience.employment_details.current.company_headcount_latest", VERIFIED, RETURNED, UNKNOWN, False, "not in profile text; judge can't re-verify"),
    _c("education.schools.degree", VERIFIED, RETURNED, UNKNOWN, True),
    _c("education.schools.field_of_study", VERIFIED, GATED, UNKNOWN, True, "returned blank; verify via Harvest"),
    _c("company_industries", VERIFIED, RETURNED, UNKNOWN, True, "industry classification; career-signals can judge"),
    _c("skills.professional_network_skills", UNAVAILABLE, GATED, UNKNOWN, True, "skills-list filter unavailable on our plan"),
    _c("work_mode", UNAVAILABLE, GATED, UNKNOWN, False, "no work_mode filter on person_search -> disclose"),
]}


def get(field: str) -> FieldCapability:
    return _MAP.get(field, _c(field, UNVERIFIED, GATED, UNKNOWN, False, "not in capability map -> unverified"))


def can_hard_filter(field: str) -> Tuple[bool, Optional[str]]:
    cap = get(field)
    if cap.filter_status != VERIFIED:
        return False, None
    if cap.data_confidence == UNKNOWN:
        return True, f"{field}: filter verified but data completeness unestablished"
    return True, None


def is_displayable(field: str) -> bool:
    return get(field).response_status == RETURNED


def recommend_routing(field: str, strength: str) -> str:
    """(field, 'required'|'preferred') -> a routing token. Nothing unverified is
    ever silently hard-filtered."""
    cap = get(field)
    if cap.filter_status in (UNAVAILABLE, UNVERIFIED):
        return JUDGE if cap.downstream_verifiable else DISCLOSE
    if strength == "preferred":
        return CONTEXT  # no verified provider-side boost mechanism exists
    if cap.data_confidence == HIGH:
        return ENFORCE
    if cap.response_status == GATED:
        return ENFORCE_NOT_VERIFIABLE
    return ENFORCE_WITH_WARNING


# Recruiter-intent filter name -> the one CrustData field it compiles to.
FILTER_FIELD_MAP: Dict[str, str] = {
    "include_titles": "experience.employment_details.current.title",
    "exclude_titles": "experience.employment_details.current.title",
    "countries": "basic_profile.location.country",
    "states": "basic_profile.location.state",
    "cities": "basic_profile.location.city",
    "radius_place": "basic_profile.location",
    "radius_miles": "basic_profile.location",
    "employment_type": "experience.employment_details.current.employment_type",
    "minimum_years": "years_of_experience_raw",
    "maximum_years": "years_of_experience_raw",
    "preferred_companies": "experience.employment_details.current.company_name",
    "exclude_current_companies": "experience.employment_details.current.company_name",
    "preferred_companies_ever": "experience.employment_details.company_name",
    "exclude_companies_ever": "experience.employment_details.company_name",
    "industries": "company_industries",
    # Recorded but unenforceable — mapped so routing resolves to 'disclose'
    # (not the unknown-field default), never appearing in supported_filters().
    "work_mode": "work_mode",
    "must_have_keywords": "basic_profile.headline",
    "must_have_keyword_groups": "basic_profile.headline",
}


def supported_filters() -> List[str]:
    """SearchQuery filter names the model says are genuinely hard-filterable."""
    return [name for name, field in FILTER_FIELD_MAP.items() if can_hard_filter(field)[0]]


def route_filter(filter_name: str, strength: str = "required") -> str:
    """Routing for a recruiter-intent filter name (not a raw field)."""
    field = FILTER_FIELD_MAP.get(filter_name)
    if field is None:
        return JUDGE
    return recommend_routing(field, strength)
