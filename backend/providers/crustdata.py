import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from backend.config import get_crustdata_api_key
from backend.models.candidate import Candidate
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class CrustDataProvider(BaseProvider):
    """Adapter for translating a SearchPlan into CrustData-compatible requests."""

    def __init__(self, client: Optional[httpx.Client] = None, base_url: Optional[str] = None) -> None:
        self._client = client
        self._base_url = base_url or "https://api.crustdata.example.com/search"

    def search(self, plan: SearchPlan) -> List[Candidate]:
        """Execute one request per search query and merge all normalized candidates."""
        if not plan.searches:
            logger.warning("No searches were provided to the CrustData provider")
            return []

        all_candidates: List[Candidate] = []

        for search in plan.searches:
            payload = self._build_payload(plan, search)
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

    def _build_payload(self, plan: SearchPlan, search: SearchQuery) -> Dict[str, Any]:
        """Translate a SearchPlan and a single SearchQuery into a provider-specific payload structure."""
        return {
            "strategy": plan.strategy,
            "reasoning": plan.reasoning,
            "confidence_score": plan.confidence_score,
            "searches": [self._build_search_payload(search)],
            "query_name": search.query_name,
        }

    def _build_search_payload(self, search: SearchQuery) -> Dict[str, Any]:
        """Translate one SearchQuery into a CrustData-style request section."""
        return {
            "include_titles": search.include_titles,
            "exclude_titles": search.exclude_titles,
            "required_skills": search.required_skills,
            "preferred_skills": search.preferred_skills,
            "countries": search.countries,
            "cities": search.cities,
            "work_mode": search.work_mode,
            "minimum_years": search.minimum_years,
            "maximum_years": search.maximum_years,
            "preferred_companies": search.preferred_companies,
            "exclude_current_companies": search.exclude_current_companies,
            "preferred_company_types": search.preferred_company_types,
            "must_have": search.must_have,
            "nice_to_have": search.nice_to_have,
            "bonus": search.bonus,
        }

    def _search_api(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the CrustData API request and return the parsed JSON payload."""
        api_key = get_crustdata_api_key()
        if not api_key:
            logger.error("CRUSTDATA_API_KEY is not configured")
            raise RuntimeError("CRUSTDATA_API_KEY is not configured. Set it in your environment or .env file.")

        client = self._client or httpx.Client(timeout=10.0)
        try:
            response = client.post(
                self._base_url,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("CrustData search request failed with HTTP status %s", exc.response.status_code)
            raise RuntimeError(f"CrustData search request failed with status {exc.response.status_code}: {exc.response.text}") from exc
        except httpx.RequestError as exc:
            logger.error("CrustData search request failed due to a request error", exc_info=True)
            raise RuntimeError(f"CrustData search request failed: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        try:
            return response.json()
        except ValueError as exc:
            logger.error("CrustData search response was not valid JSON")
            raise RuntimeError("CrustData search response was not valid JSON") from exc

    def _parse_candidates(self, response: Dict[str, Any]) -> List[Candidate]:
        """Normalize the provider response into Candidate objects."""
        results = response.get("results", [])
        candidates: List[Candidate] = []

        if not results:
            logger.warning("CrustData returned no results")

        for item in results:
            candidates.append(
                Candidate(
                    candidate_id=str(item.get("id")),
                    name=item.get("name"),
                    title=item.get("title"),
                    company=item.get("company"),
                    location=item.get("location"),
                    provider_score=item.get("score"),
                    profile_url=item.get("profile_url"),
                    source="crustdata",
                    raw_data=item,
                )
            )

        return candidates
