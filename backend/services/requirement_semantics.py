"""Recognizes a small, explicit family of Core/Supporting/Differentiator
requirement sentences (company size, technology-industry, career
progression) and judges them DETERMINISTICALLY from career_signals.py,
instead of asking the LLM requirement judge to guess at them from prose.

Why this exists: the Search Logic Experiment showed these three questions
can be answered exactly from structured employment data already returned by
CrustData — an LLM reading generated prose about them would just reintroduce
the same imprecision (unknown-as-small, career-wide industry aggregation,
history-as-current) the experiment caught and career_signals.py already
fixed. This module is the bridge from a requirement's own free-text wording
to those existing, tested predicate functions — it adds no new predicate
logic of its own and duplicates none of career_signals.py's.

Recognition is deliberately conservative and narrow: an unrecognized
sentence (including anything ambiguous, like "Experience working with
startups" with no "currently"/"current" qualifier) is left completely alone
and falls through to the existing LLM requirement_judge path unchanged. A
requirement is only ever answered here when its wording unambiguously names
one of the three validated patterns; recognizing MORE than that would be
inventing a new interpretation system, not wiring an existing one — out of
scope by design.

Only the technology industry is recognized (the one family actually
validated end-to-end in the Search Logic Experiment and the acceptance
runs). Generalizing to arbitrary recruiter-named industries is a documented,
not-implemented, future primitive — see the release report.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from backend.models.candidate import Candidate
from backend.services.career_signals import (
    current_employer_matches_industry,
    current_role,
    currently_in_leadership,
    ever_matches_industry,
    event_matches_industry,
    historical_leadership_progression,
    is_ic_title,
    is_leadership_title,
    is_small_company,
    is_enterprise_company,
    known_headcount,
    worked_across_size_bands,
    years_in_industry,
)

Scope = Literal["current", "any"]

# The one industry family validated so far. Kept private and singular on
# purpose — see the module docstring.
_TECHNOLOGY_KEYWORDS = ["technology", "software", "it services", "information technology", "internet", "saas"]


@dataclass
class RecognizedRequirement:
    kind: Literal["company_size_small", "company_size_large", "company_size_both", "industry", "industry_duration", "career_progression_historical", "career_progression_current"]
    scope: Scope = "any"
    min_years: Optional[float] = None


# Conservative, explicit trigger phrases only. Every pattern requires the
# subject noun ("startup"/"enterprise"/"large company"/"technology company")
# to actually appear — a requirement that merely mentions a company by name,
# or an unrelated phrase that happens to share a word, never matches.
_CURRENT_QUALIFIER = r"(?:currently|presently|now)\s+(?:works?|is)\s+(?:at|for)|current(?:ly)?\s+employ(?:er|ment)\s+is"

# Requires an employer-scoping verb phrase ("works/worked at/for") right
# before the subject noun — "Experience working WITH startups" (an agency
# recruiter's clients, say, not necessarily the candidate's own employer) is
# a genuinely different, ambiguous claim and must stay unrecognized, per the
# explicit example in Task 5. "working" (present participle) never matches
# \bworks?\b/\bworked\b, and "with" never matches \b(?:at|for)\b — both
# distinctions are load-bearing, not incidental.
_AT_FOR = r"\b(?:works?|worked|employ(?:ed|ment))\b(?:\s+\w+){0,3}?\s+\b(?:at|for)\b"
_SMALL_RE = re.compile(rf"{_AT_FOR}\s+(?:a\s+|an\s+)?startups?\b|{_AT_FOR}\s+(?:a\s+)?small\s+compan(?:y|ies)\b", re.I)
_LARGE_RE = re.compile(rf"{_AT_FOR}\s+(?:a\s+|an\s+)?(?:large\s+)?enterprises?\b|{_AT_FOR}\s+(?:a\s+)?large\s+compan(?:y|ies)\b", re.I)
_BOTH_RE = re.compile(r"(startups?|small\s+compan(?:y|ies)).{0,40}\band\b.{0,40}(enterprises?|large\s+compan(?:y|ies))", re.I)
_TECH_INDUSTRY_RE = re.compile(rf"{_AT_FOR}\s+(?:a\s+|an\s+)?(?:technology|tech|software)\s+compan(?:y|ies)\b", re.I)
_TECH_DURATION_RE = re.compile(r"\bin\s+(?:the\s+)?(?:technology|tech|software)\b.{0,20}\bfor\b.{0,10}(\d+(?:\.\d+)?)\+?\s*years?", re.I)
_CURRENT_RE = re.compile(_CURRENT_QUALIFIER, re.I)
_HISTORICAL_PROGRESSION_RE = re.compile(
    r"progress(?:ed|ion)\b.{0,60}\b(leader|leadership|manager|management)\b|"
    r"\b(recruiter|individual\s+contributor|\bic\b)\b.{0,40}\bto\b.{0,40}\b(leader|leadership|manager|director)\b",
    re.I,
)
_CURRENT_LEADERSHIP_RE = re.compile(
    r"currently\s+(?:a\s+)?(?:recruiting\s+)?leader|currently\s+leads?\b|currently\s+(?:a\s+)?(?:recruiting\s+)?manager",
    re.I,
)


def recognize_requirement(signal_text: str) -> Optional[RecognizedRequirement]:
    """None for anything not unambiguously one of the three validated
    families — the caller must fall back to the existing LLM judge for
    everything else, including ambiguous scope-less wording."""
    text = (signal_text or "").strip()
    if not text:
        return None

    is_current = bool(_CURRENT_RE.search(text))

    duration_match = _TECH_DURATION_RE.search(text)
    if duration_match:
        return RecognizedRequirement(kind="industry_duration", min_years=float(duration_match.group(1)))

    if _TECH_INDUSTRY_RE.search(text):
        return RecognizedRequirement(kind="industry", scope="current" if is_current else "any")

    if _BOTH_RE.search(text):
        return RecognizedRequirement(kind="company_size_both", scope="any")

    if _SMALL_RE.search(text):
        return RecognizedRequirement(kind="company_size_small", scope="current" if is_current else "any")

    if _LARGE_RE.search(text):
        return RecognizedRequirement(kind="company_size_large", scope="current" if is_current else "any")

    if _CURRENT_LEADERSHIP_RE.search(text):
        return RecognizedRequirement(kind="career_progression_current")

    if _HISTORICAL_PROGRESSION_RE.search(text):
        return RecognizedRequirement(kind="career_progression_historical")

    return None


def employment_events(candidate: Candidate) -> List[Dict[str, Any]]:
    """The raw employment events career_signals.py's functions expect
    (title, company_headcount_latest, company_industries, dates) — read
    directly from the candidate's raw CrustData payload, the only place
    past-role headcount actually lives (CandidateEvidence's PastRole does
    not carry it). Never a network call; the same raw_data every other
    reader (candidate_evidence_builder) already uses."""
    raw = candidate.raw_data or {}
    experience = raw.get("experience") if isinstance(raw.get("experience"), dict) else {}
    employment_details = experience.get("employment_details") if isinstance(experience.get("employment_details"), dict) else {}
    current = employment_details.get("current") or []
    past = employment_details.get("past") or []
    events = [e for e in (list(current) + list(past)) if isinstance(e, dict)]
    return events


def _quote_for_size_event(event: Dict[str, Any]) -> str:
    company = event.get("name") or "This employer"
    headcount = known_headcount(event.get("company_headcount_latest"))
    return f"{company} — {int(headcount):,} employees"


def _quote_for_industry_event(event: Dict[str, Any]) -> str:
    company = event.get("name") or "This employer"
    industries = [i for i in (event.get("company_industries") or []) if isinstance(i, str)]
    network_industry = event.get("company_professional_network_industry")
    if isinstance(network_industry, str) and network_industry not in industries:
        industries = industries + [network_industry]
    label = ", ".join(industries) if industries else "industry not returned"
    return f"{company} — industry: {label}"


def _first_matching(events: Sequence[Dict[str, Any]], predicate) -> Optional[Dict[str, Any]]:
    for event in events:
        if predicate(event):
            return event
    return None


def _judgment(tier: str, text: str, *, met: bool, quote: str, evidence_detail: str) -> Dict[str, Any]:
    return {
        "tier": tier,
        "signal_text": text,
        "verdict": "met" if met else "not_evidenced",
        "quote": quote if met else "",
        "term": quote if met else "",
        "source": "employment record",
        "evidence_detail": evidence_detail,
        "evidence_type": "title_history",
        "strength": "supporting",
        "deterministic": True,
    }


def evaluate(recognized: RecognizedRequirement, tier: str, text: str, candidate: Candidate) -> Dict[str, Any]:
    """The full judgment dict, in requirement_judge's existing shape, for one
    already-recognized requirement against one candidate's real employment
    events. Never fabricates a quote: every quote/evidence_detail here is
    built only from fields literally present on the specific employment
    event(s) that made the verdict true; a False verdict carries no quote at
    all, the same as requirement_judge's own not_evidenced shape."""
    events = employment_events(candidate)

    if recognized.kind == "company_size_small":
        pool = [current_role(events)] if recognized.scope == "current" and current_role(events) else events
        pool = [e for e in pool if e]
        match = _first_matching(pool, lambda e: is_small_company(e.get("company_headcount_latest")))
        scope_note = "current employer" if recognized.scope == "current" else "an employer in the career history"
        return _judgment(tier, text, met=bool(match), quote=_quote_for_size_event(match) if match else "", evidence_detail=f"Known headcount at {scope_note}, at or under 200 employees." if match else "")

    if recognized.kind == "company_size_large":
        pool = [current_role(events)] if recognized.scope == "current" and current_role(events) else events
        pool = [e for e in pool if e]
        match = _first_matching(pool, lambda e: is_enterprise_company(e.get("company_headcount_latest")))
        scope_note = "current employer" if recognized.scope == "current" else "an employer in the career history"
        return _judgment(tier, text, met=bool(match), quote=_quote_for_size_event(match) if match else "", evidence_detail=f"Known headcount at {scope_note}, at or over 5,000 employees." if match else "")

    if recognized.kind == "company_size_both":
        met = worked_across_size_bands(events)
        small = _first_matching(events, lambda e: is_small_company(e.get("company_headcount_latest")))
        large = _first_matching(events, lambda e: is_enterprise_company(e.get("company_headcount_latest")))
        quote = f"{_quote_for_size_event(small)}; {_quote_for_size_event(large)}" if met else ""
        return _judgment(tier, text, met=met, quote=quote, evidence_detail="Known headcount evidence for both a small (<=200) and a large (>=5,000) employer." if met else "")

    if recognized.kind == "industry":
        if recognized.scope == "current":
            role = current_role(events)
            met = bool(role) and event_matches_industry(role, _TECHNOLOGY_KEYWORDS)
            quote = _quote_for_industry_event(role) if met else ""
            detail = "The current employer's own industry classification names technology/software." if met else ""
        else:
            match = _first_matching(events, lambda e: event_matches_industry(e, _TECHNOLOGY_KEYWORDS))
            met = bool(match)
            quote = _quote_for_industry_event(match) if match else ""
            detail = "At least one employer in the career history is classified as technology/software." if met else ""
        return _judgment(tier, text, met=met, quote=quote, evidence_detail=detail)

    if recognized.kind == "industry_duration":
        years = years_in_industry(events, _TECHNOLOGY_KEYWORDS)
        met = recognized.min_years is not None and years >= recognized.min_years
        matches = [e for e in events if event_matches_industry(e, _TECHNOLOGY_KEYWORDS)]
        companies = ", ".join(sorted({e.get("name") for e in matches if e.get("name")})) or "technology-classified employers"
        quote = f"About {years:g} years across technology-classified employers ({companies})." if met else ""
        detail = "Summed duration across employment events individually classified as technology/software." if met else ""
        return _judgment(tier, text, met=met, quote=quote, evidence_detail=detail)

    if recognized.kind == "career_progression_historical":
        met = historical_leadership_progression(events)
        quote = ""
        if met:
            ordered = sorted(events, key=lambda e: e.get("start_date") or "0000")
            ic_event = _first_matching(ordered, lambda e: is_ic_title(e.get("title")))
            ic_index = ordered.index(ic_event) if ic_event else -1
            leadership_event = _first_matching(ordered[ic_index + 1 :], lambda e: is_leadership_title(e.get("title"))) if ic_index >= 0 else None
            if ic_event and leadership_event:
                quote = f"{ic_event.get('title')} at {ic_event.get('name')} → {leadership_event.get('title')} at {leadership_event.get('name')}"
        return _judgment(tier, text, met=met, quote=quote, evidence_detail="An individual-contributor-shaped title appears before a leadership-shaped title in the dated career history." if met else "")

    if recognized.kind == "career_progression_current":
        met = currently_in_leadership(events)
        role = current_role(events) if met else None
        quote = f"{role.get('title')} at {role.get('name')} (current)" if role else ""
        return _judgment(tier, text, met=met, quote=quote, evidence_detail="The current employment event's own title is leadership-shaped." if met else "")

    raise AssertionError(f"Unhandled recognized requirement kind: {recognized.kind}")
