"""Dual-source intake reconciliation (feature A).

Takes two independent reads of the SAME role — one from the published JD, one
from the HM/client brief — and reconciles them into a single proposed
`Understanding` plus a human-readable DIFF the recruiter validates inline.

Design contract (see docs/planning/DUAL_SOURCE_INTAKE_PLAN.md):

  * PROPOSE, never decide silently. This module produces a *candidate* intent
    and a diff; the recruiter arbitrates. Downstream (assemble -> briefing ->
    search -> ranking) is untouched — it still consumes one `Understanding`.
  * A1 tiering: a requirement the HM surfaced but the JD omitted is the real
    nuance -> propose CORE. A requirement only the boilerplate JD carried ->
    demote to non-core (supporting). Both-mentioned -> CORE (high confidence).
  * A2 parity: this runs ONLY when both sources are present. A single source
    bypasses reconciliation entirely, so behaviour is byte-identical to today.
  * A3 conflicts: scalar disagreements (years, employment type, work mode) are
    surfaced as explicit conflicts for inline resolution — never averaged. The
    merged default prefers the HM brief (the fresher, authoritative source),
    but the conflict stays visible so the recruiter can flip it.

This module is PURE and deterministic (no I/O, no LLM): it reconciles two
`Understanding` objects a caller already read. The text matcher is injectable so
a semantic (LLM/embedding) matcher can replace the default token matcher later
without changing the diff shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple

from recruiter.agents.intake.model import ReadRequirement, Understanding

SOURCE_JD = "jd"
SOURCE_HM = "hm"
SOURCE_BOTH = "both"

# Non-core landing tier for JD-only boilerplate (A1). The reader's tiers are
# core | supporting | differentiator; "non-core" means supporting.
_NON_CORE = "supporting"

# Tiny stopword set — enough to stop function words from inflating token overlap
# between differently-phrased requirements. Deliberately small; the recruiter's
# inline validation is the real safety net for a missed/false match.
_STOP = frozenset(
    "a an and or the of to in on for with experience years year strong proven "
    "hands expertise knowledge ability skills skill working work using use".split()
)

Matcher = Callable[[str, str], bool]


def _tokens(text: str) -> frozenset:
    return frozenset(t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOP)


def token_matcher(a: str, b: str) -> bool:
    """Deterministic default: two requirement phrases are "the same" when one
    token set contains the other, or they overlap strongly (Jaccard >= 0.6)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True
    inter = len(ta & tb)
    union = len(ta | tb)
    return union > 0 and (inter / union) >= 0.6


@dataclass(frozen=True)
class ReconciledRequirement:
    """One row of the reconciliation diff + the proposed merged requirement."""

    text: str
    tier: str                        # proposed tier after the A1 rule
    source: str                      # jd | hm | both
    when: str = "any"
    evidence: Optional[str] = None
    jd_tier: Optional[str] = None    # original tier in each source (for display)
    hm_tier: Optional[str] = None

    def as_read(self) -> ReadRequirement:
        return ReadRequirement(text=self.text, tier=self.tier, evidence=self.evidence, when=self.when)


@dataclass(frozen=True)
class ExperienceFlag:
    """A soft sanity catch — NOT a JD reconciliation. Minimum years is a HARD
    FILTER the recruiter sets explicitly in the boundary; we never derive or
    nudge it from the JD. But when the HM's own notes state a years figure that
    differs from the filter the recruiter typed, surface it so the recruiter can
    catch a slip (they typed 3; the HM said 5). It changes nothing on its own."""

    boundary_years: int        # the hard filter the recruiter set
    hm_mentioned_years: int    # what the HM brief stated in prose


@dataclass(frozen=True)
class Reconciliation:
    requirements: Tuple[ReconciledRequirement, ...] = ()
    merged: Optional[Understanding] = None
    # Soft years sanity catch (HM prose vs the recruiter's filter). Attached by
    # the caller that knows the boundary; None when there's nothing to confirm.
    experience: Optional["ExperienceFlag"] = None

    @property
    def agree(self) -> Tuple[ReconciledRequirement, ...]:
        return tuple(r for r in self.requirements if r.source == SOURCE_BOTH)

    @property
    def jd_only(self) -> Tuple[ReconciledRequirement, ...]:
        return tuple(r for r in self.requirements if r.source == SOURCE_JD)

    @property
    def hm_only(self) -> Tuple[ReconciledRequirement, ...]:
        return tuple(r for r in self.requirements if r.source == SOURCE_HM)


def _reconcile_requirements(
    jd: Understanding, hm: Understanding, matcher: Matcher
) -> Tuple[ReconciledRequirement, ...]:
    hm_reqs = list(hm.requirements)
    matched_hm: set = set()
    rows: list = []

    # Walk the JD's requirements, pairing each with its best HM match (if any).
    for jr in jd.requirements:
        pair_idx = next(
            (i for i, hr in enumerate(hm_reqs) if i not in matched_hm and matcher(jr.text, hr.text)),
            None,
        )
        if pair_idx is None:
            # JD-only boilerplate -> demote to non-core (A1).
            rows.append(ReconciledRequirement(
                text=jr.text, tier=_NON_CORE, source=SOURCE_JD,
                when=jr.when, evidence=jr.evidence, jd_tier=jr.tier, hm_tier=None,
            ))
            continue
        hr = hm_reqs[pair_idx]
        matched_hm.add(pair_idx)
        # Agreed -> CORE. Prefer the HM phrasing/when/evidence (authoritative),
        # fall back to the JD's where the HM didn't carry it.
        rows.append(ReconciledRequirement(
            text=hr.text or jr.text, tier="core", source=SOURCE_BOTH,
            when=hr.when or jr.when, evidence=hr.evidence or jr.evidence,
            jd_tier=jr.tier, hm_tier=hr.tier,
        ))

    # Whatever the HM surfaced that no JD requirement matched -> the real nuance -> CORE (A1).
    for i, hr in enumerate(hm_reqs):
        if i in matched_hm:
            continue
        rows.append(ReconciledRequirement(
            text=hr.text, tier="core", source=SOURCE_HM,
            when=hr.when, evidence=hr.evidence, jd_tier=None, hm_tier=hr.tier,
        ))
    return tuple(rows)


def _prefer(hm_value, jd_value):
    """Simple precedence for the non-reconciled scalars the merged read still
    carries. These are the recruiter's HARD FILTERS downstream (the boundary
    overrides them in assemble.py), so we do NOT diff or nudge them here — we
    just keep a well-formed Understanding, preferring the HM read when present."""
    return hm_value if hm_value is not None else jd_value


def reconcile(jd: Understanding, hm: Understanding, *, matcher: Matcher = token_matcher) -> Reconciliation:
    """Reconcile two independent reads into one proposed Understanding + a diff.

    Reconciles REQUIREMENTS (the AI-derived capabilities) only. Minimum years,
    work mode and location are the recruiter's explicit hard filters, owned by
    the boundary — never reconciled or nudged from the JD here (see
    `experience_flag` for the one soft years sanity-check, which compares the HM
    prose against the recruiter's filter, not the JD).

    Only called when BOTH sources are present (single-source bypasses this and
    stays byte-identical to today — A2)."""
    requirements = _reconcile_requirements(jd, hm, matcher)

    merged = Understanding(
        identity=jd.identity or hm.identity,
        requirements=tuple(r.as_read() for r in requirements),
        # Title: the JD is the published source of record; fall back to the HM read.
        posted_title=jd.posted_title or hm.posted_title,
        posted_title_source=jd.posted_title_source or hm.posted_title_source,
        min_years=_prefer(hm.min_years, jd.min_years),
        max_years=_prefer(hm.max_years, jd.max_years),
        employment_type=_prefer(hm.employment_type, jd.employment_type),
        work_mode_in_notes=_prefer(hm.work_mode_in_notes, jd.work_mode_in_notes),
    )
    return Reconciliation(requirements=requirements, merged=merged)


def experience_flag(hm: Understanding, boundary_min_years: Optional[int]) -> Optional[ExperienceFlag]:
    """The ONLY years signal: catch a recruiter slip. Minimum years is a hard
    filter the recruiter set in the boundary; if the HM's own notes state a
    different figure, surface it so they can confirm or fix the filter. Silent
    when the HM gave no years, or the two agree. Never changes the filter."""
    if boundary_min_years is None or hm.min_years is None:
        return None
    if int(hm.min_years) == int(boundary_min_years):
        return None
    return ExperienceFlag(boundary_years=int(boundary_min_years), hm_mentioned_years=int(hm.min_years))
