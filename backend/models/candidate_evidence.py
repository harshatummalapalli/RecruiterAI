"""The Candidate Evidence layer — a structured, typed view over whatever a
provider's raw response actually contained for a candidate, built to sit
between the provider and ranking/explanation/UI. It never invents a fact:
every populated field traces back to something the provider literally
returned; everything the provider didn't return shows up in `uncertainty`,
never as a guessed value or a false negative.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


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
    source: str = ""  # "current title" | "headline" | "past role: <title> at <company>" | "harvest: employment description" | "harvest: project" | "harvest: certification" | "harvest: skill"
    # The human-readable item this came from, for phrasing a natural
    # sentence without exposing the source label verbatim (e.g. the actual
    # certification title, project title, or "<title> at <company>" for an
    # employment description) — "" for CrustData sources, where the source
    # label itself is already descriptive enough.
    evidence_detail: str = ""


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
class HarvestEvidence:
    """The raw HarvestAPI (harvestapi.io) LinkedIn-profile response for one
    candidate, plus call metadata. Never merged destructively into the
    CrustData raw payload — this is a wholly separate, additive record.
    `success=False` (missing profile URL, timeout, rate limit, API error,
    malformed response — see harvest_enrichment.py) means the candidate
    simply continues on CrustData-only evidence; a failed enrichment is
    never treated as negative evidence about the candidate."""

    raw: Dict[str, Any] = field(default_factory=dict)
    fetched_at: Optional[str] = None
    success: bool = False
    cost: Optional[float] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None  # short machine-readable reason when success is False


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

    # Second-stage enrichment (see backend/services/harvest_enrichment.py).
    # None until a search's top-N enrichment step has run for this
    # candidate; never destructively merged with CrustData fields above.
    harvest: Optional[HarvestEvidence] = None
    # Structured extraction from Harvest's `experience[].description`,
    # `projects[]`, `certifications[]`, `skills[]`/`topSkills` — populated
    # by harvest_enrichment.py's normalization step, never by hand. Kept
    # separate from the CrustData-derived fields above so raw provenance
    # stays traceable per field.
    harvest_employment_descriptions: List[Tuple[str, str]] = field(default_factory=list)  # (role label, text)
    harvest_projects: List[Tuple[str, str]] = field(default_factory=list)  # (title, description)
    harvest_certifications: List[str] = field(default_factory=list)
    harvest_skills: List[str] = field(default_factory=list)
    # Self-authored, unverified — see build_candidate_evidence's
    # apply_harvest_evidence(). Never fed into signal-matching/ranking;
    # explanation-only, and always presented as self-reported.
    harvest_about: Optional[str] = None
    harvest_self_reported_experience: Optional[str] = None

    def labeled_text_sources(self) -> List[Tuple[str, str, str]]:
        """Where signal-matching is allowed to look for literal evidence.
        Each entry is (source_label, searchable_text, display_detail) —
        source_label is the internal provenance tag (never shown to a
        recruiter verbatim; MatchExplainer turns it into a natural sentence
        using display_detail instead), searchable_text is what the literal
        term-matching runs against, and display_detail is the human-
        readable item name (a certification title, project title, or
        "<title> at <company>") used to phrase that sentence — empty for
        CrustData sources, where the source label is already descriptive
        enough on its own.

        Order is priority order (most-demonstrated evidence checked first,
        so a term found in multiple places is attributed to the strongest
        one — see Phase 5 of the Harvest integration plan): CrustData
        title/headline/past-titles, then Harvest employment descriptions,
        projects, certifications, skills.

        Company/function industry tags are corporate classification
        strings (e.g. "Technology, Information and Internet"), not a
        description of the candidate's own skills, and were found to
        produce spurious matches (e.g. the word "information" from an
        employer's industry tag being counted as evidence of "information
        retrieval" expertise) — excluded for that reason, not merely for
        stoplist coverage. `about` is deliberately never included here —
        self-authored/unverified text must never feed signal-matching or
        ranking."""
        sources: List[Tuple[str, str, str]] = []
        if self.current_title:
            sources.append(("current title", self.current_title, ""))
        if self.headline:
            sources.append(("headline", self.headline, ""))
        for role in self.past_roles:
            if role.title:
                label = f"past role: {role.title} at {role.company}" if role.company else f"past role: {role.title}"
                sources.append((label, role.title, ""))
        for role_label, text in self.harvest_employment_descriptions:
            sources.append(("harvest: employment description", text, role_label))
        for title, description in self.harvest_projects:
            sources.append(("harvest: project", f"{title} {description}", title))
        for cert in self.harvest_certifications:
            sources.append(("harvest: certification", cert, cert))
        for skill in self.harvest_skills:
            sources.append(("harvest: skill", skill, skill))
        return sources
