"""Provider-order-preserving capture of one CrustData /person/search page.
Uses the production provider's own payload builder, HTTP call (with its retry
logic) and response parser, but records positions and the full response
envelope and never passes results through the ranker."""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.providers.crustdata import CrustDataProvider


@dataclass
class Capture:
    strategy: str
    payload: Dict[str, Any]
    response_envelope: Dict[str, Any]      # everything except the profile items
    raw_items: List[Dict[str, Any]]        # the provider's items, in the provider's order
    rows: List[Dict[str, Any]] = field(default_factory=list)
    elapsed_ms: float = 0.0
    calls: int = 1

    @property
    def total_count(self) -> Optional[int]:
        return self.response_envelope.get("total_count")

    @property
    def next_cursor(self) -> Optional[str]:
        return self.response_envelope.get("next_cursor")


def capture_first_page(provider: CrustDataProvider, strategy: str, payload: Dict[str, Any], query_name: str) -> Capture:
    started = time.perf_counter()
    response = provider._search_api(payload, options={})
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    items = provider._extract_profiles(response)
    candidates = provider._parse_candidates(response, query_name=query_name)
    envelope = {k: v for k, v in response.items() if k not in ("profiles", "results", "data", "items")}
    return Capture(
        strategy=strategy,
        payload=payload,
        response_envelope=envelope,
        raw_items=items,
        rows=rows_from(candidates, strategy),
        elapsed_ms=elapsed_ms,
    )


def rows_from(candidates: List[Any], strategy: str) -> List[Dict[str, Any]]:
    """One row per candidate in exactly the order given (the provider's order)."""
    rows = []
    for position, candidate in enumerate(candidates, start=1):
        raw = candidate.raw_data or {}
        meta = raw.get("__response_metadata") or {}
        rows.append(
            {
                "strategy": strategy,
                "provider_position": position,
                "candidate_id": candidate.candidate_id,
                "profile_url": candidate.profile_url,
                "name": candidate.name,
                "current_title": candidate.title,
                "current_company": candidate.company,
                "location": candidate.location,
                "fit": raw.get("fit"),
                "matched_queries": raw.get("matched_queries", []),
                "total_count": meta.get("total_count"),
                "next_cursor": meta.get("next_cursor"),
            }
        )
    return rows
