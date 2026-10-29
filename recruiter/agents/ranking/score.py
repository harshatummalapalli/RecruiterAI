"""Scoring. Two scores on the same base:

  baseline  (pre-judge, evidence-aware)  -> decides admission; breaks the
            legacy coin-flip by counting cheap requirement coverage.
  final     (post-judge)                 -> base + VERIFIED coverage; if the
            Judge FAILED for a candidate, fall back to discounted regex
            coverage (the failure-floor) instead of zero, so one Judge glitch
            never sinks a strong candidate.
"""

from __future__ import annotations

from recruiter.agents.ranking.evidence import regex_coverage, title_relevance, verified_coverage
from recruiter.candidates import CandidateRecord
from recruiter.role_model import RoleModel

TITLE_POINTS = {"direct": 3.0, "adjacent": 1.5, "tangential": 0.5, "unclear": 0.0}
CONVERGENCE = 0.5          # surfaced by more than one discovery query
PROVIDER_WEIGHT = 0.01     # tiny nudge from the provider's own relevance
REGEX_DISCOUNT = 0.5       # regex coverage is noisier than verified -> half


def _base(role: RoleModel, record: CandidateRecord) -> float:
    score = TITLE_POINTS.get(title_relevance(role, record), 0.0)
    if len(record.matched_queries) > 1:
        score += CONVERGENCE
    score += PROVIDER_WEIGHT * float(record.provider_score or 0.0)
    return score


def baseline_score(role: RoleModel, record: CandidateRecord) -> float:
    return _base(role, record) + REGEX_DISCOUNT * regex_coverage(role, record)


def final_score(role: RoleModel, record: CandidateRecord) -> float:
    base = _base(role, record)
    if record.judgments is None:                      # Judge failed -> floor, not zero
        return base + REGEX_DISCOUNT * regex_coverage(role, record)
    return base + verified_coverage(record)
