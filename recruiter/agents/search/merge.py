"""Merge + the geographic safety net — small, pure.

merge: de-duplicate by candidate_id (unioning which queries found each), the
stable identity used everywhere. geo: a conservative net — drop a candidate only
when their KNOWN location is clearly outside the scope; unknown locations are
kept (CrustData was observed to leak an unfiltered global pool on a slow query,
so this is the backstop, not the primary filter).
"""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple

from recruiter.candidates import CandidateRecord
from recruiter.search_policy import AMBIGUOUS_TITLES, city_aliases


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


def _candidate_current_title(record: CandidateRecord) -> str:
    parts = [record.title or ""]
    raw = record.raw if isinstance(record.raw, dict) else {}
    exp = raw.get("experience") if isinstance(raw.get("experience"), dict) else {}
    cur = exp.get("current") if isinstance(exp, dict) else None
    if isinstance(cur, dict):
        parts.append(str(cur.get("title") or ""))
    return " ".join(parts)


def _capability_evidence_text(record: CandidateRecord) -> str:
    parts = [record.title or ""]
    raw = record.raw if isinstance(record.raw, dict) else {}
    bp = raw.get("basic_profile") if isinstance(raw.get("basic_profile"), dict) else {}
    parts += [str(bp.get("headline") or ""), str(bp.get("summary") or "")]
    return " ".join(parts).lower()


def enforce_title_exclusions(
    records: Iterable[CandidateRecord],
    exclude_titles: Tuple[str, ...],
    capability_terms: Tuple[str, ...] = (),
) -> Tuple[List[CandidateRecord], List[CandidateRecord]]:
    """Hard title-exclusion gate on the CURRENT title (CrustData's `(!)` negative
    leaks). Unambiguous leadership titles always drop; an ambiguous title
    ("Manager") is spared when the candidate's profile carries the role's
    capability (so a hands-on "eDiscovery Manager" survives but a plain people
    "Manager" doesn't). Past titles never disqualify; an unknown title is kept."""
    hard: List[re.Pattern] = []
    spare: List[Tuple[str, re.Pattern]] = []
    for t in exclude_titles:
        key = (t or "").strip().lower()
        if not key:
            continue
        rx = re.compile(r"\b" + re.escape(key) + r"\b", re.I)
        if key in AMBIGUOUS_TITLES:
            spare.append((key, rx))
        else:
            hard.append(rx)
    cap = [c.strip().lower() for c in capability_terms if c and c.strip()]
    records = list(records)
    if not hard and not spare:
        return records, []
    kept: List[CandidateRecord] = []
    dropped: List[CandidateRecord] = []
    for r in records:
        title = _candidate_current_title(r)
        if any(rx.search(title) for rx in hard):
            dropped.append(r)
        elif any(rx.search(title) for _, rx in spare):
            # A title that LEADS with the ambiguous term ("Manager Solutions Architect")
            # is a manager first — a capability in the headline must not spare it. Only
            # spare when the ambiguous word is secondary ("eDiscovery Manager").
            head = title.strip().lower()
            leads = any(head.startswith(key) for key, rx in spare if rx.search(title))
            evidence = _capability_evidence_text(r)
            if not leads and cap and any(c in evidence for c in cap):
                kept.append(r)               # ambiguous title + capability -> senior IC, keep
            else:
                dropped.append(r)
        else:
            kept.append(r)
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
        wanted |= city_aliases(c)
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
