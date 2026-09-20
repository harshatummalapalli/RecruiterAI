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
