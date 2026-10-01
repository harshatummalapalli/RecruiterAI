"""Phase 1a — the eligibility gate.

Admission answers two different questions that today's pure positional cut
(`ranked_candidates[:target_pool_size]` in search_pipeline) conflates:

  * Eligibility (categorical): is this candidate even a legitimate match for
    the level the search asked for?
  * Ranking (ordinal): among the legitimate matches, who is best?

This module owns ONLY the first question. It never scores and never reorders
within the eligible set — it partitions the ranked candidates into those that
pass the gate and those that don't, preserving the incoming rank order inside
each partition. Ranking stays entirely in candidate_ranker.

What the gate reads (both already computed per candidate, never recomputed
here): `RoleAlignment.level_fit` and `RoleAlignment.experience_floor`.

Design constraints carried from the architecture-hardening plan:

  * Never gate on `level_fit == "unclear"`. CrustData's own seniority field is
    independently unreliable (candidate_evidence_builder documents a real
    "Senior"-labelled "Team Lead" case), and `_classify_level` already routes
    every low-confidence case — conflicting title/headline, no stated level —
    into "unclear" by construction. "above"/"below" are set only from a clear
    title/headline level marker, so `level_fit in ("above", "below")` is
    exactly the confident-mismatch set.
  * Never gate when `level_fit is None` — that means the search stated no
    target seniority, so there is no level to be eligible against.
  * Excluded candidates are removed from the admitted pool (per product
    decision: a Senior search should not surface confirmed Directors), but
    NEVER silently — each exclusion carries a machine-readable reason so it is
    auditable in diagnostics and available to the Phase 3.5 vendor-limitation
    / "filtered out" disclosure. "Hard-exclude" here means "out of the pool,"
    not "erased without a trace."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple, TypeVar

# Machine-readable exclusion reasons. Kept as constants so diagnostics,
# tests, and any future UI disclosure refer to the same identifiers rather
# than matching on prose.
REASON_LEVEL_ABOVE = "level_above_target"
REASON_LEVEL_BELOW = "level_below_target"
REASON_BELOW_EXPERIENCE_FLOOR = "below_experience_floor"


def evaluate_eligibility(
    level_fit: Optional[str],
    experience_floor: Optional[bool],
) -> Tuple[bool, Optional[str]]:
    """The gate's single per-candidate decision, isolated and side-effect-free
    so the regression harness can exercise it directly on frozen signal tuples
    (no live CrustData, no model variance — the gate is the only variable).

    Returns (eligible, reason). `reason` is one of the REASON_* constants when
    ineligible, otherwise None.

    Order of checks is deliberate: a confident level mismatch is reported as a
    level reason even if the floor also fails, because the level signal is the
    stronger statement about fit. `experience_floor is False` is only reached
    when level_fit did not already decide it.
    """
    if level_fit == "above":
        return False, REASON_LEVEL_ABOVE
    if level_fit == "below":
        return False, REASON_LEVEL_BELOW
    # level_fit is "aligned", "unclear", or None here — none of which gate.
    # The experience floor is a separate arithmetic fact; a hard False (the
    # dated roles do not add up to the years asked for) is the one remaining
    # confident mismatch. None (unknown) never gates.
    if experience_floor is False:
        return False, REASON_BELOW_EXPERIENCE_FLOOR
    return True, None


T = TypeVar("T")


@dataclass
class Exclusion:
    """One candidate removed from the admitted pool, with the reason, so the
    decision is never silent."""

    candidate: object
    reason: str


@dataclass
class GateResult:
    eligible: List[object]
    excluded: List[Exclusion]

    @property
    def excluded_candidates(self) -> List[object]:
        return [e.candidate for e in self.excluded]


def partition_by_eligibility(
    ranked_candidates: List[T],
    alignment_of: Callable[[T], Tuple[Optional[str], Optional[bool]]],
) -> GateResult:
    """Split an already-ranked candidate list into eligible and excluded,
    preserving incoming order within each partition. `alignment_of` returns the
    (level_fit, experience_floor) tuple for a candidate; the caller supplies it
    so this function stays free of any dependency on how evidence is built.
    """
    eligible: List[object] = []
    excluded: List[Exclusion] = []
    for candidate in ranked_candidates:
        level_fit, experience_floor = alignment_of(candidate)
        ok, reason = evaluate_eligibility(level_fit, experience_floor)
        if ok:
            eligible.append(candidate)
        else:
            excluded.append(Exclusion(candidate=candidate, reason=reason or ""))
    return GateResult(eligible=eligible, excluded=excluded)
