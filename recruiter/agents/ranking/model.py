"""Ranking shapes: the injected Enricher/Judge interfaces and the result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

from recruiter.candidates import CandidateRecord
from recruiter.role_model import RoleModel


class Enricher(Protocol):
    """Deep profile read (Harvest, a keeper). Mutates the record in place
    (sets raw['_enriched_text'] etc.). A fake no-op is used in tests."""

    def enrich(self, record: CandidateRecord) -> None: ...


class Judge(Protocol):
    """Verified requirement matcher (the Judge, a keeper). Returns the judgments
    (tier/verdict/quote…), or None when it failed for this candidate."""

    def judge(self, role: RoleModel, record: CandidateRecord) -> Optional[Tuple[dict, ...]]: ...


@dataclass(frozen=True)
class ScreenResult:
    """Tier-1 admission verdict on the thin provider data (no enrichment yet)."""
    keep: bool
    score: float        # coarse 0..1 admission priority — ranks who to enrich first
    reason: str = ""


class Screener(Protocol):
    """Tier-1 admission gate (cheap, CrustData-only). Scores a BATCH of candidates on
    the thin provider fields (title, headline, past titles, skills, years, geo) to
    decide WHO is worth the paid Harvest enrichment + the Tier-2 Judge. Deliberately
    different from the Judge: coarse, high-recall, no quotes, one call per batch.
    Returns one ScreenResult per input record, in the same order."""

    def screen(self, role: RoleModel, records: Tuple[CandidateRecord, ...]) -> Tuple[ScreenResult, ...]: ...


class CareerFit(Protocol):
    """Tier-2 holistic career read on the ENRICHED profile. Rates how well the whole
    career fits the role — the arc, the kind of work, progression, projects, skills —
    WITHOUT needing a verbatim quote per requirement (sparse profiles must not be
    buried). Complements the Judge, which proves individual requirements with quotes.
    Returns {"score": 0..1, "rationale": str}; a failure is swallowed by the caller."""

    def assess(self, role: RoleModel, record: CandidateRecord) -> dict: ...


@dataclass(frozen=True)
class RankedCandidate:
    record: CandidateRecord
    score: float
    fit: str            # plain, evidence-based "why this person fits"


@dataclass(frozen=True)
class RankingResult:
    ranked: Tuple[RankedCandidate, ...]   # all admitted (judged), best first
    shown: Tuple[RankedCandidate, ...]    # the top few surfaced
    admitted: int
    judged: int
    judge_failures: int
    experience_excluded: int = 0          # dropped: dated experience clearly below the min-years floor
    # The eligible pool that was NOT admitted: baseline-ranked, un-judged, held in
    # reserve so later phases can promote + judge on demand (reveal / pool-first
    # rerank / refine) without a new paid pull. Nothing here cost a Judge call yet.
    reserve: Tuple[CandidateRecord, ...] = ()
