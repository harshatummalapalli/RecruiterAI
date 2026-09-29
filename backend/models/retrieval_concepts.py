"""Retrieval concepts — storage and representation ONLY (Phase 1). See docs/experiments and the Search Translation
audit this implements: `SearchIntent.core_signals`/`supporting_signals`/`differentiator_signals` remain the sole
authority for what is actually required. Nothing here is read by SearchPlanner, QueryExpansionService,
CrustDataProvider, CandidateRanker, the requirement judge, or admission — that is deliberately Phase 2, not built
yet. The governing rule: retrieval concepts may one day guide HOW a search is built; they must never become, or be
mistaken for, a confirmed hiring requirement.

Every concept here is `derived` (produced by Task A's reasoning over the JD), never recruiter-confirmed — there is no
edit path for any of these fields in ConfirmationEdits (backend/services/confirmation.py), and there must never be
one that lets a retrieval concept rewrite a requirement.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RetrievalConcept:
    value: str
    # Which upstream field this came from, e.g. "task_a.candidate_archetype", "task_a.current_role_concepts",
    # "task_a.technologies_mentioned", "task_a.domain" — where to go looking if this value looks wrong.
    source: str
    # Always True today: nothing here is ever set or edited by the recruiter. Kept explicit (rather than assumed)
    # so a future field that IS recruiter-confirmed can't be mistaken for one of these by omission.
    derived: bool = True
    # Set only for technology_concepts/functional_domain_concepts: which confirmed requirement list (core/
    # supporting/differentiator) this value was found inside, verbatim, as a substring — i.e. which existing,
    # already-confirmed requirement it refers to. None for candidate_archetype/current_role_concepts/
    # career_background_concepts, which do not reference a specific requirement.
    requirement_tier: Optional[str] = None


@dataclass
class RetrievalConcepts:
    """Retrieval-oriented reasoning that Task A already produces (or is well placed to produce) and that used to be
    discarded after intake, or flattened into an undifferentiated requirement sentence. Kept explicitly separate
    from ConfirmedHiringIntent/SearchIntent's requirement fields so it can never be confused with, or silently
    change, what the recruiter actually confirmed."""

    candidate_archetype: Optional[RetrievalConcept] = None
    current_role_concepts: List[RetrievalConcept] = field(default_factory=list)
    career_background_concepts: List[RetrievalConcept] = field(default_factory=list)
    # Only ever a value already present, verbatim, inside a confirmed core/supporting/differentiator requirement —
    # see backend/services/search_translator.build_retrieval_concepts. Never a new, independently-sourced
    # technology/domain claim.
    technology_concepts: List[RetrievalConcept] = field(default_factory=list)
    functional_domain_concepts: List[RetrievalConcept] = field(default_factory=list)
