"""Agent 3 — Calibration. Validate our understanding with the recruiter, apply
their answers, and authorize the run.

The recruiter sees `review()` (plain-language intent + questions). On submit,
`authorize()` applies the answers and signs off — unless the recruiter rejected
the interpretation (confirm_level = "no"), which blocks until they fix the role.
The raw query is available only via `admin_query()`.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from recruiter.agents.briefing.model import BriefingPlan
from recruiter.agents.calibration.admin import admin_query_view
from recruiter.agents.calibration.apply import apply_answers
from recruiter.agents.calibration.model import CalibrationResult, ReviewPackage
from recruiter.agents.calibration.view import build_review
from recruiter.agents.intake.model import Question
from recruiter.role_model import RoleModel


class CalibrationAgent:
    def review(self, model: RoleModel, plan: BriefingPlan, refinements: Tuple[Question, ...]) -> ReviewPackage:
        return build_review(model, plan.disclosures, refinements)

    def authorize(
        self,
        model: RoleModel,
        answers: Dict[str, Any],
        questions: Tuple[Question, ...] = (),
    ) -> CalibrationResult:
        if answers.get("confirm_level") == "no":
            return CalibrationResult(
                model=model, authorized=False,
                blocked_reason="You flagged the role interpretation as wrong — please correct the role before searching.",
            )
        return CalibrationResult(model=apply_answers(model, answers, questions), authorized=True)

    def admin_query(self, plan: BriefingPlan) -> Dict[str, Any]:
        return admin_query_view(plan)
