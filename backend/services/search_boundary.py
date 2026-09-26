"""Server-side validation of the recruiter's Search Boundary.

The boundary is recruiter-owned and authoritative, so the server, not the browser, decides whether it is complete
and well formed. This is deterministic: no LLM is involved, and nothing here interprets or "fixes" a boundary beyond
normalizing spellings the search provider matches on (US state abbreviations, common country aliases).

Full "is this city really in this state" validation stays with the typeahead in the browser: the server carries no
location dataset, and this module does not pretend to.
"""

import dataclasses
from typing import List, Optional

from backend.models.intake import SearchBoundary
from backend.services.search_translator import normalize_state

WORK_MODES = ("onsite", "hybrid", "remote")
REMOTE_SCOPES = ("anywhere", "states", "cities")
MAX_RADIUS_MILES = 500.0

_COUNTRY_ALIASES = {
    "us": "United States",
    "u.s.": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
}


class BoundaryValidationError(ValueError):
    """Raised with recruiter-readable messages, one per problem."""

    def __init__(self, errors: List[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def normalize_country(country: Optional[str]) -> str:
    text = (country or "").strip()
    return _COUNTRY_ALIASES.get(text.lower(), text)


def _clean_list(values: List[str], transform=lambda value: value) -> List[str]:
    cleaned: List[str] = []
    for value in values or []:
        text = transform((value or "").strip())
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def validate_search_boundary(boundary: Optional[SearchBoundary]) -> SearchBoundary:
    """Returns the normalized boundary, or raises BoundaryValidationError listing every problem."""
    if boundary is None:
        raise BoundaryValidationError(["A search boundary is required: hiring company, country and work mode."])

    errors: List[str] = []
    hiring_company = (boundary.hiring_company or "").strip()
    country = normalize_country(boundary.country)
    work_mode = (boundary.work_mode or "").strip().lower()

    if not hiring_company:
        errors.append("Enter the hiring company.")
    if not country:
        errors.append("Select a country.")
    if work_mode not in WORK_MODES:
        errors.append("Choose a work mode: onsite, hybrid or remote.")

    state: Optional[str] = None
    city: Optional[str] = None
    radius: Optional[float] = None
    remote_scope: Optional[str] = None
    remote_states: List[str] = []
    remote_cities: List[str] = []

    if work_mode in ("onsite", "hybrid"):
        state = normalize_state((boundary.state or "").strip()) or None
        city = (boundary.city or "").strip() or None
        radius = boundary.radius_miles
        if not state:
            errors.append(f"Select a state or region for a {work_mode} role.")
        if not city:
            errors.append(f"Select a city for a {work_mode} role.")
        if radius is None or radius <= 0:
            errors.append("Enter a search radius greater than zero.")
        elif radius > MAX_RADIUS_MILES:
            errors.append(f"The search radius cannot exceed {int(MAX_RADIUS_MILES)} miles.")
    elif work_mode == "remote":
        remote_scope = (boundary.remote_scope or "").strip().lower() or None
        if remote_scope not in REMOTE_SCOPES:
            errors.append("For a remote role, choose where candidates can be located: anywhere in the country, specific states, or specific cities.")
            remote_scope = None
        elif remote_scope == "states":
            remote_states = _clean_list(boundary.remote_states, normalize_state)
            if not remote_states:
                errors.append("Add at least one state or region.")
        elif remote_scope == "cities":
            remote_cities = _clean_list(boundary.remote_cities)
            if not remote_cities:
                errors.append("Add at least one city.")

    if errors:
        raise BoundaryValidationError(errors)

    return dataclasses.replace(
        boundary,
        hiring_company=hiring_company,
        country=country,
        work_mode=work_mode,
        state=state,
        city=city,
        radius_miles=radius,
        remote_scope=remote_scope,
        remote_states=remote_states,
        remote_cities=remote_cities,
    )
