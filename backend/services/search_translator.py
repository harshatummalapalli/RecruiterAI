"""The Search Translator — the ONE place IntakeResult becomes an executable
SearchIntent. Deterministic and code-only: no LLM call happens here, and
none should happen again anywhere downstream of Living Brief confirmation.

    IntakeResult -> ConfirmedHiringIntent -> SearchIntent (existing, unchanged)

This replaces the old build_confirmed_search_intent(), which silently routed
the Living Brief's tiered understanding into a dead field (SearchIntent.
ranking, never read by CandidateRanker or sent to CrustData) and forced a
free-text location sentence into an exact-match city filter. See the
forensic investigation this resolves for the evidence.
"""

import re
from typing import List, Optional

from backend.models.hiring_intent import ConfirmedHiringIntent, StructuredLocation
from backend.models.intake import IntakeResult, LocationEntry, SearchBoundary
from backend.models.search_intent import CompanyPreferences, Experience, Location, Role, SearchIntent, Titles
from backend.providers.crustdata import SUPPORTED_EMPLOYMENT_TYPES
from backend.services.query_expansion import QueryExpansionService

# A candidate_identity this short and free of verb/descriptive-clause
# language is treated as title-shaped; anything longer or phrased as a
# sentence ("Software Engineer focused on Data Platforms") is not sent to a
# title filter — see _normalize_candidate_identity.
# CrustData matches basic_profile.location.state against the full US state
# name, never the two-letter postal abbreviation (confirmed live — an
# abbreviation silently matches zero candidates even though city/country
# match correctly, since all three are ANDed together). Task A is now
# instructed to return the full name, but this deterministic backstop
# guarantees it regardless of what the model actually returns — the same
# "code validates" pattern as the contradiction backstop.
_US_STATE_ABBREVIATIONS = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}


def normalize_state(state: Optional[str]) -> Optional[str]:
    if not state:
        return state
    return _US_STATE_ABBREVIATIONS.get(state.strip().upper(), state)


_MAX_TITLE_WORDS = 6
_DESCRIPTIVE_PHRASE_RE = re.compile(
    r"\b(focused on|responsible for|working on|centered on|specializ\w*|who\b|that\b|building the)\b",
    re.IGNORECASE,
)


def _looks_title_shaped(candidate: str) -> bool:
    text = (candidate or "").strip()
    if not text:
        return False
    if len(text.split()) > _MAX_TITLE_WORDS:
        return False
    if _DESCRIPTIVE_PHRASE_RE.search(text):
        return False
    return True


def normalize_candidate_identity(candidate_identity: Optional[str], posted_title: Optional[str]) -> str:
    """Deterministic validation, never an LLM re-interpretation. Task A's
    candidate_identity is understanding-oriented prose, not contractually
    title-shaped — this is what stops a sentence like "Software Engineer
    focused on Data Platforms" from ever reaching a literal title filter."""
    candidate_identity = (candidate_identity or "").strip()
    if _looks_title_shaped(candidate_identity):
        return candidate_identity

    if posted_title:
        # The posted title's leading segment, before any organization/team
        # suffix (e.g. "Senior Software Engineer, Data Platform, AI Labs" ->
        # "Senior Software Engineer, Data Platform"). Still prefer this over
        # the unshaped identity even if it isn't perfectly title-shaped
        # itself — it is, at minimum, the recruiter's own words.
        core = posted_title.split(",")[0].strip()
        if core:
            return core

    # Last resort: truncate rather than ever send the full descriptive
    # sentence into a title filter.
    words = candidate_identity.split()
    return " ".join(words[:_MAX_TITLE_WORDS])


def _flatten_locations(locations: List[LocationEntry]) -> Location:
    cities: List[str] = []
    states: List[str] = []
    countries: List[str] = []
    for entry in locations:
        if entry.city and entry.city not in cities:
            cities.append(entry.city)
        state = normalize_state(entry.state)
        if state and state not in states:
            states.append(state)
        if entry.country and entry.country not in countries:
            countries.append(entry.country)

    # A radius anchor around the confirmed city — the recruiter can opt into
    # this via the existing Radius Search control (Edit brief) instead of
    # the default exact city/state/country match; only offered when there's
    # a single, unambiguous city to anchor on (a multi-location JD has no
    # one place a radius would mean).
    radius_place = None
    if len(locations) == 1 and locations[0].city:
        radius_place = ", ".join(part for part in [locations[0].city, normalize_state(locations[0].state)] if part)

    return Location(cities=cities, states=states, countries=countries, radius_place=radius_place)


def _validated_employment_type(employment_type: Optional[str]) -> Optional[str]:
    if employment_type and employment_type.strip().lower() in SUPPORTED_EMPLOYMENT_TYPES:
        return employment_type
    return None


def _fallback_natural_language_query(
    candidate_identity: str,
    seniority: Optional[str],
    core_signals: List[str],
    supporting_signals: List[str],
    differentiator_signals: List[str],
) -> str:
    """Only used if Task B somehow returned no query at all (it always
    should) — a deterministic, tier-weighted template, never a mechanical
    concatenation of every JD bullet. Core is emphasized over Supporting over
    Differentiators, capped so this can't grow unbounded."""
    parts: List[str] = []
    role_desc = " ".join(part for part in [seniority, candidate_identity] if part).strip()
    if role_desc:
        parts.append(role_desc)
    if core_signals:
        parts.append(f"with strong experience in {', '.join(core_signals[:5])}")
    if supporting_signals:
        parts.append(f"experience with {', '.join(supporting_signals[:3])} is valuable")
    if differentiator_signals:
        parts.append(f"{', '.join(differentiator_signals[:2])} is a plus but not required")
    return ". ".join(parts)


def _structured_locations_from_boundary(boundary: SearchBoundary) -> List[StructuredLocation]:
    """The recruiter's explicit geographic scope, translated into the same
    StructuredLocation list shape Task A's own extraction already produces
    — _flatten_locations (unchanged) handles all of these identically
    regardless of source."""
    if boundary.work_mode in ("onsite", "hybrid"):
        return [StructuredLocation(city=boundary.city, state=boundary.state, country=boundary.country)]
    # Remote.
    if boundary.remote_scope == "cities" and boundary.remote_cities:
        return [StructuredLocation(city=city, country=boundary.country) for city in boundary.remote_cities]
    if boundary.remote_scope == "states" and boundary.remote_states:
        return [StructuredLocation(state=state, country=boundary.country) for state in boundary.remote_states]
    # "anywhere" (or an unrecognized/empty scope, conservatively treated the
    # same way) — country-level only, no city/state anchor.
    return [StructuredLocation(country=boundary.country)]


def _radius_place_from_boundary(boundary: SearchBoundary) -> Optional[str]:
    if boundary.work_mode not in ("onsite", "hybrid") or not boundary.city:
        return None
    return ", ".join(part for part in [boundary.city, normalize_state(boundary.state)] if part)


_DURATION_MENTION = re.compile(r"\b\d+\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)


def _core_signals_with_duration(
    core: List[str], supporting: List[str], minimum_years: Optional[int]
) -> List[str]:
    """The minimum years is a structured fact the intake already extracted
    (it was 3 in every one of five runs on the same JD), but whether the
    model ALSO wrote it up as a requirement varied (present in 3 of 5 runs).
    A stated minimum must always be a requirement, so add it when no signal
    of any tier already states a duration. Deterministic and never
    role-specific."""
    if not minimum_years or _DURATION_MENTION.search(" ".join(core + supporting)):
        return core
    return [f"{minimum_years}+ years of professional experience", *core]


def build_confirmed_hiring_intent(result: IntakeResult, boundary: Optional[SearchBoundary] = None) -> ConfirmedHiringIntent:
    """Stage 1: IntakeResult -> Confirmed Hiring Intent. Refuses while any
    ask issue is pending — a contradictory or otherwise unresolved intake
    must never silently become an executable search.

    `boundary`, when present, is authoritative for hiring company, location,
    work mode, and radius — the recruiter's own explicit choices from the
    intake form, never re-derived from or overwritten by Task A's JD
    reading (see backend/services/intake_reasoning.py's apply_search_
    boundary, which already reconciled any conflict between the two before
    this point — by the time we get here, the boundary is what the
    recruiter confirmed should be used). Falls back to Task A's own
    best-effort extraction only when no boundary was submitted at all
    (backward compatible with intake sessions that predate this field)."""
    if result.status != "ready" or result.pending_ask_issues:
        raise ValueError(
            "Cannot build a Confirmed Hiring Intent while the intake still has unresolved questions or contradictions."
        )

    role = result.role_understanding
    decision = result.decision
    constraints = role.explicit_constraints

    if boundary is not None:
        hiring_company = (boundary.hiring_company or "").strip() or None
        locations = _structured_locations_from_boundary(boundary)
        work_mode = boundary.work_mode
        radius_miles = boundary.radius_miles if boundary.work_mode in ("onsite", "hybrid") else None
        radius_place = _radius_place_from_boundary(boundary)
    else:
        hiring_company = (role.hiring_company.value or "").strip() or None
        locations = [
            StructuredLocation(city=entry.city, state=entry.state, country=entry.country)
            for entry in constraints.locations
        ]
        work_mode = constraints.work_mode
        radius_miles = None
        radius_place = None

    return ConfirmedHiringIntent(
        posted_title=role.posted_title,
        hiring_company=hiring_company,
        candidate_identity=role.primary_candidate_identity.value or "",
        seniority=role.seniority_scope.value,
        experience_minimum_years=constraints.experience_minimum_years,
        experience_maximum_years=constraints.experience_maximum_years,
        locations=locations,
        radius_miles=radius_miles,
        radius_place=radius_place,
        work_mode=work_mode,
        employment_type=constraints.employment_type,
        exclude_titles=list(constraints.exclusions),
        preferred_companies=[],
        # Default: exclude current employees of the company actually doing
        # the hiring — "hiring for Epiq" must never mean "find people who
        # already work at Epiq." Only ever the hiring company itself (never
        # invented from weak evidence); the recruiter can remove it on the
        # Search Brief like any other company-exclude entry, and nothing
        # downstream re-derives or re-applies it once set.
        exclude_current_companies=[hiring_company] if hiring_company else [],
        preferred_company_types=[],
        core_search_signals=_core_signals_with_duration(
            list(decision.final_search_intent.hard_requirements),
            list(decision.final_search_intent.strong_signals),
            constraints.experience_minimum_years,
        ),
        supporting_search_signals=list(decision.final_search_intent.strong_signals),
        differentiator_search_signals=list(decision.final_search_intent.preferred_differentiators),
        natural_language_search_query=decision.final_search_intent.natural_language_search_query or "",
    )


def to_search_intent(intent: ConfirmedHiringIntent, query_expander: Optional[QueryExpansionService] = None) -> SearchIntent:
    """Stage 2: Confirmed Hiring Intent -> the existing, unmodified
    SearchIntent shape SearchPlanner already consumes. This is the ONLY
    place title expansion happens for the confirmed-intake path — the
    frontend must never call its own title-expansion heuristic on this
    output (see searchIntentToBrief in models/searchBrief.ts)."""
    query_expander = query_expander or QueryExpansionService()

    normalized_identity = normalize_candidate_identity(intent.candidate_identity, intent.posted_title)
    expanded_titles = query_expander.expand_titles([normalized_identity])

    natural_language_search_query = intent.natural_language_search_query.strip() or _fallback_natural_language_query(
        normalized_identity,
        intent.seniority,
        intent.core_search_signals,
        intent.supporting_search_signals,
        intent.differentiator_search_signals,
    )

    # _flatten_locations already derives its own radius_place when there's
    # exactly one city-bearing location (the JD-only path relied on that
    # auto-derivation and never set intent.radius_miles at all). When the
    # recruiter explicitly set a radius (onsite/hybrid boundary), that value
    # was previously silently dropped here — ConfirmedHiringIntent carried
    # radius_miles/radius_place but this function never read them. Fixed:
    # an explicit radius always wins; an explicit radius_place overrides the
    # auto-derived one (same value in practice, kept in sync deliberately).
    location = _flatten_locations(intent.locations)
    if intent.radius_miles:
        location.radius_miles = intent.radius_miles
        if intent.radius_place:
            location.radius_place = intent.radius_place
    location.work_mode = intent.work_mode

    return SearchIntent(
        role=Role(title=normalized_identity, seniority=intent.seniority),
        location=location,
        experience=Experience(
            minimum_years=intent.experience_minimum_years,
            maximum_years=intent.experience_maximum_years,
        ),
        titles=Titles(
            include_titles=[title for title in expanded_titles if title != normalized_identity],
            exclude_titles=list(intent.exclude_titles),
        ),
        # Previously omitted entirely here, so exclude_current_companies/
        # preferred_company_types silently reset to empty regardless of what
        # ConfirmedHiringIntent carried — the actual root cause of current
        # employees of the hiring company reaching search results.
        company_preferences=CompanyPreferences(
            exclude_current_companies=list(intent.exclude_current_companies),
            preferred_company_types=list(intent.preferred_company_types),
        ),
        natural_language_search_query=natural_language_search_query,
        # Preserved as structured lists too (not just flattened into the NL
        # query) so ranking/evidence can look for literal textual evidence of
        # them per candidate without any role-specific keyword list in code —
        # see backend/services/candidate_evidence_builder.py.
        core_signals=list(intent.core_search_signals),
        supporting_signals=list(intent.supporting_search_signals),
        differentiator_signals=list(intent.differentiator_search_signals),
    )


def translate(result: IntakeResult, query_expander: Optional[QueryExpansionService] = None) -> SearchIntent:
    """The full IntakeResult -> SearchIntent path. Raises ValueError while
    the intake still has unresolved questions/contradictions (via
    build_confirmed_hiring_intent)."""
    confirmed = build_confirmed_hiring_intent(result)
    return to_search_intent(confirmed, query_expander=query_expander)
