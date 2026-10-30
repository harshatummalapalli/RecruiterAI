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


# City name variants — CrustData's canonical is usually the first, but profiles
# carry either, so we match any. Extend as needed (verified: CrustData uses
# "Bengaluru"/"Hyderabad"/"Pune"/"New Delhi").
_CITY_ALIAS_GROUPS = [
    {"bengaluru", "bangalore"}, {"gurugram", "gurgaon"}, {"mumbai", "bombay"},
    {"kolkata", "calcutta"}, {"chennai", "madras"}, {"pune", "poona"},
    {"new delhi", "delhi"}, {"kochi", "cochin"}, {"vadodara", "baroda"},
    {"prayagraj", "allahabad"}, {"thiruvananthapuram", "trivandrum"},
]


def _aliases(city: str) -> set:
    key = city.strip().lower()
    for group in _CITY_ALIAS_GROUPS:
        if key in group:
            return group
    return {key}


def _candidate_location_text(record: CandidateRecord) -> str:
    """Prefer the structured city + full_location; fall back to the location string."""
    parts = [record.location or ""]
    raw = record.raw if isinstance(record.raw, dict) else {}
    loc = (raw.get("basic_profile") or {}).get("location") if isinstance(raw.get("basic_profile"), dict) else None
    if isinstance(loc, dict):
        parts += [str(loc.get("city") or ""), str(loc.get("full_location") or "")]
    return " ".join(parts).lower()


def _candidate_company_text(record: CandidateRecord) -> str:
    """The candidate's CURRENT employer. Prefer the mapped company; fall back to
    the structured current employment record."""
    parts = [record.company or ""]
    raw = record.raw if isinstance(record.raw, dict) else {}
    exp = raw.get("experience") if isinstance(raw.get("experience"), dict) else {}
    cur = exp.get("current") if isinstance(exp, dict) else None
    if isinstance(cur, dict):
        parts.append(str(cur.get("company_name") or ""))
    return " ".join(parts).lower()


def enforce_company_exclusions(
    records: Iterable[CandidateRecord], excluded: Tuple[str, ...]
) -> Tuple[List[CandidateRecord], List[CandidateRecord]]:
    """Hard company-exclusion gate. CrustData's negative company filter (`not_in`
    on current.company_name) leaks — on a live run the hiring company's own
    current employees came back despite being excluded. So we re-check each
    candidate's current employer and drop a known match (substring, case-fold, so
    "Epiq" also catches "Epiq Global"). An unknown employer is kept."""
    wanted = [e.strip().lower() for e in excluded if e and e.strip()]
    records = list(records)
    if not wanted:
        return records, []
    kept: List[CandidateRecord] = []
    dropped: List[CandidateRecord] = []
    for r in records:
        hay = _candidate_company_text(r).strip()
        if hay and any(w in hay for w in wanted):
            dropped.append(r)
        else:
            kept.append(r)                   # unknown employer -> keep
    return kept, dropped


def enforce_cities(
    records: Iterable[CandidateRecord], cities: Tuple[str, ...]
) -> Tuple[List[CandidateRecord], List[CandidateRecord]]:
    """Hard city gate — the recruiter restricted to specific cities, and
    CrustData's hybrid search leaks other-city / country-only people past the
    city filter. So we re-check each candidate's own location (alias-aware) and
    drop anyone whose KNOWN location isn't one of the chosen cities. A truly
    empty location is kept (can't tell); a country-only string like "India"
    has no city match and is dropped."""
    wanted: set = set()
    for c in cities:
        wanted |= _aliases(c)
    records = list(records)
    if not wanted:
        return records, []
    kept: List[CandidateRecord] = []
    dropped: List[CandidateRecord] = []
    for r in records:
        hay = _candidate_location_text(r).strip()
        if not hay:
            kept.append(r)                       # no location at all -> keep
        elif any(a in hay for a in wanted):
            kept.append(r)
        else:
            dropped.append(r)
    return kept, dropped
