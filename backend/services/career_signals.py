"""Deterministic career-pattern predicates over a candidate's employment history.

This is the fixed, tested version of logic first tried ad hoc in the
"Search Logic Experiment" (company-size bands, industry scoping, career
progression). That experiment surfaced three real bugs — this module exists
to correct them and give them a single, reusable, tested home:

  1. A `company_headcount_latest` of 0 was silently treated as "a tiny
     company" instead of "unknown" — inflating false positives on a
     small-company predicate.
  2. An industry check aggregated across a candidate's WHOLE career, so a
     candidate currently at a non-tech company (e.g. legal services) could
     still satisfy "currently works at a technology company" purely because
     a PAST, unrelated employer happened to be tech-classified.
  3. "Reached a leadership title at some point" was conflated with
     "currently in a leadership role" — a candidate who reached Director
     years ago and has since moved to an individual-contributor title would
     incorrectly read as a current leader.

Nothing here is wired into retrieval, ranking, or any UI filter — these are
pure functions over already-available employment data (the same shape
CrustData's `experience.employment_details.current`/`past` entries already
have: title, company_headcount_latest, company_industries,
company_professional_network_industry, start_date, end_date). A future
search-translation layer can call these once a requirement like "worked at
a technology company" is extracted from recruiter intent — that extraction
itself is out of scope here.
"""

import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

# Same leadership vocabulary validated in the Search Logic Experiment.
# Kept private/internal, not a role-specific JD keyword list — this
# classifies a TITLE STRING as leadership-shaped in general, the same way a
# recruiter would read it, never a search-specific term.
_LEADERSHIP_TITLE_RE = re.compile(r"\b(lead|manager|head|director|vp|vice president|principal|chief)\b", re.I)
_IC_TITLE_RE = re.compile(r"\b(recruiter|sourcer|specialist|coordinator|associate|analyst)\b", re.I)


# ---------------------------------------------------------------------------
# Company size — an UNKNOWN headcount never satisfies a positive size check.
# ---------------------------------------------------------------------------

def known_headcount(value: Any) -> Optional[float]:
    """The employer's headcount as a real, known, positive number — or None
    (UNKNOWN) for 0, negative, missing, null, or any non-numeric/malformed
    value. 0 is explicitly UNKNOWN, never "a company of size zero": a real
    company employs at least one person, so 0 only ever means the field
    wasn't actually populated. A bool is rejected too (bool is a subclass of
    int in Python; True/False must never silently read as 1/0 headcount)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def is_small_company(headcount: Any, max_employees: float = 200) -> bool:
    """True only for a KNOWN headcount at or under the threshold. UNKNOWN
    (see known_headcount) is always False here — it never satisfies a
    positive size predicate, per spec."""
    known = known_headcount(headcount)
    return known is not None and known <= max_employees


def is_enterprise_company(headcount: Any, min_employees: float = 5000) -> bool:
    """True only for a KNOWN headcount at or over the threshold."""
    known = known_headcount(headcount)
    return known is not None and known >= min_employees


def worked_across_size_bands(
    events: Sequence[Dict[str, Any]],
    small_max: float = 200,
    enterprise_min: float = 5000,
) -> bool:
    """"Worked across small startups and large enterprises": there must be
    at least one event with a KNOWN small headcount AND at least one event
    (not necessarily the same one) with a KNOWN enterprise headcount. An
    event whose headcount is 0/null/missing/malformed contributes to
    neither side — it is simply not evidence, not a tie-breaker either way."""
    small_seen = False
    enterprise_seen = False
    for event in events:
        headcount = event.get("company_headcount_latest") if isinstance(event, dict) else None
        if is_small_company(headcount, small_max):
            small_seen = True
        if is_enterprise_company(headcount, enterprise_min):
            enterprise_seen = True
        if small_seen and enterprise_seen:
            return True
    return False


# ---------------------------------------------------------------------------
# Industry — scoped to the specific employment event(s) a requirement refers
# to, never aggregated across a candidate's whole career by default.
# ---------------------------------------------------------------------------

def _event_industries(event: Dict[str, Any]) -> List[str]:
    industries: List[str] = []
    if not isinstance(event, dict):
        return industries
    for value in event.get("company_industries") or []:
        if isinstance(value, str) and value.strip():
            industries.append(value.strip().lower())
    network_industry = event.get("company_professional_network_industry")
    if isinstance(network_industry, str) and network_industry.strip():
        industries.append(network_industry.strip().lower())
    return industries


def event_matches_industry(event: Dict[str, Any], keywords: Iterable[str]) -> bool:
    """True only if THIS event's own industry tags contain one of `keywords`
    (case-insensitive substring match). Never looks at any other event —
    scoping to a single employment event is the whole point of this
    function; a caller aggregating across events does so explicitly, by
    calling this once per event, never implicitly inside it."""
    keywords_lower = [k.lower() for k in keywords if isinstance(k, str) and k.strip()]
    if not keywords_lower:
        return False
    industries = _event_industries(event)
    return any(any(keyword in industry for keyword in keywords_lower) for industry in industries)


def _is_current_event(event: Dict[str, Any]) -> bool:
    """An event is current when it has no end date (or the source's own
    "present" text) — the same convention CrustData's `employment_details`
    lists already use (an entry in `.current[]` has `end_date: null`) and
    the same rule `_build_career` already applies. An explicit `is_current`
    key on the event, when present, always wins (lets a caller pass an
    already-classified list without relying on end_date parsing)."""
    if not isinstance(event, dict):
        return False
    if "is_current" in event:
        return bool(event["is_current"])
    end_date = event.get("end_date")
    if not end_date:
        return True
    return isinstance(end_date, str) and end_date.strip().lower() == "present"


def current_employer_matches_industry(events: Sequence[Dict[str, Any]], keywords: Iterable[str]) -> bool:
    """"Currently works at a technology company": only the CURRENT
    employment event(s) are checked. A past employer's industry — tech or
    not — has zero bearing here. This is the direct fix for the false
    positive the Search Logic Experiment found (a candidate's current,
    non-tech employer was overlooked because an unrelated past employer was
    tech-classified)."""
    current_events = [event for event in events if _is_current_event(event)]
    return any(event_matches_industry(event, keywords) for event in current_events)


def ever_matches_industry(events: Sequence[Dict[str, Any]], keywords: Iterable[str]) -> bool:
    """"Worked at a technology company" (unscoped): any single event, current
    or past, may satisfy it on its own."""
    return any(event_matches_industry(event, keywords) for event in events)


def _event_duration_years(event: Dict[str, Any]) -> float:
    """Best-effort, from whatever duration signal the event already carries
    — never derived from any other field. `years_at_company_raw` is
    CrustData's own pre-computed figure; an event with neither that nor an
    explicit `duration_years` contributes 0, not a guess."""
    if not isinstance(event, dict):
        return 0.0
    for key in ("duration_years", "years_at_company_raw"):
        value = event.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            return float(value)
    return 0.0


def years_in_industry(events: Sequence[Dict[str, Any]], keywords: Iterable[str]) -> float:
    """"Worked in technology for N years": sums duration ONLY across events
    that individually match `keywords` — a non-matching event contributes
    nothing, however long it lasted."""
    return sum(_event_duration_years(event) for event in events if event_matches_industry(event, keywords))


# ---------------------------------------------------------------------------
# Career progression — historical progression and current state are two
# different, never-conflated facts.
# ---------------------------------------------------------------------------

def is_leadership_title(title: Optional[str]) -> bool:
    return bool(title) and bool(_LEADERSHIP_TITLE_RE.search(title))


def is_ic_title(title: Optional[str]) -> bool:
    return bool(title) and bool(_IC_TITLE_RE.search(title)) and not is_leadership_title(title)


def _sort_key(event: Dict[str, Any]) -> str:
    start = event.get("start_date") if isinstance(event, dict) else None
    return start if isinstance(start, str) and start else "0000"


def historical_leadership_progression(events: Sequence[Dict[str, Any]]) -> bool:
    """True when an individual-contributor-shaped title appears at some
    point BEFORE a leadership-shaped title in the candidate's dated history
    — the pattern itself, independent of where the candidate stands today.
    Never requires monotonic progression (a step back afterward doesn't
    erase that the progression happened); never looks at whether the
    candidate is currently a leader — see currently_in_leadership for that,
    a deliberately separate question."""
    ordered = sorted([event for event in events if isinstance(event, dict)], key=_sort_key)
    ic_index = next((i for i, event in enumerate(ordered) if is_ic_title(event.get("title"))), None)
    if ic_index is None:
        return False
    return any(is_leadership_title(event.get("title")) for event in ordered[ic_index + 1 :])


def current_role(events: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The candidate's current employment event, if any — the one event
    `currently_in_leadership`/`current_employer_matches_industry` evaluate.
    When more than one event is flagged current (a provider quirk, not the
    normal case), the one with the latest start date wins; when none is
    flagged current, the most recently started event is used as a
    last-resort "current state" — still never treated as certain, callers
    that need to know may check `_is_current_event` themselves."""
    candidates = [event for event in events if isinstance(event, dict)]
    if not candidates:
        return None
    current_flagged = [event for event in candidates if _is_current_event(event)]
    pool = current_flagged or candidates
    return max(pool, key=_sort_key)


def currently_in_leadership(events: Sequence[Dict[str, Any]]) -> bool:
    """"Currently a recruiting leader": true only if the CURRENT role's own
    title is leadership-shaped. A candidate who reached Director years ago
    and has since moved to an individual-contributor title (the exact
    pattern the Search Logic Experiment found) correctly reads False here,
    even though historical_leadership_progression for the same candidate is
    True — the two questions are answered independently, on purpose."""
    role = current_role(events)
    if role is None:
        return False
    return is_leadership_title(role.get("title"))


def currently_leads_at_industry(events: Sequence[Dict[str, Any]], keywords: Iterable[str]) -> bool:
    """"Currently leads recruiting at a technology company": the CURRENT
    role must independently satisfy both the leadership condition and the
    industry condition — never a leadership title from one era combined
    with an industry tag from another."""
    role = current_role(events)
    if role is None:
        return False
    return is_leadership_title(role.get("title")) and event_matches_industry(role, keywords)
