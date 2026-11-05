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

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional, Tuple

from recruiter.agents.ranking.evidence import verified_coverage
from recruiter.agents.ranking.experience import below_floor
from recruiter.agents.ranking.explain import explain_fit
from recruiter.agents.ranking.model import Enricher, Judge, RankedCandidate, RankingResult
from recruiter.agents.ranking.score import baseline_score, final_score
from recruiter.candidates import CandidateRecord
from recruiter.role_model import RoleModel


class RankingAgent:
    def __init__(self, judge: Optional[Judge] = None, enricher: Optional[Enricher] = None,
                 admit_n: int = 25, show: int = 5, max_judge_workers: int = 8) -> None:
        self._judge = judge
        self._enricher = enricher
        self._admit_n = admit_n
        self._show = show
        # The admitted candidates are enriched + judged concurrently — the calls are
        # independent per candidate and Judge-bound (an LLM call each), so this is the
        # single biggest latency lever. 1 = sequential (back to the old behaviour).
        self._max_judge_workers = max(1, max_judge_workers)

    def rank(self, role: RoleModel, candidates: List[CandidateRecord],
             on_progress: Optional[Callable[[int, int], None]] = None) -> RankingResult:
        """on_progress(admitted, processed) fires once the pool is admitted (0
        processed) and again after each admitted candidate is enriched+judged, so
        a caller can stream 'Reading profiles: N of M' while the slow per-candidate
        Judge loop runs instead of showing nothing until the end."""
        # 0. Verified experience floor: drop candidates whose OWN dated roles are
        # clearly below the min-years requirement — CrustData's years filter can
        # leak (unreliable field / hybrid-search override), so we re-check here.
        min_years = role.seniority.min_years
        eligible = [c for c in candidates if not below_floor(c, min_years)]
        experience_excluded = len(candidates) - len(eligible)

        # 1-2. evidence-aware baseline -> admit the top N; hold the rest in reserve.
        # The reserve is baseline-ranked and NEVER judged here — it is the demand-
        # driven pool later phases promote from, so the first view only pays the
        # Judge for the N we admit (the judge-N / show-few hedge).
        by_baseline = sorted(eligible, key=lambda c: (-baseline_score(role, c), (c.name or "")))
        admitted = by_baseline[: self._admit_n]
        reserve = tuple(by_baseline[self._admit_n :])
        if on_progress is not None:
            on_progress(len(admitted), 0)

        # 3. enrich + judge the admitted — concurrently (each candidate is
        # independent; the Judge LLM call is the slow part). A single candidate's
        # Judge failure never sinks the search: it floors that one (judgments=None)
        # and the rest proceed. Counters + the progress sink run under a lock so
        # they stay correct and the persisted snapshots are serialised.
        def _process(record: CandidateRecord) -> bool:
            if self._enricher is not None:
                self._enricher.enrich(record)
                record.enriched = True
            if self._judge is not None:
                record.judgments = self._judge.judge(role, record)
                return record.judgments is not None
            return True

        judged = failures = processed = 0
        if admitted:
            lock = threading.Lock()
            workers = min(self._max_judge_workers, len(admitted))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_process, record): record for record in admitted}
                for future in as_completed(futures):
                    try:
                        ok = future.result()
                    except Exception:
                        futures[future].judgments = None
                        ok = False
                    with lock:
                        processed += 1
                        if self._judge is not None:
                            judged += 1 if ok else 0
                            failures += 0 if ok else 1
                        if on_progress is not None:
                            on_progress(len(admitted), processed)

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
            experience_excluded=experience_excluded, reserve=reserve,
        )
