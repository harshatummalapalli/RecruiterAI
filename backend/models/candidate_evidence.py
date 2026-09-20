"""The Candidate Evidence layer — a structured, typed view over whatever a
provider's raw response actually contained for a candidate, built to sit
between the provider and ranking/explanation/UI. It never invents a fact:
every populated field traces back to something the provider literally
returned; everything the provider didn't return shows up in `uncertainty`,
never as a guessed value or a false negative.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class PastRole:
    title: str
    company: str
    industries: List[str] = field(default_factory=list)
    function: Optional[str] = None
    seniority: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None


@dataclass
class EducationEntry:
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None


@dataclass
class ContactEvidence:
    email: Optional[str] = None
    phone: Optional[str] = None
    has_business_email: Optional[bool] = None


@dataclass
class MatchedSignal:
    """One literal, defensible piece of textual evidence: a Core/Supporting/
    Differentiator sentence from the Confirmed Hiring Intent for THIS search,
    paired with the specific term that was actually found in the candidate's
    own title/headline/career-history text. Never a guess — `matched_term`
    is always a substring that is really there. `tier` is an internal
    ranking-weight bucket (see CandidateRanker) and must never be surfaced
    to a recruiter verbatim; `source` (e.g. "headline", "past role: Data
    Analyst at Acme") is what should actually be shown — it says WHERE the
    evidence came from, which is what makes an explanation trustworthy."""

    tier: str  # "core" | "supporting" | "differentiator" — internal only
    signal_text: str
    matched_term: str
    source: str = ""  # "current title" | "headline" | "past role: <title> at <company>"


@dataclass
class RoleAlignment:
    """Derived entirely from the Confirmed Hiring Intent for the search that
    surfaced this candidate — never from a hardcoded, role-specific keyword
    table. The same code path evaluates a Backend Engineer search and a Lead
    Data Analyst search identically; only the intent's own content differs."""

    title_relevance: str  # "direct" | "adjacent" | "tangential" | "unclear"
    title_relevance_basis: str
    seniority_alignment: Optional[bool]  # True/False when evidence exists, None when unknown
    seniority_alignment_basis: str
    matched_signals: List[MatchedSignal] = field(default_factory=list)
    unmatched_signals: List[MatchedSignal] = field(default_factory=list)  # matched_term is "" here


@dataclass
class SearchEvidence:
    matched_queries: List[str] = field(default_factory=list)
    convergence: bool = False
    provider_fit: Optional[str] = None  # "strong" | "weak" | None (not returned for this candidate)


@dataclass
class UncertaintyNote:
    field: str
    note: str


@dataclass
class CandidateEvidence:
    candidate_id: str
    name: str
    current_title: str
    headline: str
    profile_url: Optional[str]
    location: str

    current_company: str
    current_industries: List[str] = field(default_factory=list)
    current_function: Optional[str] = None
    current_seniority: Optional[str] = None
    current_headcount: Optional[str] = None
    current_company_type: Optional[str] = None

    past_roles: List[PastRole] = field(default_factory=list)
    education: List[EducationEntry] = field(default_factory=list)
    contact: ContactEvidence = field(default_factory=ContactEvidence)

    search_evidence: SearchEvidence = field(default_factory=SearchEvidence)
    role_alignment: Optional[RoleAlignment] = None
    updated_at: Optional[str] = None

    uncertainty: List[UncertaintyNote] = field(default_factory=list)

    def labeled_text_sources(self) -> List[Tuple[str, str]]:
        """Where signal-matching is allowed to look for literal evidence,
        each piece labeled with where it came from — deliberately narrowed
        to title/headline/past-title text only. Company/function industry
        tags are corporate classification strings (e.g. "Technology,
        Information and Internet"), not a description of the candidate's
        own skills, and were found to produce spurious matches (e.g. the
        word "information" from an employer's industry tag being counted as
        evidence of "information retrieval" expertise) — excluded here for
        that reason, not merely for stoplist coverage."""
        sources: List[Tuple[str, str]] = []
        if self.current_title:
            sources.append(("current title", self.current_title))
        if self.headline:
            sources.append(("headline", self.headline))
        for role in self.past_roles:
            if role.title:
                label = f"past role: {role.title} at {role.company}" if role.company else f"past role: {role.title}"
                sources.append((label, role.title))
        return sources
