from typing import Dict, List, Optional

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import SearchIntent
from backend.services.candidate_evidence_builder import build_candidate_evidence

# Role identity/relevance is the primary signal: a candidate whose current
# title doesn't textually relate to the target role at all is never worth
# ranking above one who directly matches, no matter what else lines up.
TITLE_RELEVANCE_POINTS = {"direct": 3.0, "adjacent": 1.5, "tangential": 0.5, "unclear": 0.0}
# Seniority is real, known evidence when we have it (True/False) and
# contributes a modest amount either way — it never swamps title relevance,
# and an unknown seniority (None) contributes nothing (not a penalty).
SENIORITY_ALIGNED_BONUS = 1.0
SENIORITY_MISALIGNED_PENALTY = -0.5
# Literal textual evidence against the Confirmed Hiring Intent's own
# Core/Supporting/Differentiator sentences — weighted in that same priority
# order, mirroring the intent's own tiering rather than an invented one.
CORE_SIGNAL_WEIGHT = 1.0
SUPPORTING_SIGNAL_WEIGHT = 0.6
DIFFERENTIATOR_SIGNAL_WEIGHT = 0.3
# The provider's own relevance signal, when it was actually returned. Never
# assumed to mean "good candidate" on its own — modest weight, and "weak"
# contributes nothing (it is not treated as negative evidence).
PROVIDER_FIT_STRONG_BONUS = 0.75
# A candidate independently surfaced by more than one discovery query is
# itself a positive signal — two different retrieval paths agreeing is
# stronger evidence than either alone.
CONVERGENCE_BONUS = 0.5
# A small, non-dominant nudge from the provider's own relevance score for
# the query, kept far below every evidence-based signal above.
PROVIDER_SCORE_WEIGHT = 0.01


class CandidateRanker:
    """Rank candidates by evidence against the Confirmed Hiring Intent that
    produced this search — role relevance, seniority alignment, literal
    textual evidence for Core/Supporting/Differentiator signals, provider
    fit, and retrieval convergence. No signal dominates the others, missing
    data is never penalized, and nothing here is specific to any one role —
    see backend/services/candidate_evidence_builder.py for how alignment is
    derived generically from the intent itself."""

    def rank(self, candidates: List[Candidate], intent: SearchIntent) -> List[Candidate]:
        ranked_candidates: List[Candidate] = []

        for candidate in candidates:
            evidence = build_candidate_evidence(candidate, intent)
            candidate.final_score = self._calculate_score(evidence, candidate.provider_score)
            ranked_candidates.append(candidate)

        # final_score is an internal sort key only — never shown to the
        # recruiter as a percentage or raw number (see MatchExplanation,
        # which surfaces a relevance tier + rationale instead). Name is a
        # stable, non-evidentiary final tiebreaker; deliberately NOT the
        # number of career roles on record, which rewards long resumes
        # rather than relevance.
        return sorted(ranked_candidates, key=lambda item: (-(item.final_score or 0.0), item.name or ""))

    def rerank_top_n(
        self,
        baseline_ranked: List[Candidate],
        intent: SearchIntent,
        harvest_by_candidate_id: Dict[str, HarvestEvidence],
        top_n: int,
    ) -> List[Candidate]:
        """Second-stage rerank using Harvest evidence — reuses the identical
        scoring formula `rank()` uses (never a separate/parallel ranking
        algorithm), rescoring ONLY the first `top_n` baseline-ranked
        candidates and re-sorting them among themselves. Every candidate at
        index >= top_n is returned completely untouched, at its original
        baseline position: enrichment can reorder the enriched slice, but
        can never let an enriched candidate jump above one that was never
        considered for enrichment. `baseline_ranked` must already be the
        output of `rank()` — this never re-derives a baseline itself."""
        if top_n <= 0:
            return baseline_ranked

        head = baseline_ranked[:top_n]
        tail = baseline_ranked[top_n:]

        for candidate in head:
            harvest = harvest_by_candidate_id.get(candidate.candidate_id or "")
            evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)
            candidate.final_score = self._calculate_score(evidence, candidate.provider_score)

        reranked_head = sorted(head, key=lambda item: (-(item.final_score or 0.0), item.name or ""))
        return reranked_head + tail

    def _calculate_score(self, evidence, provider_score) -> float:
        alignment = evidence.role_alignment
        score = TITLE_RELEVANCE_POINTS.get(alignment.title_relevance, 0.0)
        score += PROVIDER_SCORE_WEIGHT * float(provider_score or 0.0)

        if alignment.seniority_alignment is True:
            score += SENIORITY_ALIGNED_BONUS
        elif alignment.seniority_alignment is False:
            score += SENIORITY_MISALIGNED_PENALTY
        # None (unknown) contributes nothing — missing data is never a penalty.

        for signal in alignment.matched_signals:
            if signal.tier == "core":
                score += CORE_SIGNAL_WEIGHT
            elif signal.tier == "supporting":
                score += SUPPORTING_SIGNAL_WEIGHT
            elif signal.tier == "differentiator":
                score += DIFFERENTIATOR_SIGNAL_WEIGHT

        if evidence.search_evidence.provider_fit == "strong":
            score += PROVIDER_FIT_STRONG_BONUS
        # "weak" or None contribute nothing — never treated as a negative.

        if evidence.search_evidence.convergence:
            score += CONVERGENCE_BONUS

        return score
