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
    "career dates": lambda detail, term, text: detail,
}


def _labelled(label: str, basis: str) -> str:
    """"Level alignment: the current title ..." — the basis is a full sentence
    that starts with a capital, so it is lower-cased after the label."""
    return f"{label}: {basis[:1].lower()}{basis[1:]}" if basis else label


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
            what_we_dont_know=[note.note for note in evidence.uncertainty]
            + self._level_unknowns(evidence)
            + self._unevidenced_core(evidence),
            matched_signals=[self._to_signal_out(s) for s in alignment.matched_signals],
            seniority_alignment=alignment.seniority_alignment,
            experience_floor=alignment.experience_floor,
            level_fit=alignment.level_fit,
            provider_fit=evidence.search_evidence.provider_fit,
            convergence=evidence.search_evidence.convergence,
            matched_queries=evidence.search_evidence.matched_queries,
            final_score=candidate.final_score,
            self_reported_notes=[evidence.harvest_self_reported_experience] if evidence.harvest_self_reported_experience else [],
            harvest_enriched=bool(harvest_evidence and harvest_evidence.success),
            review_first=self._review_first(evidence),
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

        # Two separate facts, never blended: the experience floor (arithmetic
        # on dated roles) and level alignment (what the titles say against
        # the target). Level is stated here only when it fits; a level that
        # may be above/below is a concern, and an unknown level is a gap.
        if alignment.experience_floor is True:
            parts.append(_labelled("Experience floor met", alignment.experience_floor_basis))
        if alignment.level_fit == "aligned":
            parts.append(_labelled("Level alignment", alignment.level_basis))

        if evidence.search_evidence.convergence:
            parts.append("Surfaced independently by more than one search.")

        return " ".join(parts)

    def _review_first(self, evidence: CandidateEvidence) -> List[str]:
        """Three lines a recruiter can read in ten seconds: what is proven,
        what is not, what to watch. Built only from verified judgments (never
        from unverified text), and empty when no judge ran, so nothing is
        implied about a candidate we could not check."""
        if evidence.requirement_judgments is None:
            return []
        alignment = evidence.role_alignment
        core_met = [s for s in alignment.matched_signals if s.tier == "core"]
        core_missing = [s.signal_text for s in alignment.unmatched_signals if s.tier == "core"]
        total = len(core_met) + len(core_missing)
        if total == 0:
            return []

        def trim(text: str) -> str:
            return text.rstrip(". ")

        shown = [trim(s.signal_text) for s in core_met if s.strength == "strong" and s.source != "career dates"][:3]
        first = f"Evidence for {len(core_met)} of {total} core requirements."
        if shown:
            first += " Shown in described work: " + "; ".join(shown) + "."
        second = (
            "Not evidenced on the profile: " + "; ".join(trim(t) for t in core_missing) + "."
            if core_missing
            else "Every core requirement has evidence on the profile."
        )
        watch: List[str] = list(self._potential_concerns(evidence)[:2])
        if evidence.harvest_self_reported_experience:
            watch.append(evidence.harvest_self_reported_experience)
        third = "Watch: " + " ".join(watch) if watch else "Nothing flagged."
        return [first, second, third]

    def _level_unknowns(self, evidence: CandidateEvidence) -> List[str]:
        """What the titles cannot tell us: level fit that stays unclear, and
        an experience floor that cannot be checked."""
        alignment = evidence.role_alignment
        notes: List[str] = []
        if alignment.level_fit == "unclear":
            notes.append(_labelled("Level alignment", alignment.level_basis))
        if alignment.experience_floor is None and alignment.experience_floor_basis:
            notes.append(alignment.experience_floor_basis)
        return notes

    def _unevidenced_core(self, evidence: CandidateEvidence) -> List[str]:
        """What the profile does NOT prove: the search's core requirements
        with no verified evidence. Only reported when the requirement judge
        ran, because without it "unmatched" only means "no keyword hit" and
        would misstate the candidate. Uses the existing What We Don't Know
        section, so no UI change is needed for a recruiter to see it."""
        if evidence.requirement_judgments is None:
            return []
        missing = [s.signal_text for s in evidence.role_alignment.unmatched_signals if s.tier == "core"]
        if not missing:
            return []
        return ["No evidence found on the profile for these core requirements: " + "; ".join(missing) + "."]

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

        # The same sentence can corroborate several requirements (one role
        # description covering both "backend services" and "high-volume
        # systems"); showing it twice reads as noise, not extra evidence.
        seen: set = set()
        unique: List[str] = []
        for item in items:
            key = " ".join(item.split()).casefold()
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

    def _potential_concerns(self, evidence: CandidateEvidence) -> List[str]:
        concerns: List[str] = []
        alignment = evidence.role_alignment

        if alignment.experience_floor is False:
            concerns.append(_labelled("Experience floor not met", alignment.experience_floor_basis))
        if alignment.level_fit in ("above", "below"):
            note = _labelled("Level alignment", alignment.level_basis)
            if alignment.level_fit == "above":
                note += " Worth confirming the candidate would consider this level."
            concerns.append(note)
        if (
            alignment.seniority_alignment is False
            and alignment.experience_floor is not False
            and alignment.level_fit not in ("above", "below")
        ):
            # The ranker still applies its small penalty for this case (only
            # reachable when the search states no minimum years), so the
            # reason stays visible rather than the ordering going unexplained.
            concerns.append(alignment.seniority_alignment_basis)

        if alignment.title_relevance in ("tangential", "unclear"):
            concerns.append(
                f"{alignment.title_relevance_basis} Worth verifying manually before treating this as a close match."
            )

        return concerns
