from typing import List, Optional

from pydantic import BaseModel


class MatchedSignalOut(BaseModel):
    tier: str  # "core" | "supporting" | "differentiator" — internal ranking-weight bucket; never render verbatim
    signal_text: str
    matched_term: str
    source: str = ""  # e.g. "current title", "headline", "past role: Data Analyst at Acme"


class MatchExplanation(BaseModel):
    """Evidence-based, never a percentage or a "Good Match" label. Every
    entry in strong_evidence/potential_concerns traces back to a literal
    fact the provider returned for this candidate; what_we_dont_know is
    always populated, explicitly, rather than left implicit."""

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
