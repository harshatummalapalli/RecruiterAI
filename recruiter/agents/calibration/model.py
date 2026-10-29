"""Calibration's shapes: the recruiter-facing review (plain language, NO query
internals), and the authorization result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from recruiter.agents.intake.model import Question
from recruiter.role_model import RoleModel


@dataclass(frozen=True)
class ReviewLine:
    label: str
    value: str


@dataclass(frozen=True)
class ReviewPackage:
    """What the recruiter sees: our understanding, the honest limits, and the
    questions to confirm. Deliberately carries no NL query / filter fields."""

    summary: Tuple[ReviewLine, ...]
    limits: Tuple[str, ...]
    questions: Tuple[Question, ...]


@dataclass(frozen=True)
class CalibrationResult:
    model: RoleModel                       # the model after the recruiter's answers
    authorized: bool
    blocked_reason: Optional[str] = None
