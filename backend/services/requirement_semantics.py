"""Recognizes a small, explicit family of Core/Supporting/Differentiator
requirement sentences (company size, technology-industry, career
progression/state) and judges them DETERMINISTICALLY from career_signals.py,
instead of asking the LLM requirement judge to guess at them from prose.

Why this exists: the Search Logic Experiment showed these three questions
can be answered exactly from structured employment data already returned by
CrustData — an LLM reading generated prose about them would just reintroduce
the same imprecision (unknown-as-small, career-wide industry aggregation,
history-as-current) the experiment caught and career_signals.py already
fixed. This module is the bridge from a requirement's own free-text wording
to those existing, tested predicate functions — it adds no new predicate
logic of its own and duplicates none of career_signals.py's.

The flow is deliberately two steps, not one:

    requirement text -> recognize_requirement() -> SemanticRequirement -> evaluate() -> judgment

`recognize_requirement()` is purely "what does the recruiter mean" — it
answers that question once, into an explicit, typed SemanticRequirement
(family/scope/operator/value), and nothing after it re-interprets the
sentence again. `evaluate()` is purely "does this candidate satisfy this
already-explicit requirement" — it never looks at requirement text itself,
only at the SemanticRequirement's own fields plus the candidate's real
employment events. Keeping these separate is what lets a later release add
a new SemanticRequirement source (e.g. eventually from Confirmed Hiring
Intent extraction directly, bypassing text-recognition entirely) without
touching evaluate() at all.

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
not-implemented, future primitive — see the release report. No new
semantic family was added in this release; this is a representation
refactor only.
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

# --- Explicit semantic requirement representation --------------------------
#
# Every recognized requirement is one of these four families. "scope"
# distinguishes a claim about the CURRENT employment event from one about
# the whole career ("career" — historical/any, in either order); "operator"
# names which career_signals.py predicate answers it; "value"/"values" and
# "min_years" carry whatever parameter that operator needs. Nothing here is
# a general-purpose rules engine: every (family, operator) combination below
# is handled by exactly one, already-tested career_signals.py function, and
# evaluate() has exactly one branch per combination — adding a family means
# adding a branch, not extending a schema.

Family = Literal["company_size", "industry", "career_progression", "career_state"]
Scope = Literal["current", "career"]
Operator = Literal["matches", "worked_across", "duration_at_least", "currently_leadership", "historical_leadership_progression"]


@dataclass(frozen=True)
class SemanticRequirement:
    """What the recruiter means — nothing here says anything about whether
    any particular candidate satisfies it; see evaluate() for that."""

    text: str
    family: Family
    scope: Scope
    operator: Operator
    value: Optional[str] = None
    values: Optional[Tuple[str, ...]] = None
    min_years: Optional[float] = None


# The one industry family validated so far. Kept private and singular on
# purpose — see the module docstring.
_TECHNOLOGY_KEYWORDS = ["technology", "software", "it services", "information technology", "internet", "saas"]


# Conservative, explicit trigger phrases only. Every pattern requires the
# subject noun ("startup"/"enterprise"/"large company"/"technology company")
# to actually appear — a requirement that merely mentions a company by name,
# or an unrelated phrase that happens to share a word, never matches.
_CURRENT_QUALIFIER = r"(?:currently|presently|now)\s+(?:works?|is)\s+(?:at|for)|current(?:ly)?\s+employ(?:er|ment)\s+is"

# Requires an employer-scoping verb phrase ("works/worked at/for") right
# before the subject noun — "Experience working WITH startups" (an agency
# recruiter's clients, say, not necessarily the candidate's own employer) is
# a genuinely different, ambiguous claim and must stay unrecognized, per the
# explicit example in Task 5 of the wiring release. "working" (present
# participle) never matches \bworks?\b/\bworked\b, and "with" never matches
# \b(?:at|for)\b — both distinctions are load-bearing, not incidental.
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


def recognize_requirement(signal_text: str) -> Optional[SemanticRequirement]:
    """"What does the recruiter mean" — the ONLY place requirement text is
    interpreted. None for anything not unambiguously one of the three
    validated families; the caller must fall back to the existing LLM judge
    for everything else, including ambiguous scope-less wording."""
    text = (signal_text or "").strip()
    if not text:
        return None

    is_current = bool(_CURRENT_RE.search(text))

    duration_match = _TECH_DURATION_RE.search(text)
    if duration_match:
        return SemanticRequirement(text=text, family="industry", scope="career", operator="duration_at_least", value="technology", min_years=float(duration_match.group(1)))

    if _TECH_INDUSTRY_RE.search(text):
        return SemanticRequirement(text=text, family="industry", scope="current" if is_current else "career", operator="matches", value="technology")

    if _BOTH_RE.search(text):
        return SemanticRequirement(text=text, family="company_size", scope="career", operator="worked_across", values=("small", "large"))

    if _SMALL_RE.search(text):
        return SemanticRequirement(text=text, family="company_size", scope="current" if is_current else "career", operator="matches", value="small")

    if _LARGE_RE.search(text):
        return SemanticRequirement(text=text, family="company_size", scope="current" if is_current else "career", operator="matches", value="large")

    if _CURRENT_LEADERSHIP_RE.search(text):
        return SemanticRequirement(text=text, family="career_state", scope="current", operator="currently_leadership")

    if _HISTORICAL_PROGRESSION_RE.search(text):
        return SemanticRequirement(text=text, family="career_progression", scope="career", operator="historical_leadership_progression")

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


def _evaluate_company_size_matches(requirement: SemanticRequirement, tier: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    is_match = is_small_company if requirement.value == "small" else is_enterprise_company
    threshold = "at or under 200" if requirement.value == "small" else "at or over 5,000"
    pool = [current_role(events)] if requirement.scope == "current" and current_role(events) else events
    pool = [e for e in pool if e]
    match = _first_matching(pool, lambda e: is_match(e.get("company_headcount_latest")))
    scope_note = "current employer" if requirement.scope == "current" else "an employer in the career history"
    return _judgment(
        tier, requirement.text, met=bool(match),
        quote=_quote_for_size_event(match) if match else "",
        evidence_detail=f"Known headcount at {scope_note}, {threshold} employees." if match else "",
    )


def _evaluate_company_size_worked_across(requirement: SemanticRequirement, tier: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    met = worked_across_size_bands(events)
    small = _first_matching(events, lambda e: is_small_company(e.get("company_headcount_latest")))
    large = _first_matching(events, lambda e: is_enterprise_company(e.get("company_headcount_latest")))
    quote = f"{_quote_for_size_event(small)}; {_quote_for_size_event(large)}" if met else ""
    return _judgment(tier, requirement.text, met=met, quote=quote, evidence_detail="Known headcount evidence for both a small (<=200) and a large (>=5,000) employer." if met else "")


def _evaluate_industry_matches(requirement: SemanticRequirement, tier: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    if requirement.scope == "current":
        role = current_role(events)
        met = bool(role) and event_matches_industry(role, _TECHNOLOGY_KEYWORDS)
        quote = _quote_for_industry_event(role) if met else ""
        detail = "The current employer's own industry classification names technology/software." if met else ""
    else:
        match = _first_matching(events, lambda e: event_matches_industry(e, _TECHNOLOGY_KEYWORDS))
        met = bool(match)
        quote = _quote_for_industry_event(match) if match else ""
        detail = "At least one employer in the career history is classified as technology/software." if met else ""
    return _judgment(tier, requirement.text, met=met, quote=quote, evidence_detail=detail)


def _evaluate_industry_duration(requirement: SemanticRequirement, tier: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    years = years_in_industry(events, _TECHNOLOGY_KEYWORDS)
    met = requirement.min_years is not None and years >= requirement.min_years
    matches = [e for e in events if event_matches_industry(e, _TECHNOLOGY_KEYWORDS)]
    companies = ", ".join(sorted({e.get("name") for e in matches if e.get("name")})) or "technology-classified employers"
    quote = f"About {years:g} years across technology-classified employers ({companies})." if met else ""
    detail = "Summed duration across employment events individually classified as technology/software." if met else ""
    return _judgment(tier, requirement.text, met=met, quote=quote, evidence_detail=detail)


def _evaluate_career_progression_historical(requirement: SemanticRequirement, tier: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    met = historical_leadership_progression(events)
    quote = ""
    if met:
        ordered = sorted(events, key=lambda e: e.get("start_date") or "0000")
        ic_event = _first_matching(ordered, lambda e: is_ic_title(e.get("title")))
        ic_index = ordered.index(ic_event) if ic_event else -1
        leadership_event = _first_matching(ordered[ic_index + 1 :], lambda e: is_leadership_title(e.get("title"))) if ic_index >= 0 else None
        if ic_event and leadership_event:
            quote = f"{ic_event.get('title')} at {ic_event.get('name')} → {leadership_event.get('title')} at {leadership_event.get('name')}"
    return _judgment(tier, requirement.text, met=met, quote=quote, evidence_detail="An individual-contributor-shaped title appears before a leadership-shaped title in the dated career history." if met else "")


def _evaluate_career_state_currently_leadership(requirement: SemanticRequirement, tier: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    met = currently_in_leadership(events)
    role = current_role(events) if met else None
    quote = f"{role.get('title')} at {role.get('name')} (current)" if role else ""
    return _judgment(tier, requirement.text, met=met, quote=quote, evidence_detail="The current employment event's own title is leadership-shaped." if met else "")


# One entry per (family, operator) this module actually handles — adding a
# new family means adding one entry here, never touching the dispatch logic.
_EVALUATORS = {
    ("company_size", "matches"): _evaluate_company_size_matches,
    ("company_size", "worked_across"): _evaluate_company_size_worked_across,
    ("industry", "matches"): _evaluate_industry_matches,
    ("industry", "duration_at_least"): _evaluate_industry_duration,
    ("career_progression", "historical_leadership_progression"): _evaluate_career_progression_historical,
    ("career_state", "currently_leadership"): _evaluate_career_state_currently_leadership,
}


def evaluate(requirement: SemanticRequirement, tier: str, candidate: Candidate) -> Dict[str, Any]:
    """"Does this candidate satisfy this already-explicit requirement" — the
    full judgment dict, in requirement_judge's existing shape. Never
    re-reads `requirement.text` for meaning (only recognize_requirement()
    does that); never fabricates a quote — every quote/evidence_detail here
    is built only from fields literally present on the specific employment
    event(s) that made the verdict true, and a False verdict carries no
    quote at all, the same as requirement_judge's own not_evidenced shape."""
    handler = _EVALUATORS.get((requirement.family, requirement.operator))
    if handler is None:
        raise AssertionError(f"Unhandled semantic requirement: family={requirement.family} operator={requirement.operator}")
    return handler(requirement, tier, employment_events(candidate))
