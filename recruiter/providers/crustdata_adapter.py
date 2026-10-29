"""SourcingProvider backed by the keeper CrustData provider.

Bridges the clean ProviderQuery to the legacy SearchQuery/SearchPlan and maps
results back to CandidateRecord. `backend` is imported lazily so this module
loads without it; the real network call happens only at a (credit-gated) run.
Industry filtering is not forwarded yet — the keeper provider has no industry
condition builder (noted for the provider rewrite).
"""

from __future__ import annotations

from typing import List

from recruiter.agents.briefing.model import ProviderQuery
from recruiter.candidates import CandidateRecord


def _to_search_query(pq: ProviderQuery):
    from backend.models.search_plan import SearchQuery

    return SearchQuery(
        query_name="natural_language",
        natural_language_query=pq.natural_language,
        countries=list(pq.countries),
        states=list(pq.states),
        cities=list(pq.cities),
        minimum_years=pq.min_years,
        maximum_years=pq.max_years,
        radius_place=pq.radius_place,
        radius_miles=pq.radius_miles,
        employment_type=pq.employment_type,
        exclude_titles=list(pq.exclude_titles),
        exclude_current_companies=list(pq.exclude_current_companies),
        must_have_keyword_groups=[list(g) for g in pq.must_have_keyword_groups],
    )


def _to_record(candidate) -> CandidateRecord:
    raw = candidate.raw_data or {}
    matched = raw.get("matched_queries") or ["natural_language"]
    return CandidateRecord(
        candidate_id=candidate.candidate_id or "",
        name=candidate.name, title=candidate.title, company=candidate.company,
        location=candidate.location, profile_url=candidate.profile_url,
        provider_score=candidate.provider_score, raw=raw,
        matched_queries=tuple(matched),
    )


class CrustDataAdapter:
    def __init__(self, provider=None) -> None:
        self._provider = provider

    def _get(self):
        if self._provider is None:
            from backend.providers.crustdata import CrustDataProvider
            self._provider = CrustDataProvider()
        return self._provider

    def search(self, query: ProviderQuery, page_size: int) -> List[CandidateRecord]:
        from backend.models.search_plan import SearchPlan

        plan = SearchPlan(searches=[_to_search_query(query)], strategy="natural_language",
                          reasoning="rearch pipeline", confidence_score=None)
        candidates = self._get().search_with_options(plan, options={"page_size": page_size, "max_pages": 1})
        return [_to_record(c) for c in candidates]
