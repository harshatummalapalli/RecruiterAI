"""Agent 4 — Search. Pull the pool, merge, and run the geo safety net.

Pure orchestration over an injected provider, so it runs offline (no credits) in
tests and against the real CrustData adapter in production. Enrichment + the
Judge + ranking are Agent 5's job (admission decides who is worth enriching), so
Search stops at a clean, de-duplicated, in-scope pool.
"""

from __future__ import annotations

from typing import Optional

from recruiter.agents.briefing.model import ProviderQuery
from recruiter.agents.search.merge import (
    enforce_cities,
    enforce_company_exclusions,
    enforce_geo,
    enforce_title_exclusions,
    merge,
)
from recruiter.agents.search.model import SearchResult, SourcingProvider

CREDITS_PER_RESULT = 0.03  # CrustData person_search charge


def _total_available(records) -> "int | None":
    """CrustData reports the full filter-match count on each record's response
    metadata — the market universe we pulled the first page from."""
    for record in records:
        meta = (record.raw or {}).get("__response_metadata") if isinstance(getattr(record, "raw", None), dict) else None
        total = meta.get("total_count") if isinstance(meta, dict) else None
        if isinstance(total, int) and total > 0:
            return total
    return None


class SearchAgent:
    def __init__(self, provider: SourcingProvider, page_size: int = 50) -> None:
        self._provider = provider
        self._page_size = page_size

    def autocomplete(self, field: str, query: str, limit: int = 8):
        """Canonical-value typeahead (free). Empty when the provider can't do it."""
        fn = getattr(self._provider, "autocomplete", None)
        return list(fn(field, query, limit)) if callable(fn) else []

    def preview_count(self, query: ProviderQuery):
        """How many profiles match the filters, BEFORE any paid pull (~0.03 cr).
        Returns None when the provider can't count (e.g. the offline fake)."""
        counter = getattr(self._provider, "count", None)
        return counter(query) if callable(counter) else None

    def run(self, query: ProviderQuery, *, cursor: Optional[str] = None) -> SearchResult:
        search_page = getattr(self._provider, "search_page", None)
        raw, next_cursor = search_page(query, self._page_size, cursor=cursor) if callable(search_page) else (self._provider.search(query, self._page_size), None)
        merged = merge(raw)
        kept, dropped = enforce_geo(merged, query.countries, query.states)
        city_dropped: list = []
        if query.cities:                      # hard-city gate (CrustData leaks the city filter)
            kept, city_dropped = enforce_cities(kept, query.cities)
        company_dropped: list = []
        if query.exclude_current_companies:   # CrustData leaks the negative company filter
            kept, company_dropped = enforce_company_exclusions(kept, query.exclude_current_companies)
        if getattr(query, "exclude_companies_ever", None):   # "ever worked at" scope — check full history
            kept, ever_dropped = enforce_company_exclusions(kept, query.exclude_companies_ever, include_history=True)
            company_dropped = list(company_dropped) + ever_dropped
        title_dropped: list = []
        if query.exclude_titles:              # CrustData leaks the negative title filter too
            cap_terms = tuple(t for g in query.must_have_keyword_groups for t in g)
            kept, title_dropped = enforce_title_exclusions(kept, query.exclude_titles, cap_terms)
        return SearchResult(
            candidates=tuple(kept),
            pulled=len(raw),
            geo_dropped=len(dropped) + len(city_dropped),
            est_credits=round(len(raw) * CREDITS_PER_RESULT, 2),
            excluded_dropped=len(company_dropped) + len(title_dropped),
            total_available=_total_available(raw),
            next_cursor=next_cursor or _next_cursor(raw),
            credits_used=_credits_used(raw),
        )


def _next_cursor(records) -> Optional[str]:
    for record in reversed(records):
        raw = getattr(record, "raw", None)
        metadata = raw.get("__response_metadata") if isinstance(raw, dict) else None
        cursor = metadata.get("next_cursor") if isinstance(metadata, dict) else None
        if cursor:
            return str(cursor)
    return None


def _credits_used(records) -> Optional[float]:
    for record in records:
        raw = getattr(record, "raw", None)
        metadata = raw.get("__response_metadata") if isinstance(raw, dict) else None
        if isinstance(metadata, dict):
            for key in ("credits_used", "credit_usage", "_request_credits_used"):
                try:
                    value = float(metadata[key])
                    if value >= 0:
                        return value
                except (KeyError, TypeError, ValueError):
                    continue
    return None
