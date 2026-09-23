from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FieldValue:
    value: Optional[str] = None
    evidence: Optional[str] = None
    source: Optional[str] = None


@dataclass
class CapabilityItem:
    value: str
    tier_signal: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class TechnologyGroup:
    """A purely factual inventory entry — every technology named anywhere in
    the input, grouped by category, with NO required/preferred/differentiator
    classification. Deliberately separate from CapabilityItem/tier_signal,
    which is the interpretive, search-oriented view of the same JD."""

    category: str
    items: List[str] = field(default_factory=list)


@dataclass
class LocationEntry:
    """A structured location as extracted by Task A. Never contains work-mode
    or commute-frequency language (that belongs on ExplicitConstraints.
    work_mode only) — see the forensic investigation into free-text location
    strings reaching CrustData as an unmatchable exact-filter value."""

    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None


@dataclass
class ExplicitConstraints:
    # Structured, possibly multiple (e.g. "New York or Austin"). Never a
    # free-text sentence — see LocationEntry.
    locations: List[LocationEntry] = field(default_factory=list)
    work_mode: Optional[str] = None
    experience_minimum_years: Optional[int] = None
    experience_maximum_years: Optional[int] = None
    employment_type: Optional[str] = None
    exclusions: List[str] = field(default_factory=list)


@dataclass
class RoleUnderstanding:
    """Task A output — what the company is actually trying to hire. Carries
    no recruiter decisions; see IntakeDecision for those."""

    # The literal title line as written in the input — a plain fact, never an
    # interpretation. Kept distinct from primary_candidate_identity (Task A's
    # synthesized understanding of who is actually being hired), which may
    # legitimately differ from it (see role_interpretation).
    posted_title: Optional[str] = None
    primary_candidate_identity: FieldValue = field(default_factory=FieldValue)
    # The company actually doing the hiring (the employer), not the
    # candidate's own current employer — set only when genuinely
    # identifiable from the text (a named employer, "Join <Company>",
    # letterhead/signature), never guessed. Drives a default
    # exclude-current-employees-of-this-company filter — see
    # backend/services/search_translator.py's build_confirmed_hiring_intent.
    hiring_company: FieldValue = field(default_factory=FieldValue)
    candidate_archetype: FieldValue = field(default_factory=FieldValue)
    # A 2-3 sentence, evidence-grounded explanation of what the role actually
    # is, why (citing specific JD evidence), what obvious confusion a
    # recruiter might have (e.g. a misleading title), and why it matters for
    # the search — the main teaching-grade content of the brief. Distinct
    # from the short, optional Recruiter Insight (IntakeIssue.insight_text),
    # which is reserved for one specific non-obvious call, not the main
    # explanation.
    role_interpretation: FieldValue = field(default_factory=FieldValue)
    seniority_scope: FieldValue = field(default_factory=FieldValue)
    leadership_type: FieldValue = field(default_factory=FieldValue)
    core_capabilities: List[CapabilityItem] = field(default_factory=list)
    supporting_capabilities: List[CapabilityItem] = field(default_factory=list)
    differentiators: List[CapabilityItem] = field(default_factory=list)
    # Factual inventory of every technology named anywhere in the input,
    # grouped by category — NOT a required/preferred classification. See
    # TechnologyGroup. A bare "Technology Stack" list with no signal language
    # belongs here, never auto-promoted into core/supporting/differentiators.
    technologies_mentioned: List[TechnologyGroup] = field(default_factory=list)
    domain: List[str] = field(default_factory=list)
    explicit_constraints: ExplicitConstraints = field(default_factory=ExplicitConstraints)
    # Restricted, in the prompt, to 8 search-relevant categories only (identity,
    # leadership, seniority, experience, location/work-mode, tier ambiguity,
    # contradiction, domain strictness) — never culture/process/KPI-style gaps.
    open_questions: List[str] = field(default_factory=list)


@dataclass
class IntakeIssue:
    """One ASK/TELL/IGNORE decision from Task B, or one injected by the
    deterministic contradiction backstop (see intake_reasoning.py)."""

    issue: str
    decision: str  # "ask" | "tell" | "ignore"
    # Stable id assigned by the intake session layer (backend/services/
    # intake_session.py) so the frontend/API can address a specific issue
    # when submitting a recruiter answer. Never set by the LLM or the
    # reasoning layer itself.
    id: Optional[str] = None
    reasoning: Optional[str] = None
    question: Optional[str] = None
    options: List[Dict[str, str]] = field(default_factory=list)
    consequence_if_answer_a: Optional[str] = None
    consequence_if_answer_b: Optional[str] = None
    insight_text: Optional[str] = None
    # True only for issues the deterministic backstop injected because Task B
    # did not already cover a detected contradiction — never set by the LLM.
    injected_by_backstop: bool = False
    # Set only on backstop-injected issues ("experience_seniority" |
    # "location_work_mode") — lets the session layer recognize a resolved
    # contradiction category even if a later LLM run phrases it differently.
    backstop_category: Optional[str] = None


@dataclass
class FinalSearchIntentDraft:
    """Task B's tiered judgment only. Location and experience are NOT
    duplicated here — RoleUnderstanding.explicit_constraints is the sole
    source for both (Task B's own re-run on the augmented/clarified input
    already reflects any recruiter-resolved answer, so a second copy here
    was pure duplication, confirmed during the forensic investigation)."""

    hard_requirements: List[str] = field(default_factory=list)
    strong_signals: List[str] = field(default_factory=list)
    preferred_differentiators: List[str] = field(default_factory=list)
    natural_language_search_query: Optional[str] = None
    exclusions: List[str] = field(default_factory=list)


@dataclass
class IntakeDecision:
    """Task B output — the ASK/TELL/IGNORE reasoning over Task A's understanding."""

    issues: List[IntakeIssue] = field(default_factory=list)
    recommended_ask_count: int = 0
    stop_reasoning: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    # One or two plain-language sentences bridging interpretation -> search:
    # how the role understanding actually changed what gets searched (title
    # family, which capability became the primary signal, what was
    # deliberately not required). Always populated — this is a factual bridge
    # statement, not an optional "insight".
    search_consequence_summary: Optional[str] = None
    final_search_intent: FinalSearchIntentDraft = field(default_factory=FinalSearchIntentDraft)


@dataclass
class ContradictionFinding:
    """A finding from the deterministic backstop — never from the LLM. Only
    ever asserts that two facts conflict; never picks a winner."""

    category: str  # "experience_seniority" | "location_work_mode"
    warning: str
    evidence: List[str] = field(default_factory=list)


@dataclass
class IntakeResult:
    raw_input: str = ""
    role_understanding: RoleUnderstanding = field(default_factory=RoleUnderstanding)
    decision: IntakeDecision = field(default_factory=IntakeDecision)
    contradictions: List[ContradictionFinding] = field(default_factory=list)
    # "needs_clarification": at least one ask issue (LLM-authored or
    # backstop-injected) is pending. "ready": safe to map to a SearchIntent.
    status: str = "ready"

    @property
    def pending_ask_issues(self) -> List[IntakeIssue]:
        return [issue for issue in self.decision.issues if issue.decision == "ask"]


def role_understanding_to_dict(understanding: RoleUnderstanding) -> Dict[str, Any]:
    """Round-trips a RoleUnderstanding back to the plain dict shape the Task B
    prompt expects to be given (it was originally parsed from that shape)."""
    constraints = understanding.explicit_constraints
    return {
        "posted_title": understanding.posted_title,
        "primary_candidate_identity": vars(understanding.primary_candidate_identity),
        "hiring_company": vars(understanding.hiring_company),
        "candidate_archetype": vars(understanding.candidate_archetype),
        "role_interpretation": vars(understanding.role_interpretation),
        "seniority_scope": vars(understanding.seniority_scope),
        "leadership_type": vars(understanding.leadership_type),
        "core_capabilities": [vars(item) for item in understanding.core_capabilities],
        "supporting_capabilities": [vars(item) for item in understanding.supporting_capabilities],
        "differentiators": [vars(item) for item in understanding.differentiators],
        "technologies_mentioned": [vars(group) for group in understanding.technologies_mentioned],
        "domain": list(understanding.domain),
        "explicit_constraints": {
            "locations": [vars(entry) for entry in constraints.locations],
            "work_mode": constraints.work_mode,
            "experience_minimum_years": constraints.experience_minimum_years,
            "experience_maximum_years": constraints.experience_maximum_years,
            "employment_type": constraints.employment_type,
            "exclusions": list(constraints.exclusions),
        },
        "open_questions_the_text_leaves_genuinely_unresolved": list(understanding.open_questions),
    }
