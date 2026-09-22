from typing import List, Optional

from pydantic import BaseModel


class MatchedSignalOut(BaseModel):
    tier: str  # "core" | "supporting" | "differentiator" — internal ranking-weight bucket; never render verbatim
    signal_text: str
    matched_term: str
    source: str = ""  # e.g. "current title", "headline", "past role: Data Analyst at Acme"
    # PASS 4 (evidence quality) — see backend/models/candidate_evidence.py's
    # MatchedSignal for the full contract. Internal/tooling fields; the UI
    # renders `strong_evidence` (already-phrased natural sentences) instead.
    evidence_type: str = ""
    evidence_text: str = ""
    strength: str = ""


class MatchExplanation(BaseModel):
    """Evidence-based, never a percentage or a "Good Match" label. Every
    entry in strong_evidence/potential_concerns traces back to a literal
    fact the provider returned for this candidate; what_we_dont_know is
    always populated, explicitly, rather than left implicit.

    PASS 4 (evidence quality, PART 8): this model keeps three axes
    structurally independent, and they must stay that way — `relevance_tier`
    /`seniority_alignment` is ROLE ALIGNMENT, `strong_evidence`/
    `matched_signals` is EVIDENCE STRENGTH, and `potential_concerns` is
    REQUIREMENT CONCERNS. None of these fields is derived from another, so a
    candidate with strong Harvest-sourced evidence and an active seniority
    concern shows BOTH — evidence can never silently erase or outweigh a
    concern in this explanation. The recruiter reconciles the tension, not
    the model."""

    relevance_tier: str  # "direct" | "adjacent" | "tangential" | "unclear"
    why_this_candidate: str
    strong_evidence: List[str] = []
    potential_concerns: List[str] = []
    what_we_dont_know: List[str] = []
    matched_signals: List[MatchedSignalOut] = []
    seniority_alignment: Optional[bool] = None
    provider_fit: Optional[str] = None
    convergence: bool = False
    matched_queries: List[str] = []
    final_score: Optional[float] = None
    # Self-authored by the candidate (Harvest "about" text), never verified,
    # never fed into ranking or strong_evidence — kept structurally separate
    # so the UI (and anyone reading this model) can't mistake it for a
    # demonstrated fact. Empty unless a self-reported experience claim (e.g.
    # "11+ years") was found.
    self_reported_notes: List[str] = []
    harvest_enriched: bool = False
