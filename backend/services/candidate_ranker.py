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


def _freshness(candidate: Candidate) -> str:
    """The provider's own profile-updated timestamp (ISO, so it sorts
    lexicographically), "" when absent. Used only to break exact score ties."""
    metadata = (candidate.raw_data or {}).get("metadata")
    updated = metadata.get("updated_at") if isinstance(metadata, dict) else None
    return updated if isinstance(updated, str) else ""


def _demonstrated_weight(evidence) -> float:
    """How much of the requirement coverage rests on DEMONSTRATED work (a
    described role, a project, a certification) rather than a listed skill,
    a headline or the career-dates line. Same tier weights the score uses,
    counted only for "strong" evidence. It is not part of the score; it only
    orders candidates whose scores are exactly equal."""
    weights = {"core": CORE_SIGNAL_WEIGHT, "supporting": SUPPORTING_SIGNAL_WEIGHT, "differentiator": DIFFERENTIATOR_SIGNAL_WEIGHT}
    return sum(
        weights.get(signal.tier, 0.0)
        for signal in evidence.role_alignment.matched_signals
        if signal.strength == "strong" and signal.source != "career dates"
    )


def _order(candidates: List[Candidate], demonstrated: Optional[Dict[int, float]] = None) -> List[Candidate]:
    """Score descending. Exact ties are broken by evidence, not by chance:
    more demonstrated-work coverage first, then the most recently updated
    profile, then name only as a last, non-evidentiary resort. Stable passes
    (least significant key first) so no key needs negating."""
    demonstrated = demonstrated or {}
    ordered = sorted(candidates, key=lambda item: item.name or "")
    ordered = sorted(ordered, key=_freshness, reverse=True)
    ordered = sorted(ordered, key=lambda item: -demonstrated.get(id(item), 0.0))
    return sorted(ordered, key=lambda item: -(item.final_score or 0.0))


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
        demonstrated: Dict[int, float] = {}

        for candidate in candidates:
            evidence = build_candidate_evidence(candidate, intent)
            candidate.final_score = self._calculate_score(evidence, candidate.provider_score)
            demonstrated[id(candidate)] = _demonstrated_weight(evidence)
            ranked_candidates.append(candidate)

        # final_score is an internal sort key only — never shown to the
        # recruiter as a percentage or raw number (see MatchExplanation,
        # which surfaces a relevance tier + rationale instead). Name is a
        # stable, non-evidentiary final tiebreaker; deliberately NOT the
        # number of career roles on record, which rewards long resumes
        # rather than relevance.
        return _order(ranked_candidates, demonstrated)

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

        demonstrated: Dict[int, float] = {}
        for candidate in head:
            harvest = harvest_by_candidate_id.get(candidate.candidate_id or "")
            evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)
            candidate.final_score = self._calculate_score(evidence, candidate.provider_score)
            demonstrated[id(candidate)] = _demonstrated_weight(evidence)

        reranked_head = _order(head, demonstrated)
        return reranked_head + tail

    def _calculate_score(self, evidence, provider_score) -> float:
        return sum(self.score_components(evidence, provider_score).values())

    def score_components(self, evidence, provider_score) -> Dict[str, float]:
        """The score, split by what contributed. `_calculate_score` is their
        sum, so this cannot drift from the number that actually ranks."""
        alignment = evidence.role_alignment
        parts: Dict[str, float] = {
            "title_relevance": TITLE_RELEVANCE_POINTS.get(alignment.title_relevance, 0.0),
            "provider_score": PROVIDER_SCORE_WEIGHT * float(provider_score or 0.0),
            "seniority_signal": 0.0,
            "core_coverage": 0.0,
            "supporting_coverage": 0.0,
            "differentiator_coverage": 0.0,
            "provider_fit": 0.0,
            "convergence": 0.0,
        }

        if alignment.seniority_alignment is True:
            parts["seniority_signal"] = SENIORITY_ALIGNED_BONUS
        elif alignment.seniority_alignment is False:
            parts["seniority_signal"] = SENIORITY_MISALIGNED_PENALTY
        # None (unknown) contributes nothing — missing data is never a penalty.

        for signal in alignment.matched_signals:
            if signal.tier == "core":
                parts["core_coverage"] += CORE_SIGNAL_WEIGHT
            elif signal.tier == "supporting":
                parts["supporting_coverage"] += SUPPORTING_SIGNAL_WEIGHT
            elif signal.tier == "differentiator":
                parts["differentiator_coverage"] += DIFFERENTIATOR_SIGNAL_WEIGHT

        if evidence.search_evidence.provider_fit == "strong":
            parts["provider_fit"] = PROVIDER_FIT_STRONG_BONUS
        # "weak" or None contribute nothing — never treated as a negative.

        if evidence.search_evidence.convergence:
            parts["convergence"] = CONVERGENCE_BONUS

        return parts

    def diagnose(
        self,
        ordered: List[Candidate],
        intent: SearchIntent,
        harvest_by_candidate_id: Optional[Dict[str, HarvestEvidence]] = None,
    ) -> List[Dict]:
        """Engineering diagnostic, never shown to a recruiter: for every
        candidate in the final order, what produced the score and why it sits
        where it does relative to its neighbours."""
        harvest_by_candidate_id = harvest_by_candidate_id or {}
        rows: List[Dict] = []
        for candidate in ordered:
            evidence = build_candidate_evidence(
                candidate, intent, harvest_evidence=harvest_by_candidate_id.get(candidate.candidate_id or "")
            )
            alignment = evidence.role_alignment
            real = [s for s in alignment.matched_signals if s.source != "career dates"]
            rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "name": candidate.name,
                    "score": round(candidate.final_score or 0.0, 2),
                    "components": {k: round(v, 2) for k, v in self.score_components(evidence, candidate.provider_score).items()},
                    "requirements_met": {
                        tier: sum(1 for s in alignment.matched_signals if s.tier == tier)
                        for tier in ("core", "supporting", "differentiator")
                    },
                    "requirements_met_excluding_career_dates": len(real),
                    "evidence_strength": {
                        "demonstrated_work": sum(1 for s in real if s.strength == "strong"),
                        "listed_or_headline_only": sum(1 for s in real if s.strength != "strong"),
                    },
                    "demonstrated_weight": round(_demonstrated_weight(evidence), 2),
                    "level_fit": alignment.level_fit,
                    "experience_floor": alignment.experience_floor,
                    "provider_fit": evidence.search_evidence.provider_fit,
                    "convergence": evidence.search_evidence.convergence,
                    "freshness": _freshness(candidate),
                }
            )
        for index, row in enumerate(rows):
            tied = [r for r in rows if r["score"] == row["score"]]
            neighbour = rows[index - 1] if index else None
            if len(tied) == 1:
                row["tie_break_reason"] = "unique score"
            elif neighbour is not None and neighbour["score"] == row["score"]:
                if neighbour["demonstrated_weight"] != row["demonstrated_weight"]:
                    row["tie_break_reason"] = f"tied at {row['score']} with {len(tied) - 1} others; ordered by demonstrated-work evidence"
                elif neighbour["freshness"] != row["freshness"]:
                    row["tie_break_reason"] = f"tied at {row['score']} with {len(tied) - 1} others; identical evidence, ordered by profile freshness"
                else:
                    row["tie_break_reason"] = f"tied at {row['score']} with {len(tied) - 1} others; identical evidence and freshness, ordered by name"
            else:
                row["tie_break_reason"] = f"tied at {row['score']} with {len(tied) - 1} others; first of the tie group"
        return rows
