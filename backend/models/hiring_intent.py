"""Confirmed Hiring Intent — the single source of truth produced once, at
Living Brief confirmation, from IntakeResult. No LLM call happens here and
none happens again after this point; the Search Translator
(backend/services/search_translator.py) turns this into the existing
SearchIntent/SearchPlan shape deterministically. See the forensic
investigation this resolves for why this object exists."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class StructuredLocation:
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None


@dataclass
class ConfirmedHiringIntent:
    posted_title: Optional[str] = None
    # Task A's understanding of who is being hired. NOT guaranteed to be
    # title-shaped (it can be a descriptive phrase) — the Search Translator,
    # not this object, is responsible for normalizing it before it is ever
    # used as a title filter.
    candidate_identity: str = ""
    seniority: Optional[str] = None
    experience_minimum_years: Optional[int] = None
    experience_maximum_years: Optional[int] = None
    locations: List[StructuredLocation] = field(default_factory=list)
    radius_miles: Optional[float] = None
    radius_place: Optional[str] = None
    # Context only — never translated into a provider filter (CrustData has
    # no reliable person_search work-mode field; see providers/crustdata.py).
    work_mode: Optional[str] = None
    # Only ever set to a value CrustDataProvider.SUPPORTED_EMPLOYMENT_TYPES
    # actually recognizes; the Search Translator is responsible for that
    # validation, not this object.
    employment_type: Optional[str] = None
    exclude_titles: List[str] = field(default_factory=list)
    preferred_companies: List[str] = field(default_factory=list)
    exclude_current_companies: List[str] = field(default_factory=list)
    preferred_company_types: List[str] = field(default_factory=list)
    # Search signals — influence semantic retrieval (the natural-language
    # query), never a literal provider-side skill filter (CrustData does not
    # reliably support one on this plan/integration; see the forensic
    # investigation). Core is emphasized most strongly, then Supporting, then
    # Differentiators.
    core_search_signals: List[str] = field(default_factory=list)
    supporting_search_signals: List[str] = field(default_factory=list)
    differentiator_search_signals: List[str] = field(default_factory=list)
    natural_language_search_query: str = ""
