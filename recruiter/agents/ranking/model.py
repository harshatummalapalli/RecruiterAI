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
class RankedCandidate:
    record: CandidateRecord
    score: float
    fit: str            # plain, evidence-based "why this person fits"


@dataclass(frozen=True)
class RankingResult:
    ranked: Tuple[RankedCandidate, ...]   # all admitted, best first
    shown: Tuple[RankedCandidate, ...]    # the top few surfaced
    admitted: int
    judged: int
    judge_failures: int
    experience_excluded: int = 0          # dropped: dated experience clearly below the min-years floor
