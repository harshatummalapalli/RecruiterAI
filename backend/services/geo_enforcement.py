"""Deterministic client-side geographic enforcement.

A safety net that GUARANTEES a geographically-constrained search never surfaces
candidates who are confirmably outside the recruiter's confirmed geography —
regardless of whether the provider actually honored the location filter.

Why this exists (observed live 2026-10-05): a slow CrustData geo-distance + hybrid
query blew the provider's HTTP timeout, retried, and the response that came back
was an UNFILTERED global pool (the provider reported ~169M in-scope and returned
candidates in the US, Thailand, Israel, Australia, …) for a 5-mile-Hyderabad
search. The query payload was correct — the provider degraded under latency. We
cannot rely on the provider to enforce geography under every condition, so we
enforce it ourselves as a last step before the recruiter sees anyone.

Conservative by design, mirroring admission's "never exclude the unclear": a
candidate is dropped ONLY when their current location is POSITIVELY outside scope
(a KNOWN country/state that does not match). Unknown or ambiguous locations are
kept. Radius/city precision is left to the provider; this guard works at the
country and state grain, which is what stops cross-border/cross-state leakage.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from backend.models.candidate import Candidate


def is_enabled() -> bool:
    """Default ON. A kill-switch (`SEARCH_GEO_ENFORCEMENT_ENABLED=false`) can
    disable the guard without a redeploy if it ever misbehaves."""
    raw = os.environ.get("SEARCH_GEO_ENFORCEMENT_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _norm(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().casefold()
    return cleaned or None


def _candidate_location(candidate: Candidate) -> Dict[str, Optional[str]]:
    """The candidate's current country/state as the provider reported them, from
    `raw_data.basic_profile.location` (keys: country/state/city/raw)."""
    basic_profile = (candidate.raw_data or {}).get("basic_profile") or {}
    location = basic_profile.get("location") if isinstance(basic_profile, dict) else None
    if not isinstance(location, dict):
        location = {}
    return {
        "country": _norm(location.get("country")),
        "state": _norm(location.get("state")),
        "raw": location.get("raw") or candidate.location,
    }


@dataclass
class GeoEnforcementResult:
    kept: List[Candidate]
    dropped: List[Candidate] = field(default_factory=list)
    reasons: Dict[str, str] = field(default_factory=dict)

    @property
    def dropped_count(self) -> int:
        return len(self.dropped)


def enforce_location(
    candidates: List[Candidate],
    countries: Optional[Iterable[str]] = None,
    states: Optional[Iterable[str]] = None,
) -> GeoEnforcementResult:
    """Keep every candidate except those whose KNOWN current country/state is
    outside the confirmed scope. A no-op when no country/state is confirmed (e.g.
    a deliberately global or country-less search)."""
    want_countries = {c for c in (_norm(x) for x in (countries or [])) if c}
    want_states = {s for s in (_norm(x) for x in (states or [])) if s}

    if not want_countries and not want_states:
        return GeoEnforcementResult(kept=list(candidates))

    kept: List[Candidate] = []
    dropped: List[Candidate] = []
    reasons: Dict[str, str] = {}

    for candidate in candidates:
        loc = _candidate_location(candidate)
        country, state = loc["country"], loc["state"]
        key = candidate.candidate_id or str(id(candidate))

        # Country gate: drop only a KNOWN, mismatched country. Unknown => kept.
        if want_countries and country is not None and country not in want_countries:
            dropped.append(candidate)
            reasons[key] = f"country {loc['raw']!r} outside {sorted(want_countries)}"
            continue

        # State gate: within the right (or unknown) country, drop a KNOWN,
        # mismatched state. Only enforced when the candidate is not already in a
        # wrong country (handled above) and the country matches or is unknown.
        if want_states and state is not None and state not in want_states:
            if not want_countries or country is None or country in want_countries:
                dropped.append(candidate)
                reasons[key] = f"state {loc['raw']!r} outside {sorted(want_states)}"
                continue

        kept.append(candidate)

    return GeoEnforcementResult(kept=kept, dropped=dropped, reasons=reasons)
