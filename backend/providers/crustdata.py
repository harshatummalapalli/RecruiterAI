import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from backend.config import get_crustdata_api_key
from backend.errors import ConfigurationError, ProviderError
from backend.models.candidate import Candidate
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.providers.base import BaseProvider

logger = logging.getLogger(__name__)

API_VERSION = "2025-11-01"
DEFAULT_LIMIT = 10
DEFAULT_FIELDS = ["crustdata_person_id", "basic_profile", "experience", "social_handles"]


class CrustDataProvider(BaseProvider):
    """Adapter for translating a provider-agnostic SearchPlan into CrustData-compatible requests."""

    def __init__(self, client: Optional[httpx.Client] = None, base_url: Optional[str] = None) -> None:
        self._client = client
        self._base_url = base_url or "https://api.crustdata.com/person/search"

    def search(self, plan: SearchPlan) -> List[Candidate]:
        """Execute one request per search query and merge all normalized candidates."""
        if not plan.searches:
            logger.warning("No searches were provided to the CrustData provider")
            return []

        all_candidates: List[Candidate] = []

        for search in plan.searches:
            payload = self._build_payload(search)
            started_at = time.perf_counter()
            response = self._search_api(payload)
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            candidates = self._parse_candidates(response)
            logger.info(
                "CrustData query completed",
                extra={
                    "query_name": search.query_name or "unnamed",
                    "request_duration_ms": duration_ms,
                    "candidate_count": len(candidates),
                },
            )
            all_candidates.extend(candidates)

        return all_candidates

    def _build_payload(self, search: SearchQuery) -> Dict[str, Any]:
        """Translate a provider-agnostic SearchQuery into a CrustData-compatible payload."""
        conditions = self._build_filter_conditions(search)
        filters = self._build_filters(conditions)

        payload: Dict[str, Any] = {
            "filters": filters,
            "limit": DEFAULT_LIMIT,
            "fields": DEFAULT_FIELDS,
        }

        query_text = self._build_search_query(search)
        if query_text:
            payload["search"] = {"query": query_text, "mode": "hybrid"}

        return payload

    def _build_filter_conditions(self, search: SearchQuery) -> List[Dict[str, Any]]:
        conditions: List[Dict[str, Any]] = []

        self._append_condition(
            conditions,
            "experience.employment_details.current.title",
            "(.)",
            "|".join(self._clean_string_values(search.include_titles)),
        )
        self._append_condition(
            conditions,
            "experience.employment_details.title",
            "not_in",
            self._clean_string_values(search.exclude_titles),
        )
        self._append_condition(
            conditions,
            "basic_profile.location.country",
            "in",
            self._clean_string_values(search.countries),
        )
        self._append_condition(
            conditions,
            "basic_profile.location.city",
            "in",
            self._clean_string_values(search.cities),
        )
        self._append_condition(
            conditions,
            "years_of_experience_raw",
            "=>",
            search.minimum_years,
        )
        self._append_condition(
            conditions,
            "years_of_experience_raw",
            "=<",
            search.maximum_years,
        )
        self._append_condition(
            conditions,
            "experience.employment_details.company_name",
            "in",
            self._clean_string_values(search.preferred_companies),
        )
        self._append_condition(
            conditions,
            "experience.employment_details.current.company_name",
            "not_in",
            self._clean_string_values(search.exclude_current_companies),
        )
        self._append_condition(
            conditions,
            "experience.employment_details.current.company_type",
            "in",
            self._clean_string_values(search.preferred_company_types),
        )

        return conditions

    def _append_condition(self, conditions: List[Dict[str, Any]], field: str, operator: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            if not value.strip():
                return
        elif isinstance(value, list):
            if not value:
                return
        elif isinstance(value, (tuple, set)):
            if not value:
                return

        conditions.append({"field": field, "type": operator, "value": value})

    def _build_filters(self, conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not conditions:
            return {"field": "basic_profile.name", "type": "(.)", "value": "a"}
        return {"op": "and", "conditions": conditions}

    def _build_search_query(self, search: SearchQuery) -> str:
        query_terms = [*self._clean_string_values(search.include_titles)]
        query_terms.extend(self._clean_string_values(search.required_skills))
        query_terms.extend(self._clean_string_values(search.preferred_skills))
        return " ".join(query_terms)

    def _clean_string_values(self, values: List[str]) -> List[str]:
        return [value for value in values if isinstance(value, str) and value.strip()]

    def _build_headers(self, api_key: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "x-api-version": API_VERSION,
        }

    def _search_api(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the CrustData API request and return the parsed JSON payload."""
        api_key = get_crustdata_api_key()
        if not api_key:
            logger.error("CRUSTDATA_API_KEY is not configured")
            raise ConfigurationError("CRUSTDATA_API_KEY is not configured. Set it in your environment or .env file.")

        client = self._client or httpx.Client(timeout=10.0)
        should_close_client = self._client is None
        try:
            response = client.post(self._base_url, json=payload, headers=self._build_headers(api_key))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("CrustData search request failed with HTTP status %s", exc.response.status_code)
            raise ProviderError(f"CrustData search request failed with status {exc.response.status_code}: {exc.response.text}") from exc
        except httpx.RequestError as exc:
            logger.error("CrustData search request failed due to a request error", exc_info=True)
            raise ProviderError(f"CrustData search request failed: {exc}") from exc
        finally:
            if should_close_client:
                client.close()

        try:
            return response.json()
        except ValueError as exc:
            logger.error("CrustData search response was not valid JSON")
            raise ProviderError("CrustData search response was not valid JSON") from exc

    def _parse_candidates(self, response: Dict[str, Any]) -> List[Candidate]:
        """Normalize the provider response into Candidate objects."""
        profiles = response.get("profiles") or response.get("results") or []
        candidates: List[Candidate] = []

        if not profiles:
            logger.warning("CrustData returned no results")

        for item in profiles:
            if not isinstance(item, dict):
                continue
            basic_profile = self._coerce_mapping(item.get("basic_profile"))
            experience = self._coerce_mapping(item.get("experience"))
            employment_details = self._coerce_mapping(experience.get("employment_details"))
            current_roles = employment_details.get("current") or []
            current_role = self._coerce_mapping(current_roles[0] if current_roles else None)

            social_handles = self._coerce_mapping(item.get("social_handles"))
            professional_network = self._coerce_mapping(social_handles.get("professional_network_identifier"))

            candidates.append(
                Candidate(
                    candidate_id=str(item.get("crustdata_person_id") or item.get("id") or ""),
                    name=basic_profile.get("name"),
                    title=current_role.get("title") or basic_profile.get("current_title") or basic_profile.get("headline"),
                    company=current_role.get("name"),
                    location=self._extract_location(basic_profile),
                    provider_score=self._extract_provider_score(item),
                    profile_url=professional_network.get("profile_url"),
                    source="crustdata",
                    raw_data=item,
                )
            )

        return candidates

    def _coerce_mapping(self, value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _extract_provider_score(self, item: Dict[str, Any]) -> Optional[float]:
        for key in ("score", "relevance", "ranking_score", "rank_score"):
            value = item.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def _extract_location(self, basic_profile: Dict[str, Any]) -> Optional[str]:
        location_data = basic_profile.get("location")
        if isinstance(location_data, dict):
            return location_data.get("raw") or location_data.get("city")
        if isinstance(location_data, str):
            return location_data
        return None
