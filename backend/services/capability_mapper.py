from typing import List, Tuple

from backend.models.provider_capabilities import ProviderCapabilities
from backend.models.search_plan import SearchPlan, SearchQuery


class CapabilityMapper:
    """Adapt a SearchPlan to provider-specific capabilities."""

    def map(self, plan: SearchPlan, capabilities: ProviderCapabilities) -> Tuple[SearchPlan, List[str]]:
        warnings: List[str] = []
        mapped_searches: List[SearchQuery] = []

        supported_filters = set(capabilities.supported_filters or [])
        unsupported_filters = set(capabilities.unsupported_filters or [])
        allowed_filters = supported_filters | {"include_titles"}

        for query in plan.searches:
            mapped_query = self._clone_query(query)
            dropped_fields = []

            for field_name in self._filter_fields():
                if field_name in unsupported_filters:
                    continue
                if field_name not in allowed_filters:
                    if self._has_value(query, field_name):
                        self._clear_field(mapped_query, field_name)
                        dropped_fields.append(field_name)
                        warnings.append(f"{query.query_name or 'Search'}: dropped unsupported filter '{field_name}'")
                elif field_name not in supported_filters:
                    if self._has_value(query, field_name):
                        self._clear_field(mapped_query, field_name)
                        dropped_fields.append(field_name)
                        warnings.append(f"{query.query_name or 'Search'}: dropped unsupported filter '{field_name}'")

            mapped_searches.append(mapped_query)

        return SearchPlan(
            searches=mapped_searches,
            strategy=plan.strategy,
            reasoning=plan.reasoning,
            confidence_score=plan.confidence_score,
        ), warnings

    def _clone_query(self, query: SearchQuery) -> SearchQuery:
        return SearchQuery(**query.model_dump())

    def _clear_field(self, query: SearchQuery, field_name: str) -> None:
        if field_name == "include_titles":
            query.include_titles = []
        elif field_name == "exclude_titles":
            query.exclude_titles = []
        elif field_name == "required_skills":
            query.required_skills = []
        elif field_name == "preferred_skills":
            query.preferred_skills = []
        elif field_name == "countries":
            query.countries = []
        elif field_name == "cities":
            query.cities = []
        elif field_name == "work_mode":
            query.work_mode = None
        elif field_name == "minimum_years":
            query.minimum_years = None
        elif field_name == "maximum_years":
            query.maximum_years = None
        elif field_name == "preferred_companies":
            query.preferred_companies = []
        elif field_name == "exclude_current_companies":
            query.exclude_current_companies = []
        elif field_name == "preferred_company_types":
            query.preferred_company_types = []
        elif field_name == "must_have":
            query.must_have = []
        elif field_name == "nice_to_have":
            query.nice_to_have = []
        elif field_name == "bonus":
            query.bonus = []

    def _has_value(self, query: SearchQuery, field_name: str) -> bool:
        value = getattr(query, field_name, None)
        if isinstance(value, list):
            return bool(value)
        return value is not None

    def _filter_fields(self) -> List[str]:
        return [
            "include_titles",
            "exclude_titles",
            "required_skills",
            "preferred_skills",
            "countries",
            "cities",
            "work_mode",
            "minimum_years",
            "maximum_years",
            "preferred_companies",
            "exclude_current_companies",
            "preferred_company_types",
            "must_have",
            "nice_to_have",
            "bonus",
        ]
