from typing import List, Optional

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import CandidateEvidence, HarvestEvidence, MatchedSignal
from backend.models.match_explanation import MatchExplanation, MatchedSignalOut
from backend.models.search_intent import SearchIntent
from backend.services.candidate_evidence_builder import build_candidate_evidence

# How a Harvest-sourced signal is phrased in strong_evidence — natural
# sentences, never "Harvest: ..." — the recruiter should read "why this
# matters," not which provider returned it (Phase 10 of the Harvest
# integration plan). CrustData sources ("current title", "headline", "past
# role: ...") already read naturally with the generic "{source} mentions"
# phrasing below and aren't in this map.
#
# PASS 4 (evidence quality, PART 2/6/12): demonstrated-work bullets now quote
# the actual contextual sentence (`evidence_text`) the term was found in —
# "Led A/B testing framework for product experimentation..." — instead of
# the bare matched word ("work described there includes 'work'"). A matched
# word is not evidence; a sentence a recruiter can verify is.
_HARVEST_SOURCE_PHRASING = {
    "harvest: employment description": lambda detail, term, text: f"{detail} — “{text}”",
    "harvest: project": lambda detail, term, text: f"Built a project ({detail}): “{text}”",
    "harvest: certification": lambda detail, term, text: f"Holds a certification: {detail}.",
    "harvest: skill": lambda detail, term, text: f"Lists {detail} as a skill.",
}


class MatchExplainer:
    """Builds a recruiter-facing explanation from the same CandidateEvidence
    CandidateRanker scores against — one source of truth for both, so the
    two can never disagree the way the old skill-matching explainer and the
    metadata-substring ranker used to."""

    def explain(
        self, candidate: Candidate, intent: SearchIntent, harvest_evidence: Optional[HarvestEvidence] = None
    ) -> MatchExplanation:
        evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest_evidence)
        alignment = evidence.role_alignment

        return MatchExplanation(
            relevance_tier=alignment.title_relevance,
            why_this_candidate=self._why_this_candidate(evidence, intent),
            strong_evidence=self._strong_evidence(evidence),
            potential_concerns=self._potential_concerns(evidence),
            what_we_dont_know=[note.note for note in evidence.uncertainty],
            matched_signals=[self._to_signal_out(s) for s in alignment.matched_signals],
            seniority_alignment=alignment.seniority_alignment,
            provider_fit=evidence.search_evidence.provider_fit,
            convergence=evidence.search_evidence.convergence,
            matched_queries=evidence.search_evidence.matched_queries,
            final_score=candidate.final_score,
            self_reported_notes=[evidence.harvest_self_reported_experience] if evidence.harvest_self_reported_experience else [],
            harvest_enriched=bool(harvest_evidence and harvest_evidence.success),
        )

    def _to_signal_out(self, signal: MatchedSignal) -> MatchedSignalOut:
        return MatchedSignalOut(
            tier=signal.tier,
            signal_text=signal.signal_text,
            matched_term=signal.matched_term,
            source=signal.source,
            evidence_type=signal.evidence_type,
            evidence_text=signal.evidence_text,
            strength=signal.strength,
        )

    def _why_this_candidate(self, evidence: CandidateEvidence, intent: SearchIntent) -> str:
        """One or two sentences, headline-aware by construction: this reuses
        `title_relevance_basis` directly (the single place that already
        knows whether the overlap came from the formal title or the
        candidate's own headline) rather than re-deriving a second, possibly
        inconsistent sentence. Never names an internal discovery-query
        strategy (e.g. "natural_language") — that is retrieval plumbing, not
        something a recruiter can act on."""
        alignment = evidence.role_alignment
        parts = [alignment.title_relevance_basis]

        if alignment.seniority_alignment is True:
            parts.append(f"Seniority ({evidence.current_seniority}) aligns with the target level.")
        elif alignment.seniority_alignment is False:
            parts.append(f"Seniority ({evidence.current_seniority}) does not align with the target level ({intent.role.seniority}).")

        if evidence.search_evidence.convergence:
            parts.append("Surfaced independently by more than one search.")

        return " ".join(parts)

    def _strong_evidence(self, evidence: CandidateEvidence) -> List[str]:
        """Every bullet names WHERE the evidence came from (source) rather
        than a vague "title/headline/career history" — a recruiter should be
        able to verify each claim in about the same time it takes to read
        it. Never mentions the internal core/supporting/differentiator
        ranking-weight tiers."""
        # title_relevance_basis is deliberately NOT repeated here — it is
        # already the lead sentence of why_this_candidate, and restating it
        # verbatim as the first bullet added noise rather than a second
        # fact.
        items: List[str] = []
        alignment = evidence.role_alignment

        for signal in alignment.matched_signals:
            phrasing = _HARVEST_SOURCE_PHRASING.get(signal.source)
            if phrasing:
                items.append(phrasing(signal.evidence_detail, signal.matched_term, signal.evidence_text))
            else:
                source = signal.source.capitalize() if signal.source else "Profile"
                items.append(f"{source} mentions “{signal.matched_term}”.")

        return items

    def _potential_concerns(self, evidence: CandidateEvidence) -> List[str]:
        concerns: List[str] = []
        alignment = evidence.role_alignment

        if alignment.seniority_alignment is False:
            concerns.append(alignment.seniority_alignment_basis)

        if alignment.title_relevance in ("tangential", "unclear"):
            concerns.append(
                f"{alignment.title_relevance_basis} Worth verifying manually before treating this as a close match."
            )

        return concerns
