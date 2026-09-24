"""The Candidate Evidence layer — a structured, typed view over whatever a
provider's raw response actually contained for a candidate, built to sit
between the provider and ranking/explanation/UI. It never invents a fact:
every populated field traces back to something the provider literally
returned; everything the provider didn't return shows up in `uncertainty`,
never as a guessed value or a false negative.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, NamedTuple, Optional, Tuple


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
class CareerEntry:
    """One role on the candidate record. From the full profile read when there
    is one (it carries descriptions), otherwise from the search data (titles
    and dates only). Dates are display text ("Jul 2024"), exactly as the
    source gave them."""

    title: str
    company: str
    start: Optional[str] = None
    end: Optional[str] = None
    current: bool = False
    duration: Optional[str] = None
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
    # PASS 4 (evidence quality): what KIND of evidence this is, independent
    # of the JD-priority `tier` above — see backend/services/
    # candidate_evidence_builder.py's TextSource metadata. One of
    # "demonstrated_work" | "certification" | "named_skill" | "title_history"
    # | "headline". Drives the STRONG/SUPPORTING hierarchy in `strength`.
    evidence_type: str = ""
    # The actual contextual quote the match was found in — a real sentence
    # from an employment/project description, or the short source text
    # itself for title/headline/cert/skill sources. Never just the bare
    # matched word — "a matched word is not evidence" (PASS 4). This is what
    # MatchExplainer renders to the recruiter instead of `matched_term`.
    evidence_text: str = ""
    # "strong" (demonstrated work in an employment description/project, or a
    # third-party certification) | "supporting" (a named skill, a headline,
    # or career/title history) — see PART 3 of the PASS 4 evidence-quality
    # spec. Never influences ranking weight (CandidateRanker still keys off
    # `tier`, unchanged) — this is presentation/trust metadata only.
    strength: str = ""


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
    # Two different facts, kept apart. The experience floor is arithmetic:
    # do the dated roles add up to the years the search asked for. Level fit
    # is a judgement about the title(s) against the target seniority:
    # "aligned" | "above" | "below" | "unclear", None when the search states
    # no target seniority. Neither is a hiring decision; "above" means the
    # profile MAY indicate a level higher than the target.
    experience_floor: Optional[bool] = None
    experience_floor_basis: str = ""
    level_fit: Optional[str] = None
    level_basis: str = ""


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
    # How many times the profile was requested (2 = the one malformed-response retry was used).
    attempts: int = 1


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
    # Total time covered by the employment dates on record (overlaps merged,
    # a current role counted up to today), in years. DERIVED from dates —
    # never a provider-returned field and never the candidate's own claim.
    # None when no role has a parseable start date.
    derived_experience_years: Optional[float] = None
    # Candidate record (Release 2) - display data only; none of it feeds ranking.
    # Photo: the search provider's stable image link first, the full-profile
    # read's photo as the fallback. open_to_work is set ONLY from the profile
    # read's own flag and is None (not False) when unknown; it is shown as a
    # neutral chip when true and never used in ranking.
    photo_url: Optional[str] = None
    open_to_work: Optional[bool] = None
    career: List[CareerEntry] = field(default_factory=list)
    # Verified requirement judgments (see backend/services/requirement_judge.py).
    # None = no judge ran for this candidate, so role_alignment falls back to
    # deterministic term matching; a list (possibly empty) = the judge ran and
    # role_alignment reflects ONLY judgments whose quote was verified against
    # the profile text.
    requirement_judgments: Optional[List[Dict[str, Any]]] = None

    def labeled_text_sources(self) -> List["TextSource"]:
        """Where signal-matching is allowed to look for literal evidence.
        Each entry's `label` is the internal provenance tag (never shown to
        a recruiter verbatim; MatchExplainer turns it into a natural
        sentence using `detail`/`evidence_text` instead), `text` is what
        contextual term-matching runs against, and `detail` is the human-
        readable item name (a certification title, project title, or
        "<title> at <company>") used to phrase that sentence — empty for
        CrustData sources, where the source label is already descriptive
        enough on its own.

        Order is STRENGTH-first, not discovery order (PASS 4 / PART 7 —
        "the strongest evidence source should determine the evidence
        strength"): demonstrated-work sources (Harvest employment
        descriptions, projects, certifications) are checked before
        supporting sources (current title, headline, past-role titles,
        Harvest named skills), so when the same concept is corroborated in
        both a strong and a supporting source, the resulting single
        MatchedSignal is attributed — and worded — from the strong one.

        Company/function industry tags are corporate classification
        strings (e.g. "Technology, Information and Internet"), not a
        description of the candidate's own skills, and were found to
        produce spurious matches (e.g. the word "information" from an
        employer's industry tag being counted as evidence of "information
        retrieval" expertise) — excluded for that reason, not merely for
        stoplist coverage. `about` is deliberately never included here —
        self-authored/unverified text must never feed signal-matching or
        ranking. Follower/connection counts, `openToWork`/`hiring` flags,
        and other profile metadata are never part of this list at all —
        they were never extracted into any evidence field to begin with."""
        sources: List[TextSource] = []
        for role_label, text in self.harvest_employment_descriptions:
            sources.append(TextSource("harvest: employment description", text, role_label, "demonstrated_work", "strong"))
        for title, description in self.harvest_projects:
            sources.append(TextSource("harvest: project", f"{title} {description}", title, "demonstrated_work", "strong"))
        for cert in self.harvest_certifications:
            sources.append(TextSource("harvest: certification", cert, cert, "certification", "strong"))
        if self.current_title:
            sources.append(TextSource("current title", self.current_title, "", "title_history", "supporting"))
        if self.headline:
            sources.append(TextSource("headline", self.headline, "", "headline", "supporting"))
        for role in self.past_roles:
            if role.title:
                label = f"past role: {role.title} at {role.company}" if role.company else f"past role: {role.title}"
                sources.append(TextSource(label, role.title, "", "title_history", "supporting"))
        for skill in self.harvest_skills:
            sources.append(TextSource("harvest: skill", skill, skill, "named_skill", "supporting"))
        return sources


class TextSource(NamedTuple):
    """One place signal-matching is allowed to search, plus the evidence
    metadata that place implies. `evidence_type` is one of
    "demonstrated_work" | "certification" | "named_skill" | "title_history"
    | "headline"; `strength` is "strong" | "supporting" — see PART 3 of the
    PASS 4 evidence-quality spec and MatchedSignal above."""

    label: str
    text: str
    detail: str
    evidence_type: str
    strength: str
