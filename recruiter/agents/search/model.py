"""Search shapes: the sourcing-provider interface and the search result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol, Tuple

from recruiter.agents.briefing.model import ProviderQuery
from recruiter.candidates import CandidateRecord


class SourcingProvider(Protocol):
    """Implemented by the CrustData adapter (a keeper, migrated at live-run time)
    and by a fake in tests, so Search runs offline with zero credits."""

    def search(self, query: ProviderQuery, page_size: int) -> List[CandidateRecord]: ...


@dataclass(frozen=True)
class SearchResult:
    candidates: Tuple[CandidateRecord, ...]
    pulled: int               # raw records the provider returned
    geo_dropped: int          # records removed by the geo/city safety net
    est_credits: float        # pulled * CrustData per-result charge (informational)
    excluded_dropped: int = 0  # removed by the company-exclusion verify net
    # The total market matching the hard filters (CrustData's reported total_count;
    # NL ranking only reorders this set). The "universe" we read the strongest N from.
    total_available: Optional[int] = None
