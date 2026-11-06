"""Scoring. Two scores on the same base:

  baseline  (pre-judge, evidence-aware)  -> decides admission; breaks the
            legacy coin-flip by counting cheap requirement coverage.
  final     (post-judge)                 -> base + VERIFIED coverage; if the
            Judge FAILED for a candidate, fall back to discounted regex
            coverage (the failure-floor) instead of zero, so one Judge glitch
            never sinks a strong candidate.
"""

from __future__ import annotations

from typing import Optional

from recruiter.agents.ranking.evidence import TIER_WEIGHT, regex_coverage, title_relevance, verified_coverage
from recruiter.candidates import CandidateRecord
from recruiter.role_model import RoleModel

TITLE_POINTS = {"direct": 3.0, "adjacent": 1.5, "tangential": 0.5, "unclear": 0.0}
CONVERGENCE = 0.5          # surfaced by more than one discovery query
PROVIDER_WEIGHT = 0.01     # tiny nudge from the provider's own relevance
REGEX_DISCOUNT = 0.5       # regex coverage is noisier than verified -> half
# When a career-fit read is present, it is the PRIMARY ranking driver (weighted higher
# than the quote ledger), because not everyone writes their profile like a résumé; the
# quote coverage (normalized 0..1) stays a meaningful secondary so proven requirements
# still move the ranking. base (title/convergence) remains a small tiebreak on top.
CAREER_WEIGHT = 10.0
COVERAGE_WEIGHT = 6.0


def _career_fit(record: CandidateRecord) -> Optional[float]:
    raw = record.raw if isinstance(record.raw, dict) else {}
    cf = raw.get("_career_fit")
    if isinstance(cf, dict) and isinstance(cf.get("score"), (int, float)):
        return max(0.0, min(1.0, float(cf["score"])))
    return None


def _max_coverage(role: RoleModel) -> float:
    total = sum(TIER_WEIGHT.get(req.tier, 0.0) * (0.5 if req.when == "past" else 1.0) for req in role.requirements)
    return total or 1.0


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
    coverage = REGEX_DISCOUNT * regex_coverage(role, record) if record.judgments is None else verified_coverage(record)
    career = _career_fit(record)
    if career is None:
        # No career-fit signal (fake pipeline, assessor off/failed) -> previous behaviour.
        return base + coverage
    coverage_fraction = min(1.0, coverage / _max_coverage(role))
    return base + CAREER_WEIGHT * career + COVERAGE_WEIGHT * coverage_fraction
