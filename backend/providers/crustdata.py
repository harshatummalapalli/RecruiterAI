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
DEFAULT_LIMIT = 25
DEFAULT_FIELDS = ["crustdata_person_id", "basic_profile", "experience", "social_handles"]
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_BASE = 0.5

# CrustData's person_search employment_type vocabulary, confirmed live via
# person_autocomplete on experience.employment_details.current.employment_type.
# A guessed/unvalidated value silently returns zero rows, so we only ever
# forward a value we've actually verified exists.
SUPPORTED_EMPLOYMENT_TYPES = {
    "full-time",
    "part-time",
    "internship",
    "contract",
    "self-employed",
}


class CrustDataProvider(BaseProvider):
    """Adapter for translating a provider-agnostic SearchPlan into CrustData-compatible requests."""

    def __init__(self, client: Optional[httpx.Client] = None, base_url: Optional[str] = None) -> None:
        self._client = client
        self._base_url = base_url or "https://api.crustdata.com/person/search"

    def search(self, plan: SearchPlan) -> List[Candidate]:
        """Execute one request per search query and merge all normalized candidates."""
        return self.search_with_options(plan)

    def debug_payloads(self, plan: SearchPlan, options: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Build (without sending) the exact payload each query in the plan would
        send to CrustData. Reuses the real payload-building code path — this is
        never a mock/approximation — so Debug Mode shows the true request, and no
        CrustData credits are spent computing it."""
        options = options or {}
        return [self._build_payload(search, options=options, cursor=options.get("cursor")) for search in plan.searches]

    def search_with_options(self, plan: SearchPlan, options: Optional[Dict[str, Any]] = None) -> List[Candidate]:
        """Execute one or more paginated requests per search query and merge the normalized candidates."""
        options = options or {}
        if not plan.searches:
            logger.warning("No searches were provided to the CrustData provider")
            return []

        all_candidates: List[Candidate] = []

        for search in plan.searches:
            page_number = 1
            cursor = options.get("cursor")
            max_pages = options.get("max_pages")
            if max_pages is None:
                max_pages = 1
            elif not isinstance(max_pages, int):
                max_pages = int(max_pages)
            if max_pages < 1:
                max_pages = 1

            while True:
                payload = self._build_payload(search, options=options, cursor=cursor)
                started_at = time.perf_counter()
                response = self._search_api(payload, options=options)
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                candidates = self._parse_candidates(response, query_name=search.query_name)
                logger.info(
                    "CrustData query completed",
                    extra={
                        "query_name": search.query_name or "unnamed",
                        "request_duration_ms": duration_ms,
                        "candidate_count": len(candidates),
                        "page_number": page_number,
                        "cursor": cursor,
                        **self._extract_credit_metadata(response),
                    },
                )
                all_candidates.extend(candidates)

                if page_number >= max_pages:
                    break

                next_cursor = self._extract_next_cursor(response)
                if not next_cursor:
                    break

                cursor = next_cursor
                page_number += 1

        return all_candidates

    def _build_payload(self, search: SearchQuery, options: Optional[Dict[str, Any]] = None, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Translate a provider-agnostic SearchQuery into a CrustData-compatible payload."""
        options = options or {}
        conditions = self._build_filter_conditions(search)
        filters = self._build_filters(conditions)

        payload: Dict[str, Any] = {
            "filters": filters,
            "limit": int(options.get("page_size") or DEFAULT_LIMIT),
            "fields": DEFAULT_FIELDS,
        }
        if cursor is not None:
            payload["cursor"] = cursor
        # Note: CrustData's /person/search API rejects an "autocomplete" field
        # outright (400 invalid_request, extra_forbidden) as of API version
        # 2025-11-01 — the generic `autocomplete` request option is accepted
        # by our own /search endpoint but deliberately not forwarded here.

        # A caller-supplied natural-language query (the primary discovery
        # mechanism — verified live to be relevance-ranked and to surface
        # candidates whose current title doesn't match) is sent verbatim.
        # It deliberately does NOT fall back to a title/skill keyword
        # concatenation: that old behavior merged required and preferred
        # skills into one undifferentiated text blob with no required/
        # preferred distinction, which is exactly what this replaces.
        if search.natural_language_query:
            payload["search"] = {"query": search.natural_language_query, "mode": "hybrid"}

        return payload

    def _build_filter_conditions(self, search: SearchQuery) -> List[Dict[str, Any]]:
        conditions: List[Dict[str, Any]] = []

        # Title inclusion: structural OR across conservative title variants —
        # never a "A|B|C" string with the "(.)" fuzzy operator, which was
        # confirmed live to silently fuzzy-match the literal joined string
        # (returning near-zero results) rather than behaving as an OR.
        title_or = self._fuzzy_or_conditions(
            "experience.employment_details.current.title",
            search.include_titles,
        )
        if title_or is not None:
            conditions.append(title_or)

        # Title exclusion: fuzzy-NOT ("(!)") on the CURRENT title only, never
        # `not_in`/`!=` — both were confirmed live to be exact-string-only
        # matches that let virtually every real compound executive title
        # ("Co-Founder & CTO") through unexcluded. Scoping to `current.title`
        # (not the unscoped `experience.employment_details.title`) is what
        # keeps a candidate's past Founder/CTO/Director history from
        # disqualifying them — only their present title is evaluated.
        for excluded_title in self._clean_string_values(search.exclude_titles):
            conditions.append(
                {"field": "experience.employment_details.current.title", "type": "(!)", "value": excluded_title}
            )

        self._append_condition(
            conditions,
            "basic_profile.location.country",
            "in",
            self._clean_string_values(search.countries),
        )
        self._append_condition(
            conditions,
            "basic_profile.location.state",
            "in",
            self._clean_string_values(search.states),
        )
        self._append_condition(
            conditions,
            "basic_profile.location.city",
            "in",
            self._clean_string_values(search.cities),
        )

        # Radius: CrustData has no ZIP/postal filter field at all (confirmed
        # live — an attempted zip_code filter is rejected with a 400).
        # geo_distance takes a free-form place name (geocoded server-side) or
        # explicit lat/lng — never a "zip_code" field. When the recruiter
        # only gave a ZIP, `radius_place` may itself be that ZIP string,
        # which CrustData geocodes the same as any other place text; we never
        # send it as a distinct zip filter.
        if search.radius_place and search.radius_miles:
            conditions.append(
                {
                    "field": "basic_profile.location",
                    "type": "geo_distance",
                    "value": {
                        "location": search.radius_place,
                        "distance": search.radius_miles,
                        "unit": search.radius_unit or "mi",
                    },
                }
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
            self._normalize_maximum_years(search.maximum_years),
        )

        # Employment type: only forwarded when it matches a live-confirmed
        # value (see SUPPORTED_EMPLOYMENT_TYPES) — an unvalidated categorical
        # value silently returns zero rows rather than erroring, so an
        # unrecognized value is dropped instead of risking a dead search.
        if search.employment_type and search.employment_type.strip().lower() in SUPPORTED_EMPLOYMENT_TYPES:
            self._append_condition(
                conditions,
                "experience.employment_details.current.employment_type",
                "in",
                [search.employment_type],
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

    def _fuzzy_or_conditions(self, field: str, values: List[str]) -> Optional[Dict[str, Any]]:
        """Build a genuine structural OR across fuzzy-match conditions on one
        field. Never joins values into a single "A|B|C" string — that string
        is fuzzy-matched as one literal phrase, not as alternation."""
        cleaned = self._clean_string_values(values)
        if not cleaned:
            return None
        if len(cleaned) == 1:
            return {"field": field, "type": "(.)", "value": cleaned[0]}
        return {"op": "or", "conditions": [{"field": field, "type": "(.)", "value": value} for value in cleaned]}

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

    def _normalize_maximum_years(self, maximum_years: Optional[int]) -> Optional[int]:
        """Defense-in-depth: a maximum of 0 (or less) means "no maximum" and
        must never be sent as `years_of_experience_raw =< 0` — combined with
        any minimum_years filter that would be a self-contradicting AND
        condition guaranteeing zero results. SearchQuery already normalizes
        this on construction; this guard covers any caller that builds a
        payload from an un-normalized value."""
        if maximum_years is None or maximum_years <= 0:
            return None
        return maximum_years

    def _clean_string_values(self, values: List[str]) -> List[str]:
        return [value for value in values if isinstance(value, str) and value.strip()]

    def _build_headers(self, api_key: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "x-api-version": API_VERSION,
        }

    def _search_api(self, payload: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute the CrustData API request and return the parsed JSON payload."""
        options = options or {}
        api_key = get_crustdata_api_key()
        if not api_key:
            logger.warning("Sourcing configuration is unavailable")
            raise ConfigurationError("Sourcing configuration is unavailable.")

        client = self._client or httpx.Client(timeout=10.0)
        should_close_client = self._client is None
        max_retries = int(options.get("max_retries") or DEFAULT_MAX_RETRIES)
        retry_backoff_base = float(options.get("retry_backoff_base") or DEFAULT_RETRY_BACKOFF_BASE)

        try:
            for attempt in range(max_retries + 1):
                try:
                    response = client.post(self._base_url, json=payload, headers=self._build_headers(api_key))
                    response.raise_for_status()
                    break
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    if attempt < max_retries and (status_code == 429 or status_code >= 500):
                        delay_seconds = retry_backoff_base * (2**attempt)
                        logger.warning(
                            "CrustData retrying request after HTTP status %s",
                            status_code,
                            extra={"retry_attempt": attempt + 1, "retry_delay_seconds": delay_seconds},
                        )
                        time.sleep(delay_seconds)
                        continue
                    logger.warning(
                        "Sourcing request failed with HTTP status %s | payload=%s | response_body=%s",
                        status_code,
                        payload,
                        exc.response.text[:2000],
                    )
                    raise ProviderError("The sourcing service could not complete the request.") from exc
                except httpx.RequestError as exc:
                    if attempt < max_retries:
                        delay_seconds = retry_backoff_base * (2**attempt)
                        logger.warning(
                            "CrustData retrying request due to request error",
                            extra={"retry_attempt": attempt + 1, "retry_delay_seconds": delay_seconds},
                        )
                        time.sleep(delay_seconds)
                        continue
                    logger.error("CrustData search request failed due to a request error", exc_info=True)
                    raise ProviderError(f"CrustData search request failed: {exc}") from exc
            else:
                raise ProviderError("CrustData search request failed after retries")
        finally:
            if should_close_client:
                client.close()

        try:
            return response.json()
        except ValueError as exc:
            logger.warning("Sourcing response was invalid")
            raise ProviderError("The sourcing service returned an invalid response.") from exc

    def _parse_candidates(self, response: Dict[str, Any], query_name: Optional[str] = None) -> List[Candidate]:
        """Normalize the provider response into Candidate objects."""
        profiles = self._extract_profiles(response)
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

            raw_data = self._normalize_item(item, response)
            # Tags which discovery query found this candidate (e.g.
            # "natural_language", "title_expansion"). CandidateMerger merges
            # this list across duplicates so a candidate found by more than
            # one query can be identified and given a small ranking boost —
            # convergence across independent discovery paths is itself a
            # positive signal.
            if query_name:
                raw_data["matched_queries"] = [query_name]

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
                    raw_data=raw_data,
                )
            )

        return candidates

    def _extract_profiles(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        for key in ("profiles", "results", "data", "items"):
            value = response.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _normalize_item(self, item: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
        normalized_item = dict(item)
        metadata = self._extract_response_metadata(response)
        if metadata:
            normalized_item["__response_metadata"] = metadata
        return normalized_item

    def _extract_response_metadata(self, response: Dict[str, Any]) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        for key in ("next_cursor", "total_count", "has_more", "credits_remaining", "credits_used", "credit_usage"):
            if key in response:
                metadata[key] = response[key]
        return metadata

    def _coerce_mapping(self, value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _extract_provider_score(self, item: Dict[str, Any]) -> Optional[float]:
        for key in ("score", "relevance", "ranking_score", "rank_score"):
            value = item.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def _extract_next_cursor(self, response: Dict[str, Any]) -> Optional[str]:
        value = response.get("next_cursor") or response.get("cursor")
        return value if isinstance(value, str) and value else None

    def _extract_credit_metadata(self, response: Dict[str, Any]) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        for key in ("credits_remaining", "credits_used", "credit_usage"):
            if key in response:
                metadata[key] = response[key]
        return metadata

    def _extract_location(self, basic_profile: Dict[str, Any]) -> Optional[str]:
        location_data = basic_profile.get("location")
        if isinstance(location_data, dict):
            return location_data.get("raw") or location_data.get("city")
        if isinstance(location_data, str):
            return location_data
        return None
