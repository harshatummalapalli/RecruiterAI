from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchQuery(BaseModel):
    """Provider-agnostic representation of recruiter intent for a single search query."""

    model_config = ConfigDict(validate_assignment=True)

    query_name: Optional[str] = None
    include_titles: List[str] = Field(default_factory=list)
    exclude_titles: List[str] = Field(default_factory=list)
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    countries: List[str] = Field(default_factory=list)
    states: List[str] = Field(default_factory=list)
    cities: List[str] = Field(default_factory=list)
    zip_codes: List[str] = Field(default_factory=list)
    radius_miles: Optional[float] = None
    radius_place: Optional[str] = None
    radius_unit: str = "mi"
    work_mode: Optional[str] = None
    employment_type: Optional[str] = None
    minimum_years: Optional[int] = None
    maximum_years: Optional[int] = None
    preferred_companies: List[str] = Field(default_factory=list)
    exclude_current_companies: List[str] = Field(default_factory=list)
    preferred_company_types: List[str] = Field(default_factory=list)
    # Any-time ("ever worked there") company scope — maps to the verified
    # CrustData field experience.employment_details.company_name (a superset of
    # current). preferred_companies_ever: include anyone who has EVER worked at
    # these companies; exclude_companies_ever: drop anyone who EVER worked at
    # these. The plain preferred_companies/exclude_current_companies above stay
    # scoped to the CURRENT employer (experience.employment_details.current.
    # company_name). See PHASE_0_1_IMPLEMENTATION_SPEC.md §2.5.
    preferred_companies_ever: List[str] = Field(default_factory=list)
    exclude_companies_ever: List[str] = Field(default_factory=list)
    # Hard capability keywords (Phase 2 §2.4) — whole-word (.) OR'd across the
    # candidate's description/headline/summary text. A must-have capability the
    # recruiter wants ENFORCED (precision over recall), e.g. "Java" / ".NET" /
    # "RAG". Empty keeps capabilities fully soft (NL query only).
    must_have_keywords: List[str] = Field(default_factory=list)
    # Hard capability keyword GROUPS — the synonym-aware form of
    # must_have_keywords. Each inner list is one capability expressed as a set
    # of interchangeable surface terms that are OR'd together (e.g. the
    # role-defining "AI" capability → ["AI", "ML", "machine learning", "LLM",
    # "generative", "agentic"]); the groups are AND'd with each other and with
    # the flat must_have_keywords above. This exists because must_have_keywords
    # alone AND's every term, so it cannot express "require evidence of this ONE
    # capability, in ANY of its common spellings" without over-filtering. Each
    # term is still a whole-word (.) match OR'd across description/headline/
    # summary. Empty keeps today's behavior. See CAPABILITY_AWARE_AGENT_ARCHITECTURE.md §1(C).
    must_have_keyword_groups: List[List[str]] = Field(default_factory=list)
    # Set only on the primary discovery query — when present, this is sent
    # to CrustData's `search: {query, mode: "hybrid"}` verbatim instead of
    # the title+skills keyword concatenation. See providers/crustdata.py.
    natural_language_query: Optional[str] = None

    @field_validator(
        "include_titles",
        "exclude_titles",
        "required_skills",
        "preferred_skills",
        "countries",
        "states",
        "cities",
        "zip_codes",
        "preferred_companies",
        "exclude_current_companies",
        "preferred_company_types",
        "preferred_companies_ever",
        "exclude_companies_ever",
        "must_have_keywords",
        mode="before",
    )
    @classmethod
    def _normalize_string_list(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            normalized: List[str] = []
            for item in value:
                if item is None:
                    continue
                if isinstance(item, str):
                    stripped = item.strip()
                    if stripped:
                        normalized.append(stripped)
                    continue
                normalized.append(item)
            return normalized
        return [value]

    @field_validator("must_have_keyword_groups", mode="before")
    @classmethod
    def _normalize_keyword_groups(cls, value: Any) -> List[List[str]]:
        """Clean a list of synonym groups: strip terms, drop blanks and
        duplicate terms within a group (order-preserving), and drop any group
        that ends up empty. A bare list of strings is treated as a single
        group, so callers can pass either shape."""
        if value is None:
            return []
        if isinstance(value, (list, tuple)) and value and all(isinstance(item, str) for item in value):
            value = [value]
        groups: List[List[str]] = []
        for group in value or []:
            if isinstance(group, str):
                group = [group]
            seen = set()
            cleaned: List[str] = []
            for item in group or []:
                if not isinstance(item, str):
                    continue
                stripped = item.strip()
                key = stripped.lower()
                if stripped and key not in seen:
                    seen.add(key)
                    cleaned.append(stripped)
            if cleaned:
                groups.append(cleaned)
        return groups

    @field_validator("query_name", "work_mode", "employment_type", "radius_place", "natural_language_query", mode="before")
    @classmethod
    def _normalize_optional_string(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("maximum_years", mode="before")
    @classmethod
    def _normalize_maximum_years(cls, value: Any) -> Optional[int]:
        """A maximum of 0 (or less) means "no maximum" throughout the app —
        JD parsing emits 0 as its unspecified-value placeholder, and a real
        upper bound of zero years of experience is not a meaningful search.
        Normalizing here (rather than only in the provider adapter) keeps
        every downstream consumer — capability mapping, query expansion,
        diagnostics — seeing the same "no maximum" value."""
        if value is None:
            return None
        try:
            numeric_value = int(value)
        except (TypeError, ValueError):
            return None
        return numeric_value if numeric_value > 0 else None


class SearchPlan(BaseModel):
    """Provider-agnostic plan composed of one or more recruiter-intent queries."""

    model_config = ConfigDict(validate_assignment=True)

    searches: List[SearchQuery] = Field(default_factory=list)
    strategy: Optional[str] = None
    reasoning: Optional[str] = None
    confidence_score: Optional[float] = None
