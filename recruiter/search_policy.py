"""Search policy shared between the vendor adapter (what we SEND to CrustData) and
the verify nets (what we re-check on what comes BACK).

CrustData's hard filters are literal: `city in ["Bengaluru"]` returns 4.7M but
`["Bangalore"]` returns 0, and `["Gurgaon"]` returns 1 vs `["Gurugram"]` ~1M
(live probe 2026-10-30). Under `mode="exact"` that means a recruiter's spelling
that isn't CrustData's canonical one silently drops the whole city. So we send
EVERY known spelling (the canonical one carries it, the variants are harmless).

Likewise, CrustData can't do our nuanced title rule (spare a hands-on "Manager"
when the capability matches), so we never hand it the ambiguous titles — only the
unambiguous leadership ones — and let the verify net handle the rest.
"""

from __future__ import annotations

from typing import Iterable, List, Set, Tuple

# City name variants (first is usually CrustData's canonical). Keep lowercase.
CITY_ALIAS_GROUPS: List[Set[str]] = [
    {"bengaluru", "bangalore"}, {"gurugram", "gurgaon"}, {"mumbai", "bombay"},
    {"kolkata", "calcutta"}, {"chennai", "madras"}, {"pune", "poona"},
    {"new delhi", "delhi"}, {"kochi", "cochin"}, {"vadodara", "baroda"},
    {"prayagraj", "allahabad"}, {"thiruvananthapuram", "trivandrum"},
]

# Titles that are ambiguous between leadership and a senior IC (e.g. an
# "eDiscovery Manager" is a hands-on specialist). Never sent as a hard vendor
# exclusion — the title verify net decides these, sparing a capability match.
AMBIGUOUS_TITLES: Set[str] = {"manager"}


def city_aliases(city: str) -> Set[str]:
    """All known spellings for one city, lowercased (for matching returned data)."""
    key = city.strip().lower()
    for group in CITY_ALIAS_GROUPS:
        if key in group:
            return set(group)
    return {key}


def expand_city_aliases(cities: Iterable[str]) -> Tuple[str, ...]:
    """Expand each requested city to all known spellings for the OUTBOUND filter,
    title-cased, original-first, deduped case-insensitively. Sending the full set
    guarantees we include CrustData's canonical spelling whatever the recruiter
    typed."""
    out: List[str] = []
    seen: Set[str] = set()

    def add(value: str) -> None:
        v = value.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)

    for c in cities:
        if not c or not c.strip():
            continue
        add(c.strip())                                   # the recruiter's own spelling
        for alias in sorted(city_aliases(c)):            # + every known variant
            add(alias.title())
    return tuple(out)


def hard_title_exclusions(titles: Iterable[str]) -> Tuple[str, ...]:
    """The subset of exclude-titles safe to hand CrustData as a hard filter —
    unambiguous leadership only; ambiguous ones are left to the verify net."""
    return tuple(t for t in titles if t and t.strip().lower() not in AMBIGUOUS_TITLES)
