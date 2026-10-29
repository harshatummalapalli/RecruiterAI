"""Judge backed by the keeper RequirementJudge (quote-verified, reviewed).

Translates the RoleModel's tiered requirements into the keeper SearchIntent's
signal lists and the CandidateRecord into a keeper Candidate, passes any Harvest
evidence, and returns the judgments (or None on failure). Lazy backend import.
"""

from __future__ import annotations

from typing import Optional, Tuple

from recruiter.candidates import CandidateRecord
from recruiter.role_model import RoleModel


def _to_intent(role: RoleModel):
    from backend.models.search_intent import SearchIntent

    return SearchIntent(
        core_signals=[r.text for r in role.tier("core")],
        supporting_signals=[r.text for r in role.tier("supporting")],
        differentiator_signals=[r.text for r in role.tier("differentiator")],
    )


class JudgeAdapter:
    def __init__(self, judge=None, model: Optional[str] = None) -> None:
        self._judge = judge
        self._model = model

    def _get(self):
        if self._judge is None:
            from backend.services.requirement_judge import RequirementJudge
            self._judge = RequirementJudge(model=self._model) if self._model else RequirementJudge()
        return self._judge

    def judge(self, role: RoleModel, record: CandidateRecord) -> Optional[Tuple[dict, ...]]:
        from backend.models.candidate import Candidate

        candidate = Candidate(candidate_id=record.candidate_id, title=record.title,
                              company=record.company, raw_data=record.raw)
        harvest = record.raw.get("_harvest_evidence")
        outcome = self._get().judge_detailed(candidate, _to_intent(role), harvest_evidence=harvest)
        return tuple(outcome.judgments) if outcome.judgments is not None else None
