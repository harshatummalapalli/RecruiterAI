"""Agent 5 — Ranking. The back-half brain.

  1. baseline-rank the pool on the evidence-aware score (not a coin-flip),
  2. admit the top N,
  3. enrich + Judge only the admitted (enrichment/Judge injected),
  4. final-score with the failure-floor, re-rank, surface the top few with a
     plain, evidence-based explanation of fit.

No eligibility label-gate: years are already a retrieval filter, and seniority
labels never exclude (see the RoleModel seniority decision).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from recruiter.agents.ranking.evidence import verified_coverage
from recruiter.agents.ranking.experience import below_floor
from recruiter.agents.ranking.explain import explain_fit
from recruiter.agents.ranking.model import Enricher, Judge, RankedCandidate, RankingResult
from recruiter.agents.ranking.score import baseline_score, final_score
from recruiter.candidates import CandidateRecord
from recruiter.role_model import RoleModel


class RankingAgent:
    def __init__(self, judge: Optional[Judge] = None, enricher: Optional[Enricher] = None,
                 admit_n: int = 25, show: int = 5) -> None:
        self._judge = judge
        self._enricher = enricher
        self._admit_n = admit_n
        self._show = show

    def rank(self, role: RoleModel, candidates: List[CandidateRecord]) -> RankingResult:
        # 0. Verified experience floor: drop candidates whose OWN dated roles are
        # clearly below the min-years requirement — CrustData's years filter can
        # leak (unreliable field / hybrid-search override), so we re-check here.
        min_years = role.seniority.min_years
        eligible = [c for c in candidates if not below_floor(c, min_years)]
        experience_excluded = len(candidates) - len(eligible)

        # 1-2. evidence-aware baseline -> admit the top N.
        by_baseline = sorted(eligible, key=lambda c: (-baseline_score(role, c), (c.name or "")))
        admitted = by_baseline[: self._admit_n]

        # 3. enrich + judge only the admitted.
        judged = failures = 0
        for record in admitted:
            if self._enricher is not None:
                self._enricher.enrich(record)
                record.enriched = True
            if self._judge is not None:
                record.judgments = self._judge.judge(role, record)
                if record.judgments is None:
                    failures += 1
                else:
                    judged += 1

        # 4. final score (with failure-floor) -> re-rank -> explain.
        for record in admitted:
            record.final_score = final_score(role, record)
        ranked = sorted(
            admitted,
            key=lambda c: (-(c.final_score or 0.0), -verified_coverage(c), (c.name or "")),
        )
        rows: Tuple[RankedCandidate, ...] = tuple(
            RankedCandidate(record=c, score=round(c.final_score or 0.0, 3), fit=explain_fit(role, c))
            for c in ranked
        )
        return RankingResult(
            ranked=rows, shown=rows[: self._show],
            admitted=len(admitted), judged=judged, judge_failures=failures,
            experience_excluded=experience_excluded,
        )
