"""Agent 4 — Search. Pull the pool, merge, and run the geo safety net.

Pure orchestration over an injected provider, so it runs offline (no credits) in
tests and against the real CrustData adapter in production. Enrichment + the
Judge + ranking are Agent 5's job (admission decides who is worth enriching), so
Search stops at a clean, de-duplicated, in-scope pool.
"""

from __future__ import annotations

from recruiter.agents.briefing.model import ProviderQuery
from recruiter.agents.search.merge import (
    enforce_cities,
    enforce_company_exclusions,
    enforce_geo,
    merge,
)
from recruiter.agents.search.model import SearchResult, SourcingProvider

CREDITS_PER_RESULT = 0.03  # CrustData person_search charge


class SearchAgent:
    def __init__(self, provider: SourcingProvider, page_size: int = 50) -> None:
        self._provider = provider
        self._page_size = page_size

    def run(self, query: ProviderQuery) -> SearchResult:
        raw = self._provider.search(query, self._page_size)
        merged = merge(raw)
        kept, dropped = enforce_geo(merged, query.countries, query.states)
        city_dropped: list = []
        if query.cities:                      # hard-city gate (CrustData leaks the city filter)
            kept, city_dropped = enforce_cities(kept, query.cities)
        excluded_dropped: list = []
        if query.exclude_current_companies:   # CrustData leaks the negative company filter
            kept, excluded_dropped = enforce_company_exclusions(kept, query.exclude_current_companies)
        return SearchResult(
            candidates=tuple(kept),
            pulled=len(raw),
            geo_dropped=len(dropped) + len(city_dropped),
            est_credits=round(len(raw) * CREDITS_PER_RESULT, 2),
            excluded_dropped=len(excluded_dropped),
        )
