"""Merge + the geographic safety net — small, pure.

merge: de-duplicate by candidate_id (unioning which queries found each), the
stable identity used everywhere. geo: a conservative net — drop a candidate only
when their KNOWN location is clearly outside the scope; unknown locations are
kept (CrustData was observed to leak an unfiltered global pool on a slow query,
so this is the backstop, not the primary filter).
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from recruiter.candidates import CandidateRecord


def merge(records: Iterable[CandidateRecord]) -> List[CandidateRecord]:
    by_id: dict = {}
    ordered: List[CandidateRecord] = []
    for r in records:
        if r.candidate_id and r.candidate_id in by_id:
            existing = by_id[r.candidate_id]
            existing.matched_queries = tuple(dict.fromkeys(existing.matched_queries + r.matched_queries))
            continue
        if r.candidate_id:
            by_id[r.candidate_id] = r
        ordered.append(r)
    return ordered


def enforce_geo(
    records: Iterable[CandidateRecord],
    countries: Tuple[str, ...] = (),
    states: Tuple[str, ...] = (),
) -> Tuple[List[CandidateRecord], List[CandidateRecord]]:
    scope = [s.lower() for s in list(countries) + list(states) if s]
    records = list(records)
    if not scope:
        return records, []
    kept: List[CandidateRecord] = []
    dropped: List[CandidateRecord] = []
    for r in records:
        loc = (r.location or "").lower()
        if not loc or any(s in loc for s in scope):
            kept.append(r)          # in-scope, or unknown -> keep (conservative)
        else:
            dropped.append(r)
    return kept, dropped
