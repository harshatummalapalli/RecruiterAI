"""The orchestrator — threads the five agents into one flow.

Staged, because there are two human-in-the-loop points:
  read_intent    notes + boundary -> RoleModel, or clarifications (missing years)
  prepare_review ready model      -> the recruiter's intent review + questions
  execute        authorise        -> briefing -> search -> ranking

`run_all` runs the whole thing in one call (for automation / tests) given any
answers up front. All I/O (LLM reader, capability proposer, provider, enricher,
Judge) is injected into the agents, so this composes offline with zero credits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from recruiter.agents.briefing import BriefingAgent, BriefingPlan
from recruiter.agents.calibration import CalibrationAgent, CalibrationResult, ReviewPackage
from recruiter.agents.intake import IntakeAgent, IntakeOutcome
from recruiter.agents.ranking import RankingAgent, RankingResult
from recruiter.agents.search import SearchAgent, SearchResult
from recruiter.agents.search.agent import CREDITS_PER_RESULT
from recruiter.role_model import RoleModel


@dataclass(frozen=True)
class PipelineResult:
    outcome: IntakeOutcome
    review: Optional[ReviewPackage] = None
    authorization: Optional[CalibrationResult] = None
    search: Optional[SearchResult] = None
    ranking: Optional[RankingResult] = None
    model: Optional[RoleModel] = None

    @property
    def blocked(self) -> bool:
        if not self.outcome.ready:
            return True
        return self.authorization is not None and not self.authorization.authorized


class Pipeline:
    def __init__(
        self,
        intake: IntakeAgent,
        briefing: BriefingAgent,
        calibration: CalibrationAgent,
        search: SearchAgent,
        ranking: RankingAgent,
    ) -> None:
        self.intake = intake
        self.briefing = briefing
        self.calibration = calibration
        self.search = search
        self.ranking = ranking

    def read_intent(self, notes: str, boundary: Dict[str, Any], answers: Optional[Dict[str, Any]] = None) -> IntakeOutcome:
        return self.intake.run(notes, boundary, answers=answers)

    def prepare_review(self, outcome: IntakeOutcome) -> Tuple[BriefingPlan, ReviewPackage]:
        plan = self.briefing.build(outcome.model)
        review = self.calibration.review(outcome.model, plan, outcome.refinements)
        return plan, review

    def preview(self, model: RoleModel):
        """The free confidence signal: how many profiles match this intent, before
        any paid search. Returns (matched_count|None, preview_credits)."""
        plan = self.briefing.build(model)
        return self.search.preview_count(plan.query), round(CREDITS_PER_RESULT, 2)

    def execute(
        self,
        model: RoleModel,
        answers: Optional[Dict[str, Any]] = None,
        questions: Tuple = (),
    ) -> Tuple[CalibrationResult, Optional[SearchResult], Optional[RankingResult]]:
        auth = self.calibration.authorize(model, answers or {}, questions)
        if not auth.authorized:
            return auth, None, None
        plan = self.briefing.build(auth.model)
        search_result = self.search.run(plan.query)
        ranking = self.ranking.rank(auth.model, list(search_result.candidates))
        return auth, search_result, ranking

    def run_all(
        self,
        notes: str,
        boundary: Dict[str, Any],
        *,
        intake_answers: Optional[Dict[str, Any]] = None,
        refinement_answers: Optional[Dict[str, Any]] = None,
    ) -> PipelineResult:
        outcome = self.read_intent(notes, boundary, intake_answers)
        if not outcome.ready:
            return PipelineResult(outcome=outcome)
        _, review = self.prepare_review(outcome)
        auth, search_result, ranking = self.execute(outcome.model, refinement_answers or {}, review.questions)
        return PipelineResult(
            outcome=outcome, review=review, authorization=auth,
            search=search_result, ranking=ranking,
            model=auth.model if auth else outcome.model,
        )
